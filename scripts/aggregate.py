#!/usr/bin/env python3
"""Aggregate the reviewed manifests under `plugins/` into one `catalog.json`.

amenbo has no server: discovery is served from a single static file. This script builds that file.
For every `plugins/<name>.yaml` it:

1. checks the file name agrees with the manifest's `name`;
2. validates the manifest with **amenbo's own validator** (`amenbo plugin validate`), so the catalog
   door and the client's install door can never disagree about what "valid" means;
3. refuses an `official: true` claim from anyone outside the amenbo team — the badge is curation, never
   self-declaration;
4. downloads every distributable the manifest publishes and checks its SHA-256 against the declared
   `checksum`, so a manifest whose digest does not match what the URL actually serves never reaches a user;
5. signs the downloaded bytes with the amenbo **catalog key** (`--sign-key`) and verifies the signature
   back against the public key before trusting it — or, where the bytes are the ones already published,
   carries the signature already made over them ([carried_over]).

A manifest publishes either one distributable for every platform it lists (`url` / `checksum`) or **one
per platform** (`assets`, keyed `<os>` or `<os>-<arch>`); `assets` is what decides which, exactly as it does
at amenbo's install door. Steps 4 and 5 run over each of them, because a checksum and a signature are claims
about the bytes that will actually run — so their grain is the bytes', not the entry's. An entry is
all-or-nothing: one platform's asset failing rejects the whole entry, since a listing that claims a platform
it cannot serve is what the client refuses.

The signature is what an amenbo client verifies at install time against the catalog public key it ships
with. It does not say "the author signed this"; it says "these exact bytes went through this catalog's
review". That is the whole trust root, so it is produced here and nowhere else — authors never hold a key.

The catalog is published as **two kinds of document**. `catalog.json` holds one small entry per plugin —
what a browse view draws — and everyone fetches it whole, once. `plugins/<name>.json` holds what an install
needs, signature and digests included, and is fetched for the one plugin someone opened or is installing.
Which half a field belongs in is amenbo's answer, not this script's: `plugin validate --json` hands back the
manifest already split into `entry` and `detail`, and this script publishes them. A field amenbo grows is
carried without a change here, instead of being dropped from every install until someone notices; the one
thing this script still names by hand is the distributable, which it does not copy but rebuilds around a
signature (see [DISTRIBUTABLE_KEYS]).

Each entry also carries `detail_sum`, the digest of the detail document exactly as published. It is what
lets a client notice a plugin has a different build from the one list fetch it already makes, now that the
checksums themselves are a document away. It is computed here, over the bytes written, so it cannot be
declared wrong by an author or drift from the file it names.

**That digest is only worth comparing if publishing twice over the same plugin writes the same bytes.** A
minisign signature carries the moment it was made, so a catalog that re-signs everything it publishes moves
every plugin's detail document every time anything at all is listed — and every client reads that as a new
build of every plugin. `--published` is what closes it: an asset whose bytes are the ones already published
keeps the signature already published over them.

An entry is marked `featured` when the curation list (`--featured`, [read_featured]) names it. That list
is the only place the recommendation exists: a manifest cannot carry it, because a manifest is written by
the person asking to be recommended. `official` can afford to live in a manifest and be refused from the
wrong owner — it is a fact about authorship, checkable from the repository. Being recommended is a
judgement about the plugin, so no owner test can grant it and there is nothing in a submission to check.
Keeping it in a separate file makes a submitter's pull request unable to express it at all, and makes a
change to the curation a diff of its own.

Entries that fail are **dropped** with a reason: a rotted third-party URL should stop that one plugin
from being listed, not stop the catalog from being published. `--strict` turns any rejection into a
failed run instead, which is what a dry run before merging wants.

Naming manifests on the command line aggregates just those, instead of everything under `--plugins-dir`.
That is the other half of the dry run: the pull-request gate fetches the assets of the manifests *that
pull request touches*, and leaves the already-listed ones alone — their URLs are not the submitter's to
keep alive, and under `--strict` one rotted third-party asset would otherwise block every unrelated PR.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

#: The catalog file's own schema version. Bumped only when the *envelope* changes; entries evolve by
#: adding fields, which older clients ignore.
CATALOG_V = 1

#: GitHub owners whose plugins may carry `official: true` — i.e. the amenbo team. Official means the
#: author is the team; being listed here at all is a separate, weaker thing (review, not endorsement).
OFFICIAL_OWNERS = frozenset({"ShiroDoromoto"})

#: The keys a detail document does not carry through but **rebuilds**: the distributable. [publish] fetches
#: the bytes, checks them against the declared digest, and signs them, so `url` / `checksum` / `assets`
#: are replaced with the catalog's own copy carrying the signature over the exact bytes served.
#:
#: This is the *only* schema this script still holds by name. Every other field a manifest declares rides
#: through from amenbo's own reading of it (see [build_documents]) — the catalog keeps no whitelist of
#: fields, and no opinion about which document each belongs in, to fall out of step with amenbo. A
#: whitelist here is what drops a field amenbo adds from every install until somebody notices.
DISTRIBUTABLE_KEYS = frozenset({"url", "checksum", "assets"})

#: The largest asset this catalog will fetch to hash and sign.
MAX_ASSET_BYTES = 256 * 1024 * 1024
#: Seconds to wait on the asset download before giving up on an entry.
DOWNLOAD_TIMEOUT = 60


class Rejected(Exception):
    """One manifest did not make it into the catalog. The message is the reason, shown in the report."""


# --- the checks ------------------------------------------------------------------------------------


def check_file_name(path: Path, manifest: dict) -> None:
    """`plugins/<name>.yaml` must be named for the plugin it declares — the file name is the identity a
    reviewer sees in the diff, so it may not disagree with the manifest."""
    declared = manifest.get("name")
    if path.stem != declared:
        raise Rejected(f"file name does not match the manifest name ({path.name} vs name: {declared!r})")


def check_manifest(amenbo: str, path: Path) -> tuple[dict, dict]:
    """Run amenbo's validator over the manifest and, on success, return the two documents it split the
    manifest into: `(entry, detail)`. Every problem it reports is re-raised instead.

    Publishing amenbo's own reading is what lets this script hold no list of fields to copy, and no idea of
    which half each belongs in: a field amenbo grows rides through untouched, and one amenbo does not know
    is not a field at all (its deserializer ignores unknown keys, the same forward-compatibility a client
    relies on). An amenbo too old to split the manifest is refused rather than guessed around — a document
    built from a guess is the silent drop this arrangement exists to end.
    """
    proc = subprocess.run(
        [amenbo, "--json", "plugin", "validate", str(path)],
        capture_output=True,
        text=True,
    )
    try:
        report = json.loads(proc.stdout)
    except json.JSONDecodeError:
        raise Rejected(f"amenbo plugin validate did not report: {proc.stderr.strip() or proc.stdout.strip()}")
    if not report.get("ok"):
        if report.get("parse_error"):
            raise Rejected(f"not a valid manifest — {report['parse_error']}")
        problems = "; ".join(
            f"{p.get('location', '?')}: {p.get('message', '?')}" for p in report.get("problems", [])
        )
        raise Rejected(f"invalid manifest — {problems}")
    entry, detail = report.get("entry"), report.get("detail")
    if not isinstance(entry, dict) or not isinstance(detail, dict):
        raise Rejected(
            "amenbo plugin validate reported ok but returned no entry/detail — the amenbo CLI is too old "
            "(it needs the build that splits a manifest into the two documents the catalog serves)"
        )
    return entry, detail


def check_official(manifest: dict) -> None:
    """The official badge is the catalog's to grant. A third-party manifest that sets it is refused
    outright rather than quietly downgraded, so the submitter learns why."""
    if not manifest.get("official"):
        return
    owner = str(manifest.get("repo", "")).split("/", 1)[0]
    if owner not in OFFICIAL_OWNERS:
        raise Rejected(
            f"official: true is catalog-authoritative and {owner or '(no owner)'} is not the amenbo team"
        )


def download(url: str) -> bytes:
    """Fetch the asset the manifest points at, bounded in size and time."""
    request = urllib.request.Request(url, headers={"User-Agent": "amenbo-catalog-aggregator"})
    try:
        with urllib.request.urlopen(request, timeout=DOWNLOAD_TIMEOUT) as response:
            data = response.read(MAX_ASSET_BYTES + 1)
    except (urllib.error.URLError, OSError, ValueError) as e:
        raise Rejected(f"could not download the asset: {e}")
    if len(data) > MAX_ASSET_BYTES:
        raise Rejected(f"asset is larger than the {MAX_ASSET_BYTES // (1024 * 1024)} MiB ceiling")
    if not data:
        raise Rejected("the asset URL served no bytes")
    return data


def check_checksum(data: bytes, checksum: str) -> None:
    """The declared digest must be the digest of what the URL actually served. The validator already
    checked the digest's *shape*; this is the only place the catalog learns whether it is *true*."""
    actual = hashlib.sha256(data).hexdigest()
    declared = checksum.split(":", 1)[1].lower()
    if actual != declared:
        raise Rejected(f"checksum does not match the asset (url serves sha256:{actual})")


