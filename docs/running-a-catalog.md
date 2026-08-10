# Running a catalog

English · [日本語](running-a-catalog.ja.md)

An amenbo plugin catalog is **three static files** — plus one small one per language, once your plugins are
described in more than one. There is no server to run. The most common reason to stand one up is a closed
shelf: plugins you have no intention of publishing, handed to people inside your own company.

This document is for whoever is **running the catalog**. Writing the plugins themselves is
[Writing a plugin](writing-a-plugin.md).

> Registering a third-party catalog is available from amenbo 2.0.0. Check whether
> `amenbo plugin catalog --help` answers on your machine.

## What your users see

A user registers you by the URL of your `catalog.json`.

```sh
amenbo plugin catalog add https://plugins.example.com/catalog.json --name "Example Corp"
```

amenbo fetches the `catalog-key.pub` sitting beside it, **shows the fingerprint, takes the user's consent,
and pins that key**. From then on, a plugin installed from your catalog is verified against **that key**
and nothing else.

```
https://plugins.example.com/catalog.json publishes a signing key:
  fingerprint 2F09ABE300368325
  Plugins installed from this catalog will be trusted on this key.
```

So registering you is not a bookmark — it adds **one more root of trust**. A catalog that publishes no key
can still be registered, but it can only be browsed: nothing on it installs.

## The files

They sit in one directory. amenbo derives every one of them from the URL of `catalog.json`.

| File | What is in it | Who fetches it, and when |
| --- | --- | --- |
| `catalog.json` | only what a list has to draw | everyone, once per browse (cached for an hour) |
| `plugins/<name>.json` | what an install needs: signature, checksum, settings, events | only the one plugin someone opens or installs |
| `catalog-key.pub` | the public half of your signing key | once, at registration |
| `catalog.<lang>.json` | the listing's descriptions in one language | everyone, once per browse (cached for an hour) — their own language and no other |

The listing and the detail are separate because **the signature is the largest thing in a listing**.
Nobody who is only browsing should have to download every plugin's. The language documents are separate
from the listing for the same shape of reason: nineteen languages inside `catalog.json` would charge every
reader for the eighteen they cannot read.

## `catalog.json`

The envelope, and one entry per plugin.

```json
{
  "catalog_v": 1,
  "generated_at": "2026-07-27T03:38:10Z",
  "plugins": [
    {
      "name": "helloctl",
      "desc": "One command for the things we do every day",
      "author": "Example Corp",
      "repo": "example/helloctl",
      "os": ["macos"],
      "category": "workflow",
      "official": false,
      "featured": false,
      "added_at": null,
      "detail_sum": "sha256:5aa7ef29d87409ef9b83d6bc3998c18a67d843ca030381724207bb00e57ad0a9"
    }
  ]
}
```

- `catalog_v` versions the **envelope**, and is `1` today. amenbo refuses a catalog whose version it does
  not know, whole. Entries growing a field does not move it — an older amenbo skips keys it does not know.
- `generated_at` is optional.
- One broken entry is dropped **on its own**. The rest of the catalog stays usable.

**Which fields belong in the listing and which in the detail is not yours to decide.** `amenbo plugin
validate --json` hands the manifest back already split into `entry` and `detail`, and aggregation just
publishes the two. That way a field amenbo adds later rides through without a change on your side. A
translated field follows the base field it translates, so the same call answers with `entry_i18n` beside
them — the listing half, one entry per language.

Three values are the **catalog's own**. amenbo returns them empty, and aggregation fills them in.

| Field | How to fill it |
| --- | --- |
| `detail_sum` | the SHA-256 of the detail document you wrote (`sha256:<hex>`). **Required** — this is the only thing a user's amenbo compares to notice that a plugin has a different build |
| `added_at` | the day the plugin was listed. It is the "new" axis of the browser, and missing reads as unknown (git history is the natural source) |
| `featured` | your recommendation. Leave it `false` if you have no use for it |

`official` is **the amenbo team's badge**. Do not set it on your entries.

## `catalog.<lang>.json`

