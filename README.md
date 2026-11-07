# Pagefind

Pagefind is a fully static search library that aims to perform well on large sites, while using as little of your users’ bandwidth as possible, and without hosting any infrastructure.

This fork contains a small Rust-library patch to [upstream Pagefind](https://github.com/Pagefind/pagefind)
**1.5.2**, on the default branch `low-memory-1.5.2`. It reduces peak memory when
finalizing a disposable index and includes the original prebuilt browser assets.
It is a maintained patch, not an official upstream release.

## What is different in this fork?

- **Consuming finalization:** the new `PagefindIndex::into_files(self)` API moves
  parsed pages into the index build instead of cloning the complete corpus. Use
  it when the index is finished and will not receive more records.
- **Smaller temporary allocations:** word maps are converted and merged one page
  at a time, rather than collecting temporary word maps for every page before
  merging them. This reduces peak memory during finalization.
- **Prebuilt assets included:** all 47 original JavaScript, CSS and WASM resources
  from the published Pagefind 1.5.2 crate are committed under `pagefind/vendor`.
  Rust-library consumers do not need Node.js or an asset-generation step.
- **Standalone library builds:** Tokio's `io-util` feature is declared explicitly,
  so building with default features disabled does not depend on a caller enabling it.
- **Regression and provenance checks:** tests compare the consuming and reusable
  APIs' complete output bundles. A SHA-256 inventory and verification script check
  the exact prebuilt assets.

The existing `get_files(&mut self)` API remains available for reusable indexes.
The browser resources, index format, text weighting, metadata and filter semantics
are unchanged. These changes reduce allocation peaks; the index still keeps its
parsed input and final output in memory.

In an application-level Windows stress test with 23,736 records and about 145 MB
of input, peak RSS fell from **1,775 MiB** with upstream 1.5.2 to **615 MiB** with
this fork's consuming API. Memory use depends on the corpus and build platform.

## Using the Rust library

Pin a tested full commit SHA and commit your Cargo lockfile. For example:

```toml
[dependencies.pagefind]
git = "https://github.com/swax/pagefind.git"
rev = "fc229efdba86538c173e382918f722fdc4642a99"
version = "=1.5.2"
default-features = false
```

After adding all pages, finalize a disposable index with
`index.into_files().await?` instead of `index.get_files().await?`. The consuming
method takes ownership of the index, so it cannot be reused afterward.

## Verification

Run from the repository root:

```sh
python scripts/verify_prebuilt.py
cargo test -p pagefind --no-default-features --lib --test consuming
```

See [LOW-MEMORY.md](LOW-MEMORY.md) for the upstream base commit, asset provenance
and patch details. General Pagefind documentation is available at
[pagefind.app](https://pagefind.app/). Upstream's MIT license is retained.
