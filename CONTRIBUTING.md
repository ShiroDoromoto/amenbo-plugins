# Contributing a plugin

To list a plugin, open a pull request that adds **one** file: `plugins/<name>.yaml`. One manifest, one
plugin, one file named for the plugin.

Listing is review, not endorsement: a merged PR means the manifest is well-formed and the plugin looked
reasonable — it does **not** make the plugin *official* (see the trust tiers in the
[README](README.md#trust-tiers--official-is-not-the-same-as-listed)).

## The manifest

A manifest is a small YAML file. Required fields must be present; optional fields have safe defaults, so a
manifest may omit them.

### Required

| Field | Type | Meaning |
|---|---|---|
| `name` | string | The plugin's identity in the catalog and its file name under `plugins/`. Cannot be the reserved name `registry`. |
| `desc` | string | One-line description, shown in the list view. |
| `author` | string | Who wrote the plugin. Display text — it does **not** grant the official badge. |
| `repo` | string | Source repository as `owner/name`. A detail view reads stars and README from it, lazily. |
| `os` | list | Operating systems the plugin runs on: any of `macos`, `windows`, `linux`. Must be non-empty. |
| `category` | string | A label for filtering (e.g. `workflow`). A free label — the catalog curates the vocabulary. |
| `url` | string | Where the plugin asset is fetched from on install. |
| `checksum` | string | The asset's integrity digest, e.g. `sha256:…`, verified on download against what `url` served. A third-party plugin additionally requires a minisign signature at install time. |

### Optional

| Field | Type | Default | Meaning |
|---|---|---|---|
| `official` | bool | `false` | The official badge (author is the amenbo team). **Catalog-authoritative** — a PR self-declaring this on a third-party plugin will be asked to drop it. |
| `payload_v` | integer | `1` | The event-payload contract version the plugin reads. Absent means the v1 baseline. |
| `min_amenbo` | string | none | Minimum amenbo version the plugin needs, as semver — below it, amenbo warns or refuses to enable/run it. |
| `config` | list | none | The plugin's configuration schema: a flat list of fields amenbo renders as a form and injects at run time. |

Unknown keys are ignored rather than rejected, so a manifest written for a newer amenbo still parses on an
older one.

## Example

A complete example — copy it, then replace every value with your plugin's:

```yaml
# plugins/worktree.yaml
name: worktree
desc: Isolate each task in its own git worktree
author: amenbo
repo: ShiroDoromoto/amenbo-plugin-worktree
os:
  - macos
  - linux
category: workflow
url: https://github.com/ShiroDoromoto/amenbo-plugin-worktree/releases/download/v1/worktree-v1.tar.gz
checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
# official: true   # set by catalog curation, not by submitters
```

> The `url` and `checksum` above are placeholders. Point `url` at a real release asset and set `checksum`
> to that asset's real digest — the digest is verified on download, so a wrong one fails the install.

A ready-to-edit copy of this example lives at [`manifest.example.yaml`](manifest.example.yaml).

## Checklist before you open the PR

- [ ] The file is `plugins/<name>.yaml`, and `<name>` matches the manifest's `name`.
- [ ] All required fields are present and `os` is non-empty.
- [ ] `url` points at a real, downloadable release asset, and `checksum` is that asset's real digest.
- [ ] `repo` is the plugin's own `owner/name`, not this catalog.
- [ ] You did **not** set `official: true` (unless you are the amenbo team).

## What CI checks

**On your pull request**, your manifest is checked with **amenbo's own validator** — the very same one
amenbo runs at its install door, so the catalog and the client can never disagree about what "valid"
means. You can run it yourself first, with any amenbo that has the plugin commands:

```sh
amenbo plugin validate plugins/<name>.yaml
```

It prints every problem it finds at once, and exits non-zero if there are any.

**On the merge**, the catalog build ([`catalog.yml`](.github/workflows/catalog.yml)) re-runs that
validation and then does what only it can:

- **checks the file name** matches the manifest's `name`;
- **refuses `official: true`** from anyone outside the amenbo team;
- **downloads your `url` and hashes it** — if the bytes do not match your `checksum`, the entry is dropped
  with the reason in the workflow summary;
- **signs your asset with the catalog key** and publishes the aggregated `catalog.json` to GitHub Pages,
  where every amenbo picks it up.

You never handle a key — see [Signatures](README.md#signatures--what-a-merge-into-this-catalog-means) for
why the catalog signs rather than the author.

Two consequences worth knowing:

- **Changing the asset behind a released `url` breaks the listing.** The digest and the signature are over
  the exact bytes; publish a new asset at a new URL and open a PR updating `url` and `checksum`.
- **A URL that stops resolving drops your entry** from the next catalog build. Everything else stays
  listed.
