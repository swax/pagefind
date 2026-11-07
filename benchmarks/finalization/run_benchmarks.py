"""Repeat matched Linux release benchmarks; report all runs, including output hashes."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import platform
import random
import signal
import statistics
import subprocess
import time

parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--workdir", type=Path, required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--records", type=int, nargs="+", default=[1000, 8000])
parser.add_argument("--repetitions", type=int, default=3)
args = parser.parse_args()
assert args.repetitions > 0 and all(n > 0 for n in args.records)
root = args.workdir.resolve()
evidence = args.output.resolve()
evidence.mkdir(parents=True, exist_ok=True)
results_dir = root / "results"
cases = [
    ("upstream", "upstream", "retain"),
    ("consume-only", "consume-only", "consume"),
    ("bounded-only", "bounded", "retain"),
    ("combined", "bounded", "consume"),
    ("sequential", "serial", "consume"),
]
affinity = sorted(os.sched_getaffinity(0))[:4]
assert len(affinity) == 4


def run(label, binary, mode, threads, records, repetition, languages=1):
    stem = f"{label}-t{threads}-n{records}-l{languages}-r{repetition}"
    log = results_dir / (stem + ".log")
    rss = results_dir / (stem + ".rss")
    manifest = results_dir / (stem + ".manifest.json")
    env = {**os.environ, "RAYON_NUM_THREADS": str(threads)}

    def constrain():
        os.sched_setaffinity(0, set(affinity[:threads]))

    started = time.monotonic()
    with log.open("wb") as output:
        process = subprocess.Popen(
            [
                "/usr/bin/time",
                "-f",
                "%M",
                "-o",
                str(rss),
                str(root / "bin" / binary),
                str(records),
                "512",
                mode,
                str(languages),
                str(manifest),
            ],
            env=env,
            stdout=output,
            stderr=subprocess.STDOUT,
            preexec_fn=constrain,
            start_new_session=True,
        )
        while process.poll() is None:
            children_path = Path(f"/proc/{process.pid}/task/{process.pid}/children")
            try:
                children = children_path.read_text().split()
                for child in children:
                    status = Path(f"/proc/{child}/status").read_text()
                    resident = next(
                        int(line.split()[1])
                        for line in status.splitlines()
                        if line.startswith("VmRSS:")
                    )
                    if resident > 8 * 1024**2:
                        os.killpg(process.pid, signal.SIGKILL)
                        process.wait()
                        raise RuntimeError(
                            f"{stem} exceeded the 8 GiB resident-memory guard"
                        )
            except (FileNotFoundError, StopIteration):
                pass
            if time.monotonic() - started > 240:
                os.killpg(process.pid, signal.SIGKILL)
                process.wait()
                raise TimeoutError(stem)
            time.sleep(0.05)
    if process.returncode:
        raise RuntimeError(
            f"{stem} exited {process.returncode}: {log.read_text()[-2000:]}"
        )
    line = next(
        line
        for line in reversed(log.read_text().splitlines())
        if line.startswith("BENCHMARK ")
    )
    row = json.loads(line.removeprefix("BENCHMARK "))
    row.update(
        case=label,
        threads=threads,
        repetition=repetition,
        wall_seconds=time.monotonic() - started,
        max_rss_kib=int(rss.read_text()),
        cpu_affinity=affinity[:threads],
        binary_sha256=hashlib.sha256((root / "bin" / binary).read_bytes()).hexdigest(),
    )
    return row


metadata = {
    "platform": platform.platform(),
    "cpu_model": next(
        line.split(":", 1)[1].strip()
        for line in Path("/proc/cpuinfo").read_text().splitlines()
        if line.startswith("model name")
    ),
    "available_cpus": len(os.sched_getaffinity(0)),
    "benchmark_cpus": affinity,
    "rustc": subprocess.check_output(["rustc", "-Vv"], text=True),
    "base": json.loads((evidence / "base.json").read_text()),
    "preparation": json.loads(
        (evidence / "linux-environment-preparation.json").read_text()
    ),
    "note": "Synthetic inputs generated identically by the same example; no application data. CPU affinity and Rayon threads both limited to 1 or 4. Upstream release profile unchanged.",
}
(evidence / "environment.json").write_text(json.dumps(metadata, indent=2) + "\n")
rows = []
print("Warming all four release binaries on a small synthetic corpus.", flush=True)
for label, binary, mode in cases:
    run(label, binary, mode, 1, 64, 0)
schedule = [
    (case, threads, n, repetition)
    for repetition in range(1, args.repetitions + 1)
    for n in args.records
    for threads in [1, 4]
    for case in cases
]
random.Random(20261107).shuffle(schedule)
for i, (case, threads, n, repetition) in enumerate(schedule, 1):
    row = run(*case, threads, n, repetition)
    rows.append(row)
    (evidence / "runs.json").write_text(json.dumps(rows, indent=2) + "\n")
    print(
        json.dumps(
            {
                "run": i,
                "total": len(schedule),
                "case": row["case"],
                "threads": threads,
                "records": n,
                "peak_mib": round(row["max_rss_kib"] / 1024, 1),
                "finalize_seconds": round(row["finalize_seconds"], 3),
                "wall_seconds": round(row["wall_seconds"], 3),
            }
        ),
        flush=True,
    )

for records in args.records:
    subset = [row for row in rows if row["records"] == records]
    assert len({row["bundle_sha1"] for row in subset}) == 1, (
        f"Output bytes differ for {records} records"
    )
    assert len({row["files"] for row in subset}) == 1

print("Checking a three-language corpus across every variant.", flush=True)
multilingual = [run(*case, 4, 257, 1, 3) for case in cases]
assert len({row["bundle_sha1"] for row in multilingual}) == 1, (
    "Multilingual output differs"
)
(evidence / "multilingual-parity.json").write_text(
    json.dumps(multilingual, indent=2) + "\n"
)
summary = []
for n in args.records:
    for threads in [1, 4]:
        for label, _, _ in cases:
            group = [
                row
                for row in rows
                if row["records"] == n
                and row["threads"] == threads
                and row["case"] == label
            ]
            summary.append(
                {
                    "records": n,
                    "threads": threads,
                    "case": label,
                    "runs": len(group),
                    "median_peak_mib": statistics.median(
                        row["max_rss_kib"] / 1024 for row in group
                    ),
                    "median_finalize_seconds": statistics.median(
                        row["finalize_seconds"] for row in group
                    ),
                    "median_wall_seconds": statistics.median(
                        row["wall_seconds"] for row in group
                    ),
                    "bundle_sha1": group[0]["bundle_sha1"],
                    "files": group[0]["files"],
                }
            )
(evidence / "summary.json").write_text(
    json.dumps(
        {
            "output_bytes_identical": True,
            "multilingual_bytes_identical": True,
            "measurements": summary,
        },
        indent=2,
    )
    + "\n"
)
print(
    f"PASS: {len(rows)} release benchmark runs and five multilingual parity runs.",
    flush=True,
)