One document per language, beside `catalog.json` — the listing's `desc` lines, and nothing else, keyed by
plugin name.

```json
{
  "helloctl": { "desc": "毎日やることを、ひとつのコマンドに" }
}
```

- **The names are the ones in your listing.** A plugin missing from the document is a plugin nobody
  translated, and its English line is what its row draws. Neither the row nor the reader is told that it
  fell back.
- **Only publish a language somebody translated something into.** An empty document says nothing the 404
  does not already say. **A 404 is a normal answer** here — it reads as *not translated yet*, and it is not
  an error on the client or in your logs. There is no index of which languages you have, either.
- **`catalog.json` is untouched.** Its `desc` stays the language your authors wrote it in, which is where
  every language falls back to.
- The form labels are not here. They ride inside `plugins/<name>.json`, every language at once, so an
  installed plugin's settings follow the reader with no network — see
  [Writing a plugin](writing-a-plugin.md#writing-it-in-other-languages) for what an author writes.

The **placement is what makes this work for you at all**. amenbo resolves a language document the same way
it resolves a detail document: the same base URL as the `catalog.json` a user registered, with the language
in the name. Nothing about it is special-cased for the official catalog.

## `plugins/<name>.json`

What an install needs. `name` is the only field in both documents — it is the join between them.

```json
{
  "name": "helloctl",
  "url": "https://github.com/example/helloctl/releases/download/v1/helloctl-v1.tar.gz",
  "checksum": "sha256:e23f6791e6852331a4c4bf147e86d57e6088dcbffbf936f56ade7df8c0ca6d8f",
  "signature": "untrusted comment: signature from minisign secret key\nRUQlgzYA…\n",
  "payload_v": 1
}
```

`signature` is a minisign signature over **the bytes the URL actually served**. You do not sign the
checksum a manifest declared — you **download, compare, and sign those bytes**. For a plugin built per
platform, the same happens once per key under `assets`.

A distributable's `url` must be **https** (`amenbo plugin validate` refuses anything else at the door).
The URL of `catalog.json` itself may be http, which is what makes a local rehearsal possible.

## Making the key

**Your CI signs, not amenbo.** amenbo has no surface that touches a private key.

```sh
minisign -G -p catalog-key.pub -s catalog.key
```

- Put the **public half** (`catalog-key.pub`) beside your `catalog.json`.
- Put the **private key** (`catalog.key`) in a CI secret. A secret takes text, so wrap it:
  `base64 -i catalog.key`. Keep the password in a second secret.
- The **fingerprint** is the 16 hex digits minisign writes into the comment line of `catalog-key.pub`
  (`untrusted comment: minisign public key 2F09ABE300368325`). That string is what a user is shown while
  consenting, so **publish it too** — on your download page, in your README — and they can compare.

## The aggregation script

The smallest thing that reads `plugins/*.yaml` and writes the files into `_site/`. Its only dependencies
are amenbo and minisign, and it publishes what `amenbo plugin validate --json` returned. This repository's
own [`scripts/aggregate.py`](../scripts/aggregate.py) is the same script grown up — a curation list, a
carried-over signature, a job summary — and it is worth reading once you outgrow this one.

```python
#!/usr/bin/env python3
"""Build a signed amenbo plugin catalog out of the manifests in plugins/."""

import argparse
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

CATALOG_V = 1


def documents(amenbo, manifest):
    """Hand the manifest to amenbo and take back the documents it splits into.

    Which field belongs in which document is amenbo's answer, never this script's, so a
    field amenbo grows later rides through without a change here. The translations beside
    the manifest are read with it and come back split the same way: `entry_i18n` is the
    list half, one entry per language, and the detail half is already inside `detail`.
    """
    proc = subprocess.run(
        [amenbo, "--json", "plugin", "validate", str(manifest)],
        capture_output=True,
        text=True,
    )
    report = json.loads(proc.stdout or "{}")
    if not report.get("ok"):
        sys.exit(f"{manifest}: {proc.stdout.strip() or proc.stderr.strip()}")
    return report["entry"], report.get("entry_i18n") or {}, report["detail"]


def signed(distributable, label, key, password):
    """Download one distributable, check it against the digest the manifest declared, and
    sign those exact bytes with the catalog key."""
    with urllib.request.urlopen(distributable["url"], timeout=60) as response:
        data = response.read()
    digest = "sha256:" + hashlib.sha256(data).hexdigest()
    if digest != distributable["checksum"]:
        sys.exit(f"{label}: the url serves {digest}, not the declared {distributable['checksum']}")
    with tempfile.TemporaryDirectory() as tmp:
        asset, signature = Path(tmp) / label, Path(tmp) / f"{label}.minisig"
        asset.write_bytes(data)
        subprocess.run(
            ["minisign", "-S", "-s", str(key), "-m", str(asset), "-x", str(signature)],
            input=f"{password}\n",
            text=True,
            capture_output=True,
            check=True,
        )
        return {"url": distributable["url"], "checksum": digest, "signature": signature.read_text()}


def encode(document):
    """One rendering for both files, so detail_sum is the digest of exactly the bytes written."""
    return json.dumps(document, indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--plugins-dir", type=Path, default=Path("plugins"))
    parser.add_argument("--out", type=Path, default=Path("_site"))
    parser.add_argument("--key", type=Path, required=True, help="the minisign secret key to sign with")
    parser.add_argument("--amenbo", default=os.environ.get("AMENBO_BIN", "amenbo"))
    args = parser.parse_args()
    password = os.environ.get("CATALOG_KEY_PASSWORD", "")

    (args.out / "plugins").mkdir(parents=True, exist_ok=True)
    entries = []
    # The listing's desc lines per language, keyed by plugin name — written out at the end,
    # once every plugin has contributed whatever languages its author wrote.
    languages = {}
    for manifest in sorted(args.plugins_dir.glob("*.yaml")):
        # A translation is not a manifest: `mail.ja.yaml` is read with `mail.yaml`, not on its
        # own. A plugin's name holds no dot, so a dot left in the stem is the language.
        if "." in manifest.stem:
            continue
        entry, entry_i18n, detail = documents(args.amenbo, manifest)
        # The official badge belongs to the amenbo team's own catalog. Yours grants none.
        entry["official"] = False
        if detail.get("assets"):
            detail["assets"] = {
                platform: signed(asset, f"{entry['name']}-{platform}", args.key, password)
                for platform, asset in sorted(detail["assets"].items())
            }
        else:
            detail.update(signed(detail, entry["name"], args.key, password))
        text = encode(detail)
        (args.out / "plugins" / f"{entry['name']}.json").write_text(text)
        # The digest of the detail document as written: what tells a client this build moved.
        entry["detail_sum"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
        for lang, line in entry_i18n.items():
            languages.setdefault(lang, {})[entry["name"]] = line
        entries.append(entry)
        print(f"ok {entry['name']}")

    catalog = {
        "catalog_v": CATALOG_V,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "plugins": entries,
    }
    (args.out / "catalog.json").write_text(encode(catalog))
    # Only the languages somebody translated into. An empty document would answer nothing that
    # the 404 does not already answer.
    for lang, lines in sorted(languages.items()):
        (args.out / f"catalog.{lang}.json").write_text(encode(lines))
    print(f"wrote {args.out}/catalog.json with {len(entries)} plugin(s)")
    print(f"wrote {len(languages)} translated listing(s)")


if __name__ == "__main__":
    main()
```

It **stops on the first problem**. Once being listed matters more — when one rotted URL holding back the
whole catalog becomes the worse failure — change it to drop that one entry with a reason and carry on.

## Publish the same bytes twice

A minisign signature carries the moment it was made. Sign the same asset again and you get a different
signature, a different detail document, and a different `detail_sum` — which is the one thing a user's
amenbo compares to decide a plugin has a new build. A catalog that re-signs everything on every publish
therefore tells every user that every plugin was updated, every time anything at all was listed.

So **carry the signature over when the bytes have not changed**: before signing, read what you currently
publish for that plugin, and if the asset's digest is the one already published there, keep the signature
published with it. Verify it against your public key over the bytes you just downloaded — carrying one
over is a claim about those bytes, and a claim is worth checking. Anything that stops you (nothing
published yet, an asset that moved, a signature that no longer verifies) just means signing afresh, which
is what would have happened anyway.

What the signature says is that these bytes went through your review. It does not say when, so the one
made last time supports that exactly as well.

## GitHub Actions

Rebuild on every push to `main` and publish to GitHub Pages. **Sign on merge only** — never hand the
private key to a run a submitter can influence.

```yaml
name: catalog

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read

concurrency:
  group: catalog
  cancel-in-progress: false

jobs:
  build:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7

      # The manifest rules live in amenbo itself, so CI needs an amenbo too. `plugin validate`
      # is not in a released build yet, so this builds it from source.
      - uses: actions/checkout@v7
        with:
          repository: ShiroDoromoto/amenbo
          path: .amenbo-src
      - run: cargo build -p amenbo-cli
        working-directory: .amenbo-src

      - uses: actions/setup-python@v7
        with:
          python-version: "3.x"
      - run: sudo apt-get update && sudo apt-get install -y --no-install-recommends minisign

      - name: Build the catalog
        env:
          AMENBO_BIN: ${{ github.workspace }}/.amenbo-src/target/debug/amenbo
          CATALOG_SIGNING_KEY: ${{ secrets.CATALOG_SIGNING_KEY }}
          CATALOG_KEY_PASSWORD: ${{ secrets.CATALOG_KEY_PASSWORD }}
        run: |
          set -euo pipefail
          # The secret holds the private key base64-wrapped. RUNNER_TEMP goes away with the job.
          printf '%s' "$CATALOG_SIGNING_KEY" | base64 -d > "$RUNNER_TEMP/catalog.key"
          python3 scripts/build-catalog.py --key "$RUNNER_TEMP/catalog.key"
          cp catalog-key.pub _site/catalog-key.pub

      - uses: actions/upload-pages-artifact@v5
        with:
          path: _site

  publish:
    needs: build
    runs-on: ubuntu-latest
    permissions:
      pages: write
      id-token: write
    environment:
      name: github-pages
    steps:
      - uses: actions/configure-pages@v6
      - uses: actions/deploy-pages@v5
```

## A rehearsal on your own machine

Before you publish anything, walk the same path a user walks. The catalog itself may be http, so one
static server is enough.

```sh
python3 scripts/build-catalog.py --key catalog.key
cp catalog-key.pub _site/
(cd _site && python3 -m http.server 8765) &

amenbo plugin catalog add http://127.0.0.1:8765/catalog.json --name "Example Corp" --yes
amenbo plugin catalog list      # does the fingerprint match your catalog-key.pub?
amenbo plugin install <name>
```

`--yes` is how "I saw the fingerprint and I agree" is declared without a prompt. Leave it off and you get
the question.

## Rotating the key

**It costs your users a re-registration.** amenbo does not quietly accept a distributable signed by a key
other than the one pinned.

```
Error: https://plugins.example.com/catalog.json now publishes a different key
(32701CC140855BC6, pinned: 2F09ABE300368325). amenbo will not accept it on the old
consent — unregister the catalog and register it again to trust the new key.
```

`amenbo plugin catalog remove <url>`, then `add` again — that round trip is what puts the new fingerprint
**in front of the person deciding**. Which is why rotating a key is not a quiet piece of maintenance:
**announce the new fingerprint first.**

## What amenbo does not do

- **It ships no tool for building a catalog.** amenbo verifies; it has no surface that touches a private
  key. Nothing that runs on a user's machine gets the ability to sign.
- **It takes no part in keeping or revoking your key.** A pin only ever answers "is this the key that was
  registered?". That the key has not leaked is yours to guarantee.
- **The official badge stays the amenbo team's.** A plugin from your catalog shows up under **your
  catalog's name** — the one the user gave it when they registered you.
