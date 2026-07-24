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

…plus **the distributable**, in one of the two forms below.

### The distributable: one for everything, or one per OS

A plugin that is a single file everywhere — a script — publishes one asset with `url` and `checksum`:

| Field | Type | Meaning |
|---|---|---|
| `url` | string | Where the plugin asset is fetched from on install. Must be `https://`. |
| `checksum` | string | The asset's integrity digest, e.g. `sha256:…`, verified on download against what `url` served. A third-party plugin additionally requires a minisign signature at install time. |

A plugin built per platform — a native binary — cannot: three OSes are three different files, and the name
is the identity, so it cannot be split into three listings either. It publishes **one asset per OS**
instead, under `assets`:

| Field | Type | Meaning |
|---|---|---|
| `assets` | map | One `{ url, checksum }` per OS, keyed exactly as `os` spells them. Each entry means the same as the `url` / `checksum` above, for the bytes served on that OS. |

The keys of `assets` and the entries of `os` must answer for the same platforms — no OS claimed with
nothing to serve there, and nothing served for an OS the plugin does not claim.

Write **one** of the two. Where a manifest has both, `assets` is what answers, on the client and here; the
single-`url` form stays valid and is not deprecated.

### Optional

| Field | Type | Default | Meaning |
|---|---|---|---|
| `official` | bool | `false` | The official badge (author is the amenbo team). **Catalog-authoritative** — a PR self-declaring this on a third-party plugin will be asked to drop it. |
| `scope` | string | `project` | Which switch enables the plugin: `project` (each project answers for itself) or `machine` (one answer for the device). Declare `machine` only when a per-project answer would mean nothing for your plugin — a user is never shown both. |
| `payload_v` | integer | `1` | The event-payload contract version the plugin reads. Absent means the v1 baseline. |
| `min_amenbo` | string | none | Minimum amenbo version the plugin needs, as semver — below it, amenbo warns or refuses to enable/run it. |
| `config` | list | none | The plugin's configuration schema: a flat list of fields amenbo renders as a form and injects at run time. |
| `events` | list | none | The events your plugin's hook fires on. Absent means it observes nothing — a command-only plugin. |

An `events` entry is either the event's name, or an object narrowing where it fires:

```yaml
events:
  - task.done                  # both faces, no reply — the notification default
  - event: task.status_changed
    faces: [cli]               # cli / gui; must be non-empty
    reply: true                # relay the hook's output back to the caller; only with faces: [cli]
```

Unknown keys are ignored rather than rejected, so a manifest written for a newer amenbo still parses on an
older one. The catalog entry is built from the manifest amenbo itself reads, so every field amenbo knows
about is carried into the entry your plugin installs from — none is quietly dropped for the aggregator to
catch up with later.

## Example

A complete example — copy it, then replace every value with your plugin's. This one is a native plugin,
so it publishes one asset per OS:

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
assets:
  macos:
    url: https://github.com/ShiroDoromoto/amenbo-plugin-worktree/releases/download/v1/worktree-v1-macos.tar.gz
    checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
  linux:
    url: https://github.com/ShiroDoromoto/amenbo-plugin-worktree/releases/download/v1/worktree-v1-linux.tar.gz
    checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
# official: true   # set by catalog curation, not by submitters
```

A plugin that is one file on every OS it lists writes the single form in place of `assets`:

```yaml
url: https://github.com/you/your-plugin/releases/download/v1/your-plugin-v1.tar.gz
checksum: sha256:0000000000000000000000000000000000000000000000000000000000000000
```

> Every `url` and `checksum` above is a placeholder. Point each `url` at a real release asset and set its
> `checksum` to that asset's real digest — the digest is verified on download, so a wrong one fails the
> install.

A ready-to-edit copy of this example lives at [`manifest.example.yaml`](manifest.example.yaml).

## Checklist before you open the PR

- [ ] The file is `plugins/<name>.yaml`, and `<name>` matches the manifest's `name`.
- [ ] All required fields are present and `os` is non-empty.
- [ ] You wrote **one** distributable form: either `url` + `checksum`, or `assets`.
- [ ] Using `assets`: it has an entry for every OS in `os`, and no entry for an OS that is not in it.
- [ ] Every `url` points at a real, downloadable release asset, and its `checksum` is that asset's real digest.
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

Your pull request then goes through the catalog build itself, over the manifest you submitted, as a dry
run: the file name must match the manifest's `name`, `official: true` is refused from anyone outside the
amenbo team, and **every asset you publish is downloaded and hashed** — bytes that do not match the
`checksum` beside them fail the check, before the merge rather than after it. With `assets`, that is once
per OS, and the failure names which one (`assets.linux: …`). Already-listed entries are not re-fetched, so
someone else's asset going offline never blocks your PR.

**On the merge**, the catalog build ([`catalog.yml`](.github/workflows/catalog.yml)) runs all of that
again over every listed manifest, and then does what only it can:

- **signs each of your assets with the catalog key** — one signature per set of bytes, stored beside the
  `checksum` it belongs to — and publishes the aggregated `catalog.json` to GitHub Pages, where every
  amenbo picks it up;
- **drops** an entry whose checks now fail — a `url` that has rotted since it was merged, say — with the
  reason in the workflow summary, rather than holding the whole catalog back.

You never handle a key — see [Signatures](README.md#signatures--what-a-merge-into-this-catalog-means) for
why the catalog signs rather than the author.

Three consequences worth knowing:

- **Changing the asset behind a released `url` breaks the listing.** The digest and the signature are over
  the exact bytes; publish a new asset at a new URL and open a PR updating `url` and `checksum`.
- **A URL that stops resolving drops your entry** from the next catalog build. Everything else stays
  listed.
- **An entry is all-or-nothing.** One OS's asset failing drops the whole listing, not that one OS — a
  listing that claims an OS it cannot serve is exactly what amenbo refuses to install.
