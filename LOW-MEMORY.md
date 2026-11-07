# Pagefind 1.5.2: bounded finalization

This branch is based on upstream tag `v1.5.2` (commit
`bf17396721be637cc67c8ed7ead1dc7b8ac43d96`). It provides a Rust-library build
with the original 1.5.2 JavaScript and WASM resources already present, so consuming
projects do not need Node.js or an asset-generation step.

The bundled resources are copied without modification from the published
`pagefind` 1.5.2 crate, SHA-256
`aa7d3c661e0e18b6c9eec1305908baf2bd9564af247727f9e7f4b4d25cd2da39`.
The Rust source in that crate matches the upstream tag. The crate version is set
to 1.5.2 so the embedded resource filenames resolve correctly. Upstream's MIT
license is retained.
The Tokio `io-util` feature is declared explicitly so the library also builds
standalone with default features disabled, without relying on a caller to enable it.
`PREBUILT-SHA256.json` records every resource hash; verify it with
`python scripts/verify_prebuilt.py`.

## Allocation changes

- `PagefindIndex::into_files(self)` finalizes a disposable index, moving parsed
  pages into the build instead of cloning the complete corpus.
- The existing reusable `get_files(&mut self)` API retains its input and remains
  available for callers that append records or rebuild an index.
- Word maps are converted and merged one page at a time, rather than collecting
  temporary word maps for every page before merging them.

The index encoding, page order, text weighting, metadata, filters and browser
resources are unchanged. `pagefind/tests/consuming.rs` compares complete bundle
bytes for synthetic weighted HTML, diacritics, exclusions and custom records.

```sh
cargo test -p pagefind --no-default-features --lib --test consuming
```

For an application dependency, pin this repository to a full commit SHA using
Cargo's `git` and `rev` fields. Keep the consuming project's lockfile committed
and use `--locked` in CI. This branch is a maintained patch, not an upstream
Pagefind release.