def verify(data: bytes, signature: str, label: str, public_key: Path) -> bool:
    """Whether this signature holds over these exact bytes, under the catalog's public key.

    Every signature the catalog publishes goes through here, whether it was just made or is being carried
    over from the last publish — a signature this catalog cannot itself verify would fail on every user's
    machine, and it is far cheaper to learn that here.
    """
    with tempfile.TemporaryDirectory() as tmp:
        asset = Path(tmp) / label
        signature_file = Path(tmp) / f"{label}.minisig"
        asset.write_bytes(data)
        signature_file.write_text(signature)
        verifying = subprocess.run(
            ["minisign", "-V", "-p", str(public_key), "-m", str(asset), "-x", str(signature_file)],
            capture_output=True,
            text=True,
        )
        return verifying.returncode == 0


def sign(data: bytes, label: str, key: Path, password: str, public_key: Path) -> str:
    """Sign the asset bytes with the catalog key and return the full minisign signature text.

    The bytes are signed under `label` so that minisign's trusted comment — which is signed too — names
    what was signed (the plugin, and its platform where there is one per platform) rather than a temporary
    file.
    """
    with tempfile.TemporaryDirectory() as tmp:
        asset = Path(tmp) / label
        signature = Path(tmp) / f"{label}.minisig"
        asset.write_bytes(data)
        signing = subprocess.run(
            ["minisign", "-S", "-s", str(key), "-m", str(asset), "-x", str(signature)],
            input=f"{password}\n",
            capture_output=True,
            text=True,
        )
        if signing.returncode != 0 or not signature.exists():
            # The password is on stdin, never in argv or in this message.
            raise Rejected(f"signing failed: {signing.stderr.strip()}")
        text = signature.read_text()
    if not verify(data, text, label, public_key):
        raise Rejected("the signature did not verify against the catalog public key")
    return text


