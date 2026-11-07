# Linux release finalization benchmarks

Candidate: `codex/upstream-low-memory`, based on upstream `1e288eaabee84c593da0a77e106aa1ed84d864cc`.

This compares the unchanged upstream algorithm, consuming finalization alone, bounded parallel batching alone, both changes together, and consuming finalization with the sequential conversion used in the 1.5.2 fork. The proposed upstream patch preserves parallel conversion.

## Method

- Ubuntu 22.04 under WSL2, x86_64 GNU/glibc 2.35; Rust 1.99.0.
- Unmodified upstream release profile: `opt-level = "s"`, LTO enabled, stripping enabled.
- All variants share the same frozen benchmark lockfile and 47 verified published 1.6.0 browser resources. Package version is set to 1.6.0 only in the disposable benchmark checkout so resource filenames resolve. No generated assets or version changes belong to the proposed patch.
- The frozen lockfile resolves the current upstream requirement for html-escape 0.3.0; the checked-in upstream lockfile still contained 0.2.13. Every variant uses exactly the same resolution.
- Deterministic synthetic HTML and custom records, 512 generated vocabulary tokens per record, metadata, weighted headings, diacritics, filters, sorts and ignored content. No application data is used.
- 1,000 records (4,943,224 content bytes) and 8,000 records (39,558,224 content bytes).
- CPU affinity and Rayon thread count both fixed to one or four CPUs. Three repetitions per configuration, interleaved using a fixed random seed; 60 measured processes total.
- GNU time maximum resident set size covers ingestion, finalization and bundle hashing. Finalization time is measured separately; wall time covers the complete process.
- Timings varied under WSL. These are workload-specific medians, not a general speedup claim or a benchmark of the published musl/jemalloc binary.

## Proposed patch versus upstream

| Records | Threads | Upstream peak MiB | Combined peak MiB | RSS reduction | Upstream wall s | Combined wall s |
| ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| 1,000 | 1 | 490.4 | 240.7 | 50.9% | 1.612 | 1.715 |
| 1,000 | 4 | 478.5 | 226.1 | 52.8% | 1.663 | 1.865 |
| 8,000 | 1 | 3,615.0 | 1,600.2 | 55.7% | 13.851 | 13.857 |
| 8,000 | 4 | 3,651.5 | 1,573.9 | 56.9% | 20.351 | 12.037 |

The 1,000-record full-process wall medians were about 6% (one thread) and 12% (four threads) higher with the combined patch. Ingestion and finalization timings varied between repetitions. The small-input results are retained above and in the raw data; the four-thread large-corpus timing improvement should not be generalized to every site.

## Isolated changes: 8,000 records

| Threads | Variant | Median peak MiB | Median finalize s | Finalize range s | Median wall s |
| ---: | --- | ---: | ---: | ---: | ---: |
| 1 | upstream | 3,615.0 | 9.661 | 8.918 to 10.374 | 13.851 |
| 1 | consume-only | 3,209.3 | 8.072 | 7.558 to 10.165 | 11.731 |
| 1 | bounded-only | 2,018.7 | 8.575 | 7.590 to 9.256 | 11.427 |
| 1 | combined | 1,600.2 | 9.277 | 5.893 to 10.472 | 13.857 |
| 1 | sequential | 1,266.1 | 7.270 | 5.870 to 9.374 | 10.317 |
| 4 | upstream | 3,651.5 | 14.975 | 11.358 to 18.620 | 20.351 |
| 4 | consume-only | 3,271.8 | 11.898 | 11.358 to 12.191 | 16.661 |
| 4 | bounded-only | 1,986.8 | 9.512 | 7.781 to 11.636 | 15.359 |
| 4 | combined | 1,573.9 | 7.947 | 6.510 to 8.105 | 12.037 |
| 4 | sequential | 1,164.4 | 7.973 | 5.320 to 10.069 | 13.797 |

## Output parity

All 60 measured runs produced byte-identical bundles for their corpus size, across every algorithm, API mode, thread count and repetition. The 8,000-record corpus produced 8,630 files. Five additional runs on a 257-record, three-language corpus also produced byte-identical bundles.

## Reproduction

Prerequisites: Linux with at least four available CPUs, enough RAM for the baseline (about 4 GiB peak in these runs; 8 GiB or more available is recommended), Python with safe tar extraction support, Git, GNU time at `/usr/bin/time`, a C build toolchain, and Rust 1.99.0 installed through rustup.

From a checkout of this fork containing both source commits:

```sh
rustup toolchain install 1.99.0 --profile minimal
python3 benchmarks/finalization/reproduce.py --repository . \
  --candidate e24aa211006ec0a20e30d96c367148d953af607a \
  --workdir /tmp/pagefind-finalization-bench
```

The work directory must be empty. The script builds four matched release binaries and runs all five algorithm/API cases. It downloads the official 1.6.0 crate and checks its SHA-256 before using its resources. It leaves the source checkout unchanged. All generated reports go under the work directory.

For a quick harness/parity check instead of measurements:

```sh
python3 benchmarks/finalization/reproduce.py --repository . \
  --candidate e24aa211006ec0a20e30d96c367148d953af607a \
  --workdir /tmp/pagefind-finalization-smoke --records 64 --repetitions 1
```

The runner caps each measured process at 240 seconds and monitors an 8 GiB resident-memory guard. It does not impose a virtual-address limit, because allocator address reservations do not represent resident RAM.

Raw runs, summaries, environment metadata and the frozen lockfile accompany this report.

## Validation of the proposed patch

- Rust release tests: 43 existing unit tests plus four new consuming/reuse/output-parity tests, with default features disabled and `tokio/io-util` enabled explicitly.
- Default-feature release unit tests: 43 passed.
- Extended-feature release tests: 43 unit tests plus all four new tests passed.
- WebAssembly crate's native release tests: four passed.
- JavaScript tests: 21 passed.
- Toolproof browser/CLI/API integration tests: **345 passed**, zero failures, zero changed snapshots and zero retries. Current upstream Default and Component UI assets were built for this suite because its image-URL snapshots include fixes newer than the published 1.6.0 resources.
- Portable reproduction package smoke check: ten release processes and five multilingual parity processes passed against the exact proposed patch commit.

Stock Clippy 1.99 fails on both unchanged upstream and the candidate for the same two existing denied lints: `clippy::unused_io_amount` in `pagefind/src/service/mod.rs` and `clippy::erasing_op` in `pagefind/src/fossick/mod.rs`. Neither file is changed by the patch. The candidate completes Clippy when allowing exactly those two inherited lints; other existing warnings remain. No unrelated lint fixes are included. See `clippy-audit.json` and `validation.json`.
