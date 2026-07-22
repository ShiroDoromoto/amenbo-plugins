# amenbo-plugins

The public plugin catalog for [**amenbo**](https://github.com/ShiroDoromoto/amenbo) — a local-first
task & project manager where an AI and a human collaborate on one machine.

Each plugin is one manifest under [`plugins/`](plugins/): a small YAML file describing the plugin well
enough to **list it, judge it, and fetch it** — without any central server. Add yours by opening a pull
request (see **[CONTRIBUTING.md](CONTRIBUTING.md)**).

## How the catalog works

amenbo has no server. Discovery is served entirely from static files and from GitHub's own numbers:

- The reviewed manifests in `plugins/` are aggregated into a single `catalog.json` and served statically.
- amenbo's in-app plugin browser fetches that **one file once**, then filters, searches, sorts, and pages
  it **locally** — it never queries GitHub once per plugin.
- Heavy signals (stars, download counts, README) are fetched **lazily**, only for the one plugin a user
  opens — never for the whole catalog.

This keeps browsing fast and offline-friendly no matter how many plugins the catalog holds: what grows is
the number of manifests, and the client already holds them all after one fetch.

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
  local file. amenbo takes no position on those.

## Getting listed

Open a PR that adds a single `plugins/<name>.yaml`. The full field reference, an example, and the review
checklist are in **[CONTRIBUTING.md](CONTRIBUTING.md)**.

## License

The catalog tooling and docs in this repository are licensed under [Apache-2.0](LICENSE). Each listed
plugin is licensed by its own author under its own terms, in its own source repository.