def read_featured(path: Path) -> set[str]:
    """The plugins this catalog recommends, one name per line — the hand-curated "featured" axis.

    A flat list of names, not YAML: it has no structure to gain from one, and this script's only
    dependency is the amenbo binary it validates with. Blank lines and `#` comments are ignored, and a
    missing file simply means nothing is recommended yet.

    The list is a set, not a ranking. It says *which* plugins are recommended and nothing about their
    order among themselves, so the order of the lines here carries no meaning and a client is free to sort
    the recommended ones however it likes.
    """
    if not path.exists():
        return set()
    names = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        name = line.split("#", 1)[0].strip()
        if name:
            names.add(name)
    return names


def added_at(path: Path) -> str | None:
    """When this manifest first landed in the catalog, from git history — the "new" axis of the browser.

    A client holds the catalog, not the repository, so this date exists only if the aggregation writes
    it down. Returns None outside a git checkout, or for a file not committed yet (a pull request).
    """
    result = subprocess.run(
        ["git", "log", "--diff-filter=A", "--format=%aI", "--", str(path)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        return None
    dates = [line for line in result.stdout.splitlines() if line.strip()]
    return dates[-1] if dates else None


# --- assembling ------------------------------------------------------------------------------------


def already_published(name: str, source: str | None) -> dict | None:
    """The detail document this catalog currently publishes for `name`, or None when there is none to read.

    `source` is where the catalog is served from — the base URL, or a directory holding a copy of it. Every
    way of failing to read it answers the same way: no previous document. What that costs is a fresh
    signature, which is the outcome this script had before it could look at all.
    """
    if not source:
        return None
    try:
        if source.startswith("http://") or source.startswith("https://"):
            document = download(f"{source.rstrip('/')}/plugins/{name}.json")
        else:
            document = (Path(source) / "plugins" / f"{name}.json").read_bytes()
        parsed = json.loads(document.decode("utf-8"))
    except (Rejected, OSError, ValueError):
        return None
    return parsed if isinstance(parsed, dict) else None


def carried_over(previous: dict | None, data: bytes, checksum: str, label: str, public_key: Path) -> str | None:
    """The signature this catalog already published over these exact bytes, when it still holds.

    A minisign signature carries the moment it was made, so signing the same bytes twice produces two
    different documents — and a detail document that moves says a plugin has a new build when nothing about
    it has changed. What a signature claims is that these bytes went through this catalog's review, not when
    they did, so the one made last time supports that claim exactly as well.

    It is carried over only when the bytes are the same ones (the digest published beside it) **and** it
    verifies over them here. Anything else — no previous document, an unsigned one, a different asset, a
    signature that no longer verifies — answers None and the caller signs afresh.
    """
    if not previous:
        return None
    signature = previous.get("signature")
    if not isinstance(signature, str) or previous.get("checksum") != checksum:
        return None
    return signature if verify(data, signature, label, public_key) else None


def publish(distributable: dict, label: str, args: argparse.Namespace, previous: dict | None) -> dict:
    """Fetch one distributable, check it against its declared digest, sign it, and return the catalog's
    copy of it — `url`, `checksum`, and the `signature` over the exact bytes served.

    `label` names the bytes in minisign's trusted comment, which is signed along with them. For a
    per-platform asset it carries the platform, so a signature says which distributable of a plugin it
    covers.

    `previous` is what the catalog publishes for this distributable now, if anything: an unchanged asset
    keeps the signature it already has ([carried_over]).
    """
    data = download(distributable["url"])
    check_checksum(data, distributable["checksum"])
    published = {"url": distributable["url"], "checksum": distributable["checksum"]}
    if args.sign_key:
        published["signature"] = carried_over(
            previous, data, distributable["checksum"], label, args.public_key
        ) or sign(data, label, args.sign_key, args.sign_password, args.public_key)
    return published


def is_signed(detail: dict) -> bool:
    """Whether every distributable in a built detail carries a signature — what a run without a key lacks."""
    assets = detail.get("assets")
    if assets:
        return all("signature" in asset for asset in assets.values())
    return "signature" in detail


def encode(document: dict) -> str:
    """Serialize one published document. Both files go through here, so `detail_sum` is a digest of exactly
    the bytes the detail file is written with — sorted keys and all — rather than of a second rendering that
    could differ by a space."""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


@dataclass
class Published:
    """One plugin, as the catalog publishes it: its list entry, and the detail document the entry's
    `detail_sum` names — carried together with the exact text that document is written as."""

    entry: dict
    detail: dict
    detail_text: str


def build_documents(path: Path, args: argparse.Namespace) -> Published:
    """Run one manifest through every check and return what the catalog publishes for it, or raise
    [Rejected].

    The two documents are amenbo's own split of the manifest, with one thing rebuilt: [publish] replaces
    the detail's `url` / `checksum` / `assets` with the catalog's copy, signed over the exact bytes served
    ([DISTRIBUTABLE_KEYS]). Everything else rides through untouched, which is the point — the catalog holds
    no second copy of amenbo's schema, and no second opinion about which document a field belongs in.
    """
    entry, manifest_detail = check_manifest(args.amenbo, path)
    check_file_name(path, entry)
    check_official(entry)
    entry.setdefault("official", False)

    detail = {key: value for key, value in manifest_detail.items() if key not in DISTRIBUTABLE_KEYS}
    # Read once per plugin, and only where a signature is being made at all: without a key there is
    # nothing to carry over.
    previous = already_published(entry["name"], args.published) if args.sign_key else None

    # `assets` alone decides which of the two distributable forms is in play — the same rule the client's
    # install door reads, so a detail can never mean one thing here and another there. The validator above
    # has already established that whichever form this manifest uses is complete.
    assets = manifest_detail.get("assets")
    if assets:
        published = {}
        previous_assets = (previous or {}).get("assets") or {}
        for platform, asset in sorted(assets.items()):
            try:
                published[platform] = publish(
                    asset, f"{entry['name']}-{platform}", args, previous_assets.get(platform)
                )
            except Rejected as e:
                # *Which* distributable failed is an author's first question once a plugin publishes
                # several, so name it where the validator names it — under `assets.<platform>`.
                raise Rejected(f"assets.{platform}: {e}")
        detail["assets"] = published
    else:
        detail.update(publish(manifest_detail, entry["name"], args, previous))

    # The digest is taken over the text that will be written, and written into the entry that points at it,
    # so the pair is consistent by construction. amenbo compares this value and nothing else to notice a
    # plugin whose install information has moved.
    detail_text = encode(detail)
    entry["detail_sum"] = "sha256:" + hashlib.sha256(detail_text.encode("utf-8")).hexdigest()
    entry["added_at"] = added_at(path)
    # Written here and nowhere else: whatever the manifest said about being recommended (amenbo does not
    # even read such a key) is replaced by what the curation list says.
    entry["featured"] = entry["name"] in args.featured_names
    return Published(entry=entry, detail=detail, detail_text=detail_text)


def report(lines: list[str]) -> None:
    """Print the run's outcome, and mirror it into the GitHub job summary when there is one."""
    text = "\n".join(lines)
    print(text)
    summary = os.environ.get("GITHUB_STEP_SUMMARY")
    if summary:
        with open(summary, "a", encoding="utf-8") as f:
            f.write(text + "\n")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugins-dir", type=Path, default=Path("plugins"), help="where the manifests live")
    parser.add_argument("--out", type=Path, default=Path("_site/catalog.json"), help="the catalog to write")
    parser.add_argument("--detail-dir", type=Path, help="where to write plugins/<name>.json; default: a plugins/ directory beside --out")
    parser.add_argument("--amenbo", default=os.environ.get("AMENBO_BIN", "amenbo"), help="the amenbo CLI to validate with")
    parser.add_argument("--sign-key", type=Path, help="the catalog signing key; without it, entries are unsigned")
    parser.add_argument("--public-key", type=Path, default=Path("catalog-key.pub"), help="the public half, to verify each signature")
    parser.add_argument("--published", help="where this catalog is served from (a base URL, or a directory holding a copy): an asset that has not changed keeps the signature published there, so a detail document only moves when the plugin does")
    parser.add_argument("--featured", type=Path, default=Path("featured.txt"), help="the curation list: the plugins this catalog recommends, one name per line")
    parser.add_argument("--strict", action="store_true", help="fail the run on any rejected manifest, rather than dropping it (a dry run before merging)")
    parser.add_argument("manifests", nargs="*", type=Path, help="the manifests to aggregate; default: every *.yaml under --plugins-dir")
    args = parser.parse_args()

    args.sign_password = os.environ.get("CATALOG_SIGNING_PRIVATE_KEY_PASSWORD", "")
    args.featured_names = read_featured(args.featured)
    if args.sign_key and not args.sign_key.exists():
        print(f"error: signing key not found: {args.sign_key}", file=sys.stderr)
        return 1

    # The detail documents sit under the catalog, so a client resolves one by name against the URL it
    # already fetched the list from. Writing them into the reviewed manifests instead would put derived
    # files in the one directory that is the source of truth, so that shape is refused rather than tidied
    # up afterwards.
    if args.detail_dir is None:
        args.detail_dir = args.out.parent / "plugins"
    if args.detail_dir.resolve() == args.plugins_dir.resolve():
        print(
            f"error: --detail-dir would write the published documents into the reviewed manifests "
            f"({args.detail_dir}) — point --out at a build directory, or pass --detail-dir",
            file=sys.stderr,
        )
        return 1

    manifests = sorted(args.manifests) if args.manifests else sorted(args.plugins_dir.glob("*.yaml"))
    published: list[Published] = []
    rejections: list[str] = []
    for path in manifests:
        try:
            documents = build_documents(path, args)
        except Rejected as e:
            rejections.append(f"{path}: {e}")
            continue
        published.append(documents)

    lines = [f"## Catalog: {len(published)} of {len(manifests)} manifests"]
    lines += [
        f"- ok: `{p.entry['name']}`"
        + (" featured" if p.entry["featured"] else "")
        + (f" ({', '.join(p.detail['assets'])})" if "assets" in p.detail else "")
        + ("" if is_signed(p.detail) else " (unsigned)")
        for p in published
    ]
    lines += [f"- **rejected** {r}" for r in rejections]
    # A curated name that matches no manifest is a typo that would otherwise fail silently — the plugin
    # simply never gets its badge. Only worth saying on a full run: the pull-request gate aggregates the
    # manifests one PR touched, where every *other* recommended plugin is legitimately absent.
    if not args.manifests:
        stray = sorted(args.featured_names - {p.entry["name"] for p in published})
        lines += [f"- **not listed, so not featured**: `{name}` (in {args.featured})" for name in stray]
    report(lines)

    if rejections and args.strict:
        print("error: a manifest was rejected (strict)", file=sys.stderr)
        return 1
    # Publishing a catalog where nothing survived would replace a good catalog with an empty one. That is
    # a systemic failure (the network, the validator, the key), not a plugin going away.
    if manifests and not published:
        print("error: every manifest was rejected — refusing to publish an empty catalog", file=sys.stderr)
        return 1

    # The details go down first: an entry naming a detail_sum for a document that is not there yet is the
    # one ordering a client can actually catch out. Nothing is deleted here — a run over some of the
    # manifests (the pull-request gate) is not evidence that the rest have gone away.
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.detail_dir.mkdir(parents=True, exist_ok=True)
    for p in published:
        (args.detail_dir / f"{p.entry['name']}.json").write_text(p.detail_text)

    catalog = {
        "catalog_v": CATALOG_V,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": [p.entry for p in published],
    }
    args.out.write_text(encode(catalog))
    print(f"wrote {args.out} and {len(published)} detail document(s) under {args.detail_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
