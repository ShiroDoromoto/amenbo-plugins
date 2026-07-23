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
   back against the public key before trusting it.

A manifest publishes either one distributable for every OS it lists (`url` / `checksum`) or **one per OS**
(`assets`); `assets` is what decides which, exactly as it does at amenbo's install door. Steps 4 and 5 run
over each of them, because a checksum and a signature are claims about the bytes that will actually run —
so their grain is the bytes', not the entry's. An entry is all-or-nothing: one OS's asset failing rejects
the whole entry, since a listing that claims an OS it cannot serve is what the client refuses.

The signature is what an amenbo client verifies at install time against the catalog public key it ships
with. It does not say "the author signed this"; it says "these exact bytes went through this catalog's
review". That is the whole trust root, so it is produced here and nowhere else — authors never hold a key.

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
from datetime import datetime, timezone
from pathlib import Path

import yaml

#: The catalog file's own schema version. Bumped only when the *envelope* changes; entries evolve by
#: adding fields, which older clients ignore.
CATALOG_V = 1

#: GitHub owners whose plugins may carry `official: true` — i.e. the amenbo team. Official means the
#: author is the team; being listed here at all is a separate, weaker thing (review, not endorsement).
OFFICIAL_OWNERS = frozenset({"ShiroDoromoto"})

#: The manifest fields that are copied into a catalog entry verbatim. Deliberately a whitelist rather
#: than a pass-through: an entry stays small and predictable, and a manifest cannot inflate the one file
#: every client downloads. A field amenbo adds later is added here too.
#:
#: The distributable — `url` / `checksum` / `assets` — is deliberately *not* here: it is not copied but
#: rebuilt by [publish], which adds the signature only after fetching the bytes and checking their digest.
ENTRY_FIELDS = (
    "name",
    "desc",
    "author",
    "repo",
    "os",
    "category",
    "official",
    "payload_v",
    "min_amenbo",
    "config",
)

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


def check_manifest(amenbo: str, path: Path) -> None:
    """Run amenbo's validator over the manifest and re-raise every problem it reports."""
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
        problems = "; ".join(
            f"{p.get('location', '?')}: {p.get('message', '?')}" for p in report.get("problems", [])
        )
        raise Rejected(f"invalid manifest — {problems}")


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


