#!/usr/bin/env python3
"""Build and benchmark upstream, consuming-only, bounded and sequential variants."""

import argparse
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--repository", type=Path, default=Path.cwd())
parser.add_argument("--baseline", default="1e288eaabee84c593da0a77e106aa1ed84d864cc")
parser.add_argument("--candidate", default="origin/codex/upstream-low-memory")
parser.add_argument("--workdir", type=Path)
parser.add_argument("--records", type=int, nargs="+", default=[1000, 8000])
parser.add_argument("--repetitions", type=int, default=3)
args = parser.parse_args()
here = Path(__file__).resolve().parent
repository = args.repository.resolve()
resolve = lambda ref: subprocess.check_output(
    ["git", "rev-parse", ref], cwd=repository, text=True
).strip()
baseline = resolve(args.baseline)
candidate = resolve(args.candidate)
root = (
    args.workdir.resolve()
    if args.workdir
    else Path(tempfile.mkdtemp(prefix="pagefind-release-memory-"))
)
root.mkdir(exist_ok=True)
assert not any(root.iterdir()), "Use an empty work directory"
source = root / "src"
source.mkdir()
archive = subprocess.check_output(["git", "archive", baseline], cwd=repository)
with tarfile.open(fileobj=io.BytesIO(archive)) as contents:
    contents.extractall(
        source,
        members=[m for m in contents.getmembers() if m.isfile() or m.isdir()],
        filter="data",
    )
read = lambda ref, path: subprocess.check_output(
    ["git", "show", ref + ":" + path], cwd=repository
)
paths = ["lib.rs", "service/api.rs", "index/mod.rs"]
original = {name: read(baseline, "pagefind/src/" + name) for name in paths}
patched = {name: read(candidate, "pagefind/src/" + name) for name in paths}
serial = original["index/mod.rs"].decode()
start = serial.index(
    "    // Process pages in parallel - each page builds its own word map"
)
end = serial.index("\n    // Merge results sequentially", start)
loop = (
    serial[start:end]
    .replace(
        "let page_results: Vec<PageProcessingResult> = pages",
        "let page_results = pages",
        1,
    )
    .replace(".into_par_iter()", ".into_iter()", 1)
)
assert loop.endswith("        .collect();\n")
loop = loop[: -len("        .collect();\n")].rstrip() + ";\n"
serial = (serial[:start] + loop + serial[end:]).encode()
crate_url = "https://static.crates.io/crates/pagefind/pagefind-1.6.0.crate"
payload = urllib.request.urlopen(crate_url, timeout=90).read()
checksum = "5d9345b46c57402962ba0f02e8513d69ef24e14e068073d4d06f5bfdd8c437d0"
assert hashlib.sha256(payload).hexdigest() == checksum
count = 0
with tarfile.open(fileobj=io.BytesIO(payload), mode="r:gz") as contents:
    for member in contents.getmembers():
        if not member.isfile() or not member.name.startswith("pagefind-1.6.0/vendor/"):
            continue
        path = source / "pagefind" / Path(member.name).relative_to("pagefind-1.6.0")
        assert path.resolve().is_relative_to(source.resolve())
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(contents.extractfile(member).read())
        count += 1
assert count == 47
manifest = source / "pagefind/Cargo.toml"
text = manifest.read_text().replace('version = "0.0.0"', 'version = "1.6.0"', 1)
text = text.replace("[features]\n", "[features]\nconsuming_benchmark = []\n", 1)
text += '\n[dev-dependencies]\ntokio = { version = "1", features = ["io-util"] }\n'
manifest.write_text(text)
shutil.copyfile(here / "benchmark-Cargo.lock", source / "Cargo.lock")
examples = source / "pagefind/examples"
examples.mkdir(exist_ok=True)
shutil.copyfile(here / "memory_benchmark.rs", examples / "memory_benchmark.rs")
(root / "bin").mkdir()
(root / "results").mkdir()
(root / "report").mkdir()
variants = [
    ("upstream", original, False),
    ("consume-only", {**patched, "index/mod.rs": original["index/mod.rs"]}, True),
    ("bounded", patched, True),
    ("serial", {**patched, "index/mod.rs": serial}, True),
]
env = {**os.environ, "RUSTUP_TOOLCHAIN": "1.99.0"}
builds = []
for name, files, consuming in variants:
    for path, data in files.items():
        (source / "pagefind/src" / path).write_bytes(data)
    command = [
        "cargo",
        "build",
        "-p",
        "pagefind",
        "--release",
        "--no-default-features",
        "--example",
        "memory_benchmark",
        "--locked",
        "-j",
        "4",
    ]
    if consuming:
        command += ["--features", "consuming_benchmark"]
    print("Building " + name, flush=True)
    with (root / "report" / (name + "-build.log")).open("w") as log:
        subprocess.run(
            command,
            cwd=source,
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
            check=True,
        )
    destination = root / "bin" / name
    shutil.copyfile(source / "target/release/examples/memory_benchmark", destination)
    destination.chmod(0o755)
    builds.append(
        {
            "name": name,
            "source_sha256": {
                path: hashlib.sha256(data).hexdigest() for path, data in files.items()
            },
            "binary_sha256": hashlib.sha256(destination.read_bytes()).hexdigest(),
        }
    )
report = root / "report"
(report / "builds.json").write_text(json.dumps(builds, indent=2) + "\n")
(report / "base.json").write_text(
    json.dumps({"upstream_commit": baseline, "candidate_commit": candidate}, indent=2)
    + "\n"
)
(report / "linux-environment-preparation.json").write_text(
    json.dumps(
        {
            "assets_version": "1.6.0",
            "assets_count": 47,
            "assets_crate_sha256": checksum,
            "build_profile": {"opt-level": "s", "lto": True, "strip": True},
            "common_preparation": [
                "verified published browser assets",
                "package version 1.6.0",
                "benchmark example and feature",
                "dev-only tokio/io-util",
                "shared frozen benchmark lockfile",
            ],
        },
        indent=2,
    )
    + "\n"
)
subprocess.run(
    [
        "python3",
        str(here / "run_benchmarks.py"),
        "--workdir",
        str(root),
        "--output",
        str(report),
        "--records",
        *map(str, args.records),
        "--repetitions",
        str(args.repetitions),
    ],
    env=env,
    check=True,
)
print("Reports: " + str(report), flush=True)
