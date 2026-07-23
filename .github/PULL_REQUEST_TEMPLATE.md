<!-- Adding a plugin? Confirm each box. See CONTRIBUTING.md for the field reference. -->

## Plugin

- **Name:**
- **Repo (`owner/name`):**

## Checklist

- [ ] This PR adds a single `plugins/<name>.yaml`, and `<name>` matches the manifest's `name`.
- [ ] All required fields are present (`name`, `desc`, `author`, `repo`, `os`, `category`) and `os` is non-empty.
- [ ] The distributable is written in exactly one form: `url` + `checksum`, or `assets` with an entry for every OS in `os` and no others.
- [ ] Every `url` points at a real, downloadable release asset, and its `checksum` is that asset's real digest.
- [ ] `repo` is the plugin's own repository, not this catalog.
- [ ] I did **not** set `official: true` (unless I am the amenbo team).

## Notes for reviewers

<!-- Anything the review should know: what the plugin does, why the OS set, etc. -->