def sign(data: bytes, label: str, key: Path, password: str, public_key: Path) -> str:
    """Sign the asset bytes with the catalog key and return the full minisign signature text.

    The signature is verified against the public key before it is returned: a signature this catalog
    cannot itself verify would fail on every user's machine, and it is far cheaper to learn that here.

    The bytes are signed under `label` so that minisign's trusted comment — which is signed too — names
    what was signed (the plugin, and its OS where there is one per OS) rather than a temporary file.
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
        verifying = subprocess.run(
            ["minisign", "-V", "-p", str(public_key), "-m", str(asset), "-x", str(signature)],
            capture_output=True,
            text=True,
        )
        if verifying.returncode != 0:
            raise Rejected(f"the signature did not verify against the catalog public key: {verifying.stderr.strip()}")
        return signature.read_text()


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


def publish(distributable: dict, label: str, args: argparse.Namespace) -> dict:
    """Fetch one distributable, check it against its declared digest, sign it, and return the catalog's
    copy of it — `url`, `checksum`, and the `signature` over the exact bytes served.

    `label` names the bytes in minisign's trusted comment, which is signed along with them. For a per-OS
    asset it carries the OS, so a signature says which distributable of a plugin it covers.
    """
    data = download(distributable["url"])
    check_checksum(data, distributable["checksum"])
    published = {"url": distributable["url"], "checksum": distributable["checksum"]}
    if args.sign_key:
        published["signature"] = sign(data, label, args.sign_key, args.sign_password, args.public_key)
    return published


def is_signed(entry: dict) -> bool:
    """Whether every distributable in a built entry carries a signature — what a run without a key lacks."""
    assets = entry.get("assets")
    if assets:
        return all("signature" in asset for asset in assets.values())
    return "signature" in entry


def build_entry(path: Path, args: argparse.Namespace) -> dict:
    """Run one manifest through every check and return the catalog entry, or raise [Rejected]."""
    try:
        manifest = yaml.safe_load(path.read_text())
    except yaml.YAMLError as e:
        raise Rejected(f"not readable as YAML: {e}")
    if not isinstance(manifest, dict):
        raise Rejected("a manifest must be a YAML mapping")

    check_manifest(args.amenbo, path)
    check_file_name(path, manifest)
    check_official(manifest)

    entry = {field: manifest[field] for field in ENTRY_FIELDS if field in manifest}
    entry.setdefault("official", False)

    # `assets` alone decides which of the two distributable forms is in play — the same rule the client's
    # install door reads, so an entry can never mean one thing here and another there. The validator above
    # has already established that whichever form this manifest uses is complete.
    assets = manifest.get("assets")
    if assets:
        published = {}
        for os_name, asset in sorted(assets.items()):
            try:
                published[os_name] = publish(asset, f"{entry['name']}-{os_name}", args)
            except Rejected as e:
                # *Which* distributable failed is an author's first question once an entry publishes
                # several, so name it where the validator names it — under `assets.<os>`.
                raise Rejected(f"assets.{os_name}: {e}")
        entry["assets"] = published
    else:
        entry.update(publish(manifest, entry["name"], args))

    first_seen = added_at(path)
    if first_seen:
        entry["added_at"] = first_seen
    return entry


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
    parser.add_argument("--out", type=Path, default=Path("catalog.json"), help="the catalog to write")
    parser.add_argument("--amenbo", default=os.environ.get("AMENBO_BIN", "amenbo"), help="the amenbo CLI to validate with")
    parser.add_argument("--sign-key", type=Path, help="the catalog signing key; without it, entries are unsigned")
    parser.add_argument("--public-key", type=Path, default=Path("catalog-key.pub"), help="the public half, to verify each signature")
    parser.add_argument("--strict", action="store_true", help="fail the run on any rejected manifest, rather than dropping it (a dry run before merging)")
    parser.add_argument("manifests", nargs="*", type=Path, help="the manifests to aggregate; default: every *.yaml under --plugins-dir")
    args = parser.parse_args()

    args.sign_password = os.environ.get("CATALOG_SIGNING_PRIVATE_KEY_PASSWORD", "")
    if args.sign_key and not args.sign_key.exists():
        print(f"error: signing key not found: {args.sign_key}", file=sys.stderr)
        return 1

    manifests = sorted(args.manifests) if args.manifests else sorted(args.plugins_dir.glob("*.yaml"))
    entries: list[dict] = []
    rejections: list[str] = []
    for path in manifests:
        try:
            entries.append(build_entry(path, args))
        except Rejected as e:
            rejections.append(f"{path}: {e}")

    lines = [f"## Catalog: {len(entries)} of {len(manifests)} manifests"]
    lines += [
        f"- ok: `{e['name']}`"
        + (f" ({', '.join(e['assets'])})" if "assets" in e else "")
        + ("" if is_signed(e) else " (unsigned)")
        for e in entries
    ]
    lines += [f"- **rejected** {r}" for r in rejections]
    report(lines)

    if rejections and args.strict:
        print("error: a manifest was rejected (strict)", file=sys.stderr)
        return 1
    # Publishing a catalog where nothing survived would replace a good catalog with an empty one. That is
    # a systemic failure (the network, the validator, the key), not a plugin going away.
    if manifests and not entries:
        print("error: every manifest was rejected — refusing to publish an empty catalog", file=sys.stderr)
        return 1

    catalog = {
        "catalog_v": CATALOG_V,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": entries,
    }
    args.out.write_text(json.dumps(catalog, indent=2, ensure_ascii=False, sort_keys=True) + "\n")
    print(f"wrote {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
