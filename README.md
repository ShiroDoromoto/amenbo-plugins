# amenbo-plugins

The public plugin catalog for [**amenbo**](https://github.com/ShiroDoromoto/amenbo) — a local-first
task & project manager where an AI and a human collaborate on one machine.

**Documentation** — the contracts an author is held to, in English and Japanese:

| | English | 日本語 |
|---|---|---|
| Writing a plugin | [`docs/writing-a-plugin.md`](docs/writing-a-plugin.md) | [`docs/writing-a-plugin.ja.md`](docs/writing-a-plugin.ja.md) |
| Carrying data outward | [`docs/carrying-data-outward.md`](docs/carrying-data-outward.md) | [`docs/carrying-data-outward.ja.md`](docs/carrying-data-outward.ja.md) |
| Running a catalog | [`docs/running-a-catalog.md`](docs/running-a-catalog.md) | [`docs/running-a-catalog.ja.md`](docs/running-a-catalog.ja.md) |

Each plugin is one manifest under [`plugins/`](plugins/): a small YAML file describing the plugin well
enough to **list it, judge it, and fetch it** — without any central server. Add yours by opening a pull
request (see **[CONTRIBUTING.md](CONTRIBUTING.md)**).

This repository is about **being listed**. Writing the plugin itself — the JSON amenbo hands it, what its
output means, the manifest fields, enabling, signatures — is
**[Writing a plugin](docs/writing-a-plugin.md)** ([日本語](docs/writing-a-plugin.ja.md)). That document is
the canon; what follows here is the catalog's side of it.

## How the catalog works

amenbo has no server. Discovery is served entirely from static files and from GitHub's own numbers:

- The reviewed manifests in `plugins/` are aggregated into a single `catalog.json` and served statically.
  It holds one small entry per plugin: what a list has to draw, and nothing an install needs.
- amenbo's in-app plugin browser fetches that **one file once**, then filters, searches, sorts, and pages
  it **locally** — it never queries GitHub once per plugin.
- What an install needs — the signature, the digests, the settings and events a plugin declares — is a
  second document per plugin, `plugins/<name>.json`, fetched **only** for the one plugin being opened or
  installed. A signature is the largest thing in a listing and the one thing nobody browsing needs.
- Heavy signals (stars, download counts, and the README of a plugin that wrote no `about` of its own) are
  fetched **lazily** the same way, only for the one plugin a user opens — never for the whole catalog.
- The lines a **person** reads — a plugin's `desc`, its `about`, and the labels on its settings form — are
  published in whatever languages its author wrote them in. The `desc` lines go into a `catalog.<lang>.json`
  beside the listing, so a reader fetches their own language and not the other eighteen; the `about` and the
  form labels ride inside `plugins/<name>.json`, all languages at once, so an opened plugin's description
  comes out of the document that was already fetched to open it, and an installed plugin's settings follow
  the reader's language with no network at all.

This keeps browsing fast and offline-friendly no matter how many plugins the catalog holds: what grows is
the number of manifests, and the client already holds every listing after one fetch.

The catalog is served at:

```
https://shirodoromoto.github.io/amenbo-plugins/catalog.json
https://shirodoromoto.github.io/amenbo-plugins/catalog.<lang>.json
https://shirodoromoto.github.io/amenbo-plugins/plugins/<name>.json
```

Each entry carries a `detail_sum` — the digest of its detail document — so a client can tell that a plugin
has a different build from the list fetch it already makes, without opening every detail to find out.

A language nobody has translated a listing into has no document, and the 404 that fetching it gets is the
answer rather than an error.

All of them are rebuilt by [`.github/workflows/catalog.yml`](.github/workflows/catalog.yml) on every push to
`main` and published to GitHub Pages — no server, just static files. Nothing is committed back to the
repository: `plugins/` stays the reviewed truth, and everything served is derived from it every time.

## Signatures — what a merge into this catalog means

Every asset in the catalog is signed by the catalog's CI, and amenbo verifies that signature (plus the
declared SHA-256) before it will install anything.

- **Authors hold no keys and sign nothing.** The private key exists only as a secret of this repository's
  CI; the public half is [`catalog-key.pub`](catalog-key.pub), which ships inside amenbo.
- **The signature says the bytes went through this catalog** — reviewed, downloaded, digest-checked — not
  that the author personally vouched for them. That is the same shape as trusting a Homebrew maintainer's
  review of a formula rather than the upstream author's signature.
- **Signing happens at merge, never on a pull request.** A submitter's branch never runs with the key.

An asset outside this catalog carries no signature of *ours*, which is the **free** tier's trade: you may
point amenbo at any catalog, and this repository vouches for nothing you point it at. It is still signed
and verified — against the key that catalog publishes, which its users are shown and agree to when they
register it. Running one is **[Running a catalog](docs/running-a-catalog.md)**
([日本語](docs/running-a-catalog.ja.md)): three static files, no server, and a key of your own.

## Trust tiers — *official* is not the same as *listed*

| Tier | Who builds it | How | Label |
|---|---|---|---|
| **Official** | the amenbo team | built by the team and curated into this catalog | official badge (`official: true`) |
| **Listed (reviewed)** | anyone | manifest opened as a PR here, reviewed, and merged | listed / reviewed (**not** official; `official: false`) |
| **Free** | anyone | your own catalog URL / manifest URL / a local file | not involved with this catalog |

- **Official** and **listed** are different axes. *Official* means the author is the amenbo team; *listed*
  means the manifest lives in this catalog. Every official plugin is also listed.
- **`official` is decided by curation here, never self-declared.** A pull request setting `official: true`
  on a third-party plugin will not be merged with that flag.
- The **free** tier needs nothing from this repository: point amenbo at any manifest or catalog URL, or a
  local file. This catalog takes no position on those; what stands behind a registered catalog is the key
  that catalog publishes, not ours.

### Featured — a third axis, and not a tier

amenbo's plugin browser leads with a **featured** view: the plugins this catalog recommends. That is a
separate question from both of the above — a listed third-party plugin can be featured, and an official
one need not be.

It is curated by hand in [`featured.txt`](featured.txt), one plugin name per line, and nowhere else. There
is no manifest field for it and a submission cannot ask for it: `official` can sit in a manifest because
it is a fact about authorship that the review can check, while being recommended is a judgement about the
plugin, which nothing in a pull request could establish. Changing what is featured is this catalog's own
act, and arrives as its own diff.

The list is a set, not a ranking — it says which plugins are recommended, and leaves their order to the
client. amenbo also ignores the flag on any catalog but this one, so a third-party catalog cannot
recommend its own entries into that view.

## Getting listed

Open a PR that adds a single `plugins/<name>.yaml`. The full field reference, an example, and the review
checklist are in **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## License

The catalog tooling and docs in this repository are licensed under [Apache-2.0](LICENSE). Each listed
plugin is licensed by its own author under its own terms, in its own source repository.
