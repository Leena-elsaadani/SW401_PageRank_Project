#!/usr/bin/env python3
"""Reproducibly benchmark the sequential and OpenMP PageRank implementations."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import re
import shlex
import shutil
import statistics
import subprocess
import sys
import time
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parent.parent
THREAD_COUNTS = (1, 2, 4, 8)
LARGE_DATASET_THRESHOLD = 600 * 1024 * 1024
MIN_MEMORY_RESERVE = 1024 * 1024 * 1024
RAW_FIELDS = (
    "dataset",
    "dataset_path",
    "dataset_bytes",
    "dataset_sha256",
    "nodes",
    "edges",
    "implementation",
    "requested_threads",
    "actual_threads",
    "phase",
    "repetition",
    "timestamp_utc",
    "solver_seconds",
    "process_wall_seconds",
    "iterations",
    "error",
    "outcome",
    "exit_status",
    "log_path",
)


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def unique_run_id() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def available_memory_bytes() -> int | None:
    try:
        for line in Path("/proc/meminfo").read_text(encoding="ascii").splitlines():
            if line.startswith("MemAvailable:"):
                return int(line.split()[1]) * 1024
    except (OSError, ValueError):
        pass
    if hasattr(os, "sysconf"):
        try:
            return int(os.sysconf("SC_AVPHYS_PAGES") * os.sysconf("SC_PAGE_SIZE"))
        except (OSError, ValueError):
            pass
    return None


def cpu_model() -> str | None:
    try:
        for line in Path("/proc/cpuinfo").read_text(encoding="utf-8").splitlines():
            if line.lower().startswith(("model name", "hardware")):
                return line.split(":", 1)[-1].strip()
    except OSError:
        pass
    return platform.processor() or None


def calculate_metrics(sequential_seconds: float, parallel_seconds: float, threads: int) -> dict[str, Any]:
    if sequential_seconds <= 0.0 or parallel_seconds <= 0.0 or threads <= 0:
        raise ValueError("Runtimes and thread count must be positive.")
    speedup = sequential_seconds / parallel_seconds
    efficiency = speedup / threads
    serial_fraction: float | None = None
    amdahl_speedup: float | None = None
    gustafson_speedup: float | None = None
    serial_fraction_flag = ""
    if threads > 1:
        serial_fraction = (1.0 / speedup - 1.0 / threads) / (1.0 - 1.0 / threads)
        amdahl_denominator = serial_fraction + (1.0 - serial_fraction) / threads
        if amdahl_denominator != 0.0:
            amdahl_speedup = 1.0 / amdahl_denominator
        gustafson_speedup = threads - serial_fraction * (threads - 1)
        if not math.isfinite(serial_fraction) or serial_fraction < 0.0 or serial_fraction > 1.0:
            serial_fraction_flag = "implausible estimate; investigate measurement noise or overhead"
    return {
        "speedup": speedup,
        "efficiency": efficiency,
        "serial_fraction": serial_fraction,
        "serial_fraction_flag": serial_fraction_flag,
        "amdahl_speedup": amdahl_speedup,
        "gustafson_speedup": gustafson_speedup,
    }


def parse_harness_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {"nodes", "edges", "iterations", "error", "elapsed_seconds", "actual_threads"}
    missing = required.difference(values)
    if missing:
        raise ValueError(f"Benchmark harness omitted output fields: {', '.join(sorted(missing))}")
    return values


def compiler_info(compiler: str) -> tuple[str, str]:
    resolved = shutil.which(compiler)
    if not resolved:
        raise RuntimeError(f"C++ compiler not found: {compiler}")
    result = subprocess.run(
        [resolved, "--version"],
        check=True,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
    )
    return resolved, result.stdout.splitlines()[0]


def discover_datasets(explicit: list[Path], include_full: bool) -> list[Path]:
    if explicit:
        candidates = explicit
    else:
        candidates = [
            ROOT / "data" / "samples" / "livejournal_100MB.txt",
            ROOT / "data" / "samples" / "livejournal_500MB.txt",
        ]
        if include_full:
            candidates.append(ROOT / "data" / "processed" / "livejournal_clean.txt")
    found: list[Path] = []
    seen: set[Path] = set()
    for candidate in candidates:
        path = candidate.expanduser()
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if not path.is_file():
            print(f"Dataset unavailable: {path}", file=sys.stderr)
            continue
        if path not in seen:
            found.append(path)
            seen.add(path)
    return found


def check_dataset_resources(path: Path, include_full: bool, allow_low_memory: bool) -> None:
    size = path.stat().st_size
    if size > LARGE_DATASET_THRESHOLD and not include_full:
        raise RuntimeError(
            f"{path.name} is {size:,} bytes; datasets larger than 600 MiB require "
            "--include-full after reviewing available memory and runtime."
        )
    available = available_memory_bytes()
    if available is None:
        print(f"Warning: available memory could not be determined for {path.name}.", file=sys.stderr)
        return
    estimate = max(MIN_MEMORY_RESERVE, size * 2)
    required = estimate + MIN_MEMORY_RESERVE
    if available < required and not allow_low_memory:
        raise RuntimeError(
            f"Skipping {path.name}: estimated working set is at least "
            f"{estimate / (1024 ** 3):.2f} GiB and only "
            f"{available / (1024 ** 3):.2f} GiB is available. "
            "Use --allow-low-memory only after reviewing the risk."
        )
    print(
        f"Resource check {path.name}: size={size:,} bytes, conservative working-set "
        f"estimate>={estimate / (1024 ** 3):.2f} GiB, "
        f"available={available / (1024 ** 3):.2f} GiB."
    )


def make_run_directory(root: Path, run_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    path = root / run_id
    suffix = 1
    while path.exists():
        path = root / f"{run_id}_{suffix}"
        suffix += 1
    path.mkdir()
    return path


def run_one(
    executable: Path,
    dataset: Path,
    dataset_bytes: int,
    dataset_digest: str,
    implementation: str,
    threads: int,
    phase: str,
    repetition: int,
    damping: float,
    tolerance: float,
    max_iterations: int,
    timeout: float,
    log_dir: Path,
) -> dict[str, Any]:
    label = f"{dataset.stem}_{implementation}_{threads}t_{phase}_{repetition}"
    log_path = log_dir / f"{label}.log"
    command = [
        str(executable),
        implementation,
        str(dataset),
        str(damping),
        str(tolerance),
        str(max_iterations),
        str(threads),
    ]
    started_at = utc_now()
    start = time.perf_counter()
    outcome = "failed"
    exit_status: int | str = ""
    parsed: dict[str, str] = {}
    process_output = ""
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={
                **os.environ,
                "OMP_DYNAMIC": "FALSE",
                "OMP_NUM_THREADS": str(threads),
                "OMP_PROC_BIND": "close",
            },
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        process_output = completed.stdout
        exit_status = completed.returncode
        if completed.returncode == 0:
            parsed = parse_harness_output(completed.stdout)
            if int(parsed["actual_threads"]) != threads:
                raise ValueError(
                    f"Observed {parsed['actual_threads']} OpenMP threads; expected {threads}."
                )
            outcome = "success"
    except subprocess.TimeoutExpired as error:
        outcome = "timed_out"
        partial = error.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        process_output = str(partial) + f"\nBenchmark timed out after {timeout} seconds.\n"
    except (OSError, ValueError) as error:
        process_output += f"\nBenchmark runner error: {error}\n"
    process_wall = time.perf_counter() - start
    log_path.write_text(
        f"timestamp_utc={started_at}\ncommand={shlex.join(command)}\n"
        f"timeout_seconds={timeout}\noutcome={outcome}\nexit_status={exit_status}\n\n"
        f"{process_output}",
        encoding="utf-8",
    )
    row: dict[str, Any] = {
        "dataset": dataset.name,
        "dataset_path": str(dataset),
        "dataset_bytes": dataset_bytes,
        "dataset_sha256": dataset_digest,
        "nodes": parsed.get("nodes", ""),
        "edges": parsed.get("edges", ""),
        "implementation": implementation,
        "requested_threads": threads,
        "actual_threads": parsed.get("actual_threads", ""),
        "phase": phase,
        "repetition": repetition,
        "timestamp_utc": started_at,
        "solver_seconds": parsed.get("elapsed_seconds", ""),
        "process_wall_seconds": f"{process_wall:.9f}",
        "iterations": parsed.get("iterations", ""),
        "error": parsed.get("error", ""),
        "outcome": outcome,
        "exit_status": exit_status,
        "log_path": str(log_path),
    }
    print(
        f"{dataset.name}: {implementation} {threads} thread(s), "
        f"{phase} {repetition}: {outcome}"
        + (f", solver={row['solver_seconds']} s" if row["solver_seconds"] else "")
    )
    return row


def write_csv(path: Path, rows: list[dict[str, Any]], fields: tuple[str, ...] | list[str]) -> None:
    with path.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def summarize_rows(rows: list[dict[str, Any]], repetitions: int) -> list[dict[str, Any]]:
    summaries: list[dict[str, Any]] = []
    datasets = sorted({row["dataset"] for row in rows})
    for dataset in datasets:
        dataset_rows = [row for row in rows if row["dataset"] == dataset and row["phase"] == "measured"]
        seq_rows = [
            row for row in dataset_rows
            if row["implementation"] == "sequential" and row["outcome"] == "success"
        ]
        seq_times = [float(row["solver_seconds"]) for row in seq_rows]
        sequential_median = statistics.median(seq_times) if len(seq_times) == repetitions else None
        for implementation, thread_count in [("sequential", 1), *(("openmp", t) for t in THREAD_COUNTS)]:
            matching = [
                row for row in dataset_rows
                if row["implementation"] == implementation
                and int(row["requested_threads"]) == thread_count
            ]
            successful = [row for row in matching if row["outcome"] == "success"]
            times = [float(row["solver_seconds"]) for row in successful]
            complete = len(successful) == repetitions
            runtime = statistics.median(times) if complete else None
            metrics: dict[str, Any] = {
                "speedup": None,
                "efficiency": None,
                "serial_fraction": None,
                "serial_fraction_flag": "",
                "amdahl_speedup": None,
                "gustafson_speedup": None,
            }
            if runtime is not None and sequential_median is not None and implementation == "openmp":
                metrics = calculate_metrics(sequential_median, runtime, thread_count)
            first = matching[0] if matching else {}
            summaries.append(
                {
                    "dataset": dataset,
                    "implementation": implementation,
                    "threads": thread_count,
                    "successful_repetitions": len(successful),
                    "required_repetitions": repetitions,
                    "median_seconds": runtime,
                    "sequential_median_seconds": sequential_median,
                    "complete": complete and (implementation == "sequential" or sequential_median is not None),
                    "nodes": first.get("nodes", ""),
                    "edges": first.get("edges", ""),
                    **metrics,
                }
            )
    return summaries


def write_plots(summaries: list[dict[str, Any]], plots_dir: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except ImportError as error:
        raise RuntimeError(
            "Matplotlib is required to generate benchmark plots. "
            "Install it with: python3 -m pip install -r benchmarks/requirements.txt"
        ) from error

    generated: list[str] = []
    datasets = sorted({row["dataset"] for row in summaries})
    for dataset in datasets:
        rows = [row for row in summaries if row["dataset"] == dataset]
        sequential = next(
            (row for row in rows if row["implementation"] == "sequential" and row["complete"]),
            None,
        )
        parallel = sorted(
            (row for row in rows if row["implementation"] == "openmp" and row["complete"]),
            key=lambda row: row["threads"],
        )
        if not sequential or not parallel:
            continue
        plots_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(dataset).stem)

        def save_plot(filename: str, title: str, ylabel: str, values: list[float], color: str) -> None:
            figure, axis = plt.subplots(figsize=(7, 4.5))
            axis.plot([row["threads"] for row in parallel], values, marker="o", color=color, label="OpenMP")
            axis.set_title(f"{title} — {dataset}")
            axis.set_xlabel("OpenMP threads")
            axis.set_ylabel(ylabel)
            axis.set_xticks([row["threads"] for row in parallel])
            axis.grid(True, alpha=0.3)
            axis.legend()
            figure.tight_layout()
            target = plots_dir / f"{stem}_{filename}.png"
            figure.savefig(target, dpi=160)
            plt.close(figure)
            generated.append(str(target))

        save_plot(
            "runtime",
            "Median runtime versus thread count",
            "Solver runtime (seconds)",
            [row["median_seconds"] for row in parallel],
            "tab:blue",
        )
        save_plot(
            "speedup",
            "Measured speedup versus thread count",
            "Speedup (ratio)",
            [row["speedup"] for row in parallel],
            "tab:green",
        )
        save_plot(
            "efficiency",
            "Parallel efficiency versus thread count",
            "Efficiency (ratio)",
            [row["efficiency"] for row in parallel],
            "tab:orange",
        )

        figure, axis = plt.subplots(figsize=(8, 4.5))
        labels = ["Sequential"] + [f"OpenMP {row['threads']} thread(s)" for row in parallel]
        runtimes = [sequential["median_seconds"]] + [row["median_seconds"] for row in parallel]
        axis.bar(labels, runtimes, color=["tab:gray"] + ["tab:blue"] * len(parallel))
        axis.set_title(f"Sequential and OpenMP median runtime — {dataset}")
        axis.set_ylabel("Solver runtime (seconds)")
        axis.set_xlabel("Implementation")
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.3)
        figure.tight_layout()
        target = plots_dir / f"{stem}_comparison.png"
        figure.savefig(target, dpi=160)
        plt.close(figure)
        generated.append(str(target))
    return generated


def markdown_number(value: Any, digits: int = 6) -> str:
    if value is None or value == "":
        return "Unavailable"
    if isinstance(value, float):
        if not math.isfinite(value):
            return "Unavailable"
        return f"{value:.{digits}g}"
    return str(value)


def generate_report(
    report_path: Path,
    run_id: str,
    datasets: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    environment: dict[str, Any],
    result_dir: Path,
    plots: list[str],
    parameters: dict[str, Any],
) -> None:
    lines = [
        "# Performance Evaluation",
        "",
        "## 1. Purpose",
        "",
        "This evaluation compares the sequential PageRank implementation with its OpenMP counterpart, "
        "measuring solver runtime, speedup, thread efficiency, and observed scalability. All reported "
        "numerical results are generated from successful measured repetitions; no missing values are estimated.",
        "",
        "## 2. Experimental environment",
        "",
        "| Property | Recorded value |",
        "|---|---|",
        f"| Operating system | {environment.get('platform', 'Unavailable')} |",
        f"| CPU model | {environment.get('cpu_model') or 'Unavailable'} |",
        f"| Logical CPUs visible | {environment.get('logical_cpu_count') or 'Unavailable'} |",
        f"| Available memory at run start | {environment.get('available_memory_gib', 'Unavailable')} GiB |",
        f"| Compiler | {environment.get('compiler_version', 'Unavailable')} |",
        f"| Compiler flags | `{environment.get('compiler_flags', 'Unavailable')}` |",
        f"| Python | {environment.get('python_version', 'Unavailable')} |",
        f"| Run identifier (UTC) | `{run_id}` |",
        "",
        "## 3. Datasets",
        "",
        "The documented 100 MiB and 500 MiB inputs are prefixes of the cleaned edge ordering, not random "
        "samples. The full input is the cleaned directed LiveJournal graph. The runner records actual file "
        "size, SHA-256, node count, and edge count for each dataset it processes.",
        "",
    ]
    if datasets:
        lines.extend(
            [
                "| Dataset | Size (bytes) | SHA-256 | Nodes | Directed edges |",
                "|---|---:|---|---:|---:|",
            ]
        )
        lines.extend(
            f"| {item['name']} | {item['bytes']} | `{item['sha256']}` | "
            f"{item.get('nodes') or 'Unavailable'} | {item.get('edges') or 'Unavailable'} |"
            for item in datasets
        )
    else:
        lines.extend(
            [
                "No project benchmark dataset was present when this report was generated. The required "
                "LiveJournal files and their performance results are therefore unavailable. The committed "
                "tiny graph is reserved for workflow validation and is not reported as a project benchmark.",
            ]
        )
    lines.extend(
        [
            "",
            "## 4. Methodology",
            "",
            f"Both implementations use damping factor `{parameters['damping']}`, tolerance "
            f"`{parameters['tolerance']}`, and maximum `{parameters['max_iterations']}` iterations. "
            "Each configuration has one unmeasured warm-up followed by "
            f"{parameters['repetitions']} measured repetitions. Sequential PageRank is measured once per "
            "dataset; OpenMP is measured at 1, 2, 4, and 8 threads. The runner checks the actual OpenMP team "
            "size and records a mismatch as a failed run. Compilation and graph loading are excluded from "
            "solver time; the same harness loads each graph before timing the direct solver call. Timing uses "
            "`std::chrono::steady_clock` at sub-millisecond resolution. The implementation-provided elapsed "
            "time was not used because it is rounded to whole milliseconds and the OpenMP CLI does not report it.",
            "",
            "All raw warm-up and measured attempts, including nonzero exits and timeouts, are retained in "
            f"`{result_dir.as_posix()}/raw_runs.csv`; corresponding stdout/stderr logs and compiler output are "
            "stored with the run. The processed medians and formulas are in `summary.csv` and `metrics.json`.",
            "",
            "## 5. Runtime results",
            "",
            "| Dataset | Sequential median (s) | OpenMP 1 thread (s) | OpenMP 2 threads (s) | OpenMP 4 threads (s) | OpenMP 8 threads (s) |",
            "|---|---:|---:|---:|---:|---:|",
        ]
    )
    for dataset in sorted({row["dataset"] for row in summaries}):
        rows = [row for row in summaries if row["dataset"] == dataset]
        seq = next((row for row in rows if row["implementation"] == "sequential"), None)
        by_threads = {row["threads"]: row for row in rows if row["implementation"] == "openmp"}
        values = [seq.get("median_seconds") if seq else None] + [
            by_threads.get(threads, {}).get("median_seconds") for threads in THREAD_COUNTS
        ]
        lines.append("| " + dataset + " | " + " | ".join(markdown_number(value) for value in values) + " |")
    if not summaries:
        lines.append("| No available benchmark dataset | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |")
    lines.extend(
        [
            "",
            "A median is reported only when all required measured repetitions for that configuration succeeded. "
            "A partial run set is marked unavailable rather than presented as a complete median.",
            "",
            "## 6. Speedup, efficiency, and serial-fraction estimate",
            "",
            "Speedup is `T_seq / T_parallel`; efficiency is `speedup / P` and is shown as a ratio (multiply by "
            "100 for percent). The Karp–Flatt estimate is `s = (1/S(P) - 1/P) / (1 - 1/P)` and is omitted "
            "for P = 1. Estimates outside [0, 1] are retained and explicitly flagged; they may indicate "
            "measurement noise, parallel overhead, or behavior not captured by a simple fixed serial fraction. "
            "Karp–Flatt is an estimate from observed performance, not a direct measurement of serial code.",
            "",
            "| Dataset | Threads | Median runtime (s) | Speedup (ratio) | Efficiency (ratio) | Karp–Flatt s | Amdahl S(P) | Gustafson S(P) | Estimate flag |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    parallel_summaries = [row for row in summaries if row["implementation"] == "openmp"]
    for row in parallel_summaries:
        lines.append(
            f"| {row['dataset']} | {row['threads']} | {markdown_number(row['median_seconds'])} | "
            f"{markdown_number(row['speedup'])} | {markdown_number(row['efficiency'])} | "
            f"{markdown_number(row['serial_fraction'])} | {markdown_number(row['amdahl_speedup'])} | "
            f"{markdown_number(row['gustafson_speedup'])} | {row['serial_fraction_flag'] or '—'} |"
        )
    if not parallel_summaries:
        lines.append("| No completed parallel runs | — | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | — |")
    lines.extend(
        [
            "",
            "## 7. Amdahl’s and Gustafson’s laws",
            "",
            "Amdahl’s prediction, `S(P) = 1 / (s + (1-s)/P)`, illustrates a fixed-workload upper bound "
            "when the estimated serial fraction is valid. Gustafson’s prediction, `S(P) = P - s(P-1)`, "
            "describes the potential speedup when workload scales with processor count. These theoretical "
            "values are derived from Karp–Flatt estimates and are not benchmark measurements. They are "
            "unavailable when no valid completed median is available.",
            "",
            "## 8. Scalability and interpretation",
            "",
        ]
    )
    if parallel_summaries:
        lines.append(
            "Interpret scalability from the measured runtime, speedup, and efficiency columns above. "
            "Interpret thread scaling only for complete configurations on the same dataset and environment; "
            "do not generalize from the tiny validation fixture."
        )
    else:
        lines.append(
            "No scalability conclusion can be drawn because the project datasets were unavailable and no "
            "project benchmark measurements were completed."
        )
    lines.extend(
        [
            "",
            "## 9. Figures",
            "",
        ]
    )
    if plots:
        lines.extend(f"![{Path(plot).stem}]({Path(os.path.relpath(plot, report_path.parent)).as_posix()})" for plot in plots)
    else:
        lines.append("No figures were generated because there are no complete dataset measurements.")
    lines.extend(
        [
            "",
            "The runner creates per-dataset plots for median runtime, measured speedup, efficiency, and the "
            "sequential/OpenMP runtime comparison. Each plotted point comes only from complete measured runs.",
            "",
            "## 10. Limitations and sources of error",
            "",
            "- Large LiveJournal inputs are not included in Git. Missing files leave all corresponding results unavailable.",
            "- The current OpenMP implementation uses the same solver code path as the sequential version, but parallel "
            "reductions and scheduling can change floating-point summation order.",
            "- Solver-only timing excludes graph parsing, so it isolates PageRank iteration cost rather than end-to-end application latency.",
            "- Warm-up and operating-system caching, CPU frequency scaling, background load, and thread placement can affect measurements.",
            "- The documented samples are prefixes of the original edge ordering and may not represent the full graph structurally.",
            "- Amdahl and Gustafson predictions rely on a derived serial fraction and should not be treated as direct observations.",
            "",
            "## 11. Conclusion",
            "",
        ]
    )
    if summaries:
        lines.append(
            "This report contains the measurements available for the recorded run. Interpret results only "
            "for datasets and configurations with complete successful repetitions. Validation-fixture timings "
            "are not evidence of LiveJournal scalability."
        )
    else:
        lines.append(
            "The benchmarking workflow is in place, but no project-dataset performance result can be stated "
            "until the local LiveJournal files are prepared and the benchmark is run."
        )
    lines.extend(
        [
            "",
            "## 12. Reproduction",
            "",
            "See [`benchmarks/README.md`](../benchmarks/README.md) for build, smoke-test, and full benchmark commands. "
            f"Recorded parameters: damping `{parameters['damping']}`, tolerance `{parameters['tolerance']}`, "
            f"maximum iterations `{parameters['max_iterations']}`, measured repetitions "
            f"`{parameters['repetitions']}`, warm-ups `{parameters['warmups']}`.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", type=Path, default=[], help="Benchmark this dataset; repeatable.")
    parser.add_argument("--include-full", action="store_true", help="Include the cleaned full dataset after resource review.")
    parser.add_argument("--repetitions", type=int, default=3, help="Measured repetitions per configuration (minimum 3).")
    parser.add_argument("--warmups", type=int, default=1, help="Unmeasured warm-up runs per configuration.")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Per-run timeout in seconds.")
    parser.add_argument("--damping", type=float, default=0.85)
    parser.add_argument("--tolerance", type=float, default=1e-8)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "results" / "performance")
    parser.add_argument("--plots-root", type=Path, default=ROOT / "plots" / "performance")
    parser.add_argument("--report", type=Path, default=ROOT / "report" / "performance_evaluation.md")
    parser.add_argument("--no-report", action="store_true", help="Do not update report/performance_evaluation.md.")
    parser.add_argument("--no-plots", action="store_true", help="Skip Matplotlib plots.")
    parser.add_argument("--allow-low-memory", action="store_true", help="Override the conservative memory guard.")
    args = parser.parse_args()
    if args.repetitions < 3:
        parser.error("--repetitions must be at least 3.")
    if args.warmups < 0 or args.timeout <= 0:
        parser.error("--warmups must be nonnegative and --timeout must be positive.")
    if args.max_iterations <= 0 or args.tolerance <= 0 or not 0 < args.damping < 1:
        parser.error("Use positive tolerance/iterations and a damping factor strictly between 0 and 1.")

    try:
        compiler, compiler_version = compiler_info(args.compiler)
        datasets = discover_datasets(args.dataset, args.include_full)
        for dataset in datasets:
            check_dataset_resources(dataset, args.include_full, args.allow_low_memory)
    except (RuntimeError, OSError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2

    run_id = unique_run_id()
    output_root = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    plots_root = args.plots_root if args.plots_root.is_absolute() else ROOT / args.plots_root
    run_dir = make_run_directory(output_root, run_id)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir()
    binary_dir = ROOT / "build"
    binary_dir.mkdir(exist_ok=True)
    executable = binary_dir / ("performance_harness.exe" if os.name == "nt" else "performance_harness")
    compile_command = [
        compiler,
        "-std=c++17",
        "-O3",
        "-fopenmp",
        str(ROOT / "src" / "sequential" / "graph.cpp"),
        str(ROOT / "src" / "sequential" / "pagerank.cpp"),
        str(ROOT / "src" / "openmp" / "pagerank_omp.cpp"),
        str(ROOT / "benchmarks" / "performance_harness.cpp"),
        "-I",
        str(ROOT / "src" / "sequential"),
        "-o",
        str(executable),
    ]
    compile_start = time.perf_counter()
    compiled = subprocess.run(
        compile_command,
        cwd=ROOT,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    compile_seconds = time.perf_counter() - compile_start
    (run_dir / "build.log").write_text(
        f"command={shlex.join(compile_command)}\n"
        f"compile_seconds={compile_seconds:.9f}\n"
        f"exit_status={compiled.returncode}\n\n{compiled.stdout}",
        encoding="utf-8",
    )
    if compiled.returncode != 0:
        print(f"Compilation failed; see {run_dir / 'build.log'}", file=sys.stderr)
        return 1

    environment = {
        "timestamp_utc": utc_now(),
        "run_id": run_id,
        "platform": platform.platform(),
        "cpu_model": cpu_model(),
        "logical_cpu_count": os.cpu_count(),
        "available_memory_gib": (
            round(available_memory_bytes() / (1024 ** 3), 3)
            if available_memory_bytes() is not None else None
        ),
        "compiler": compiler,
        "compiler_version": compiler_version,
        "compiler_flags": "-std=c++17 -O3 -fopenmp",
        "compiler_command": shlex.join(compile_command),
        "compile_seconds": compile_seconds,
        "python_version": platform.python_version(),
        "thread_counts": list(THREAD_COUNTS),
        "repetitions": args.repetitions,
        "warmups": args.warmups,
        "timeout_seconds": args.timeout,
        "damping": args.damping,
        "tolerance": args.tolerance,
        "max_iterations": args.max_iterations,
        "available_datasets": [str(path) for path in datasets],
    }
    (run_dir / "environment.json").write_text(json.dumps(environment, indent=2) + "\n", encoding="utf-8")

    raw_rows: list[dict[str, Any]] = []
    dataset_metadata: list[dict[str, Any]] = []
    for dataset in datasets:
        size = dataset.stat().st_size
        digest = sha256_file(dataset)
        metadata: dict[str, Any] = {
            "name": dataset.name,
            "path": str(dataset),
            "bytes": size,
            "sha256": digest,
        }
        dataset_metadata.append(metadata)
        configurations = [("sequential", 1)] + [("openmp", count) for count in THREAD_COUNTS]
        for implementation, threads in configurations:
            for repetition in range(1, args.warmups + 1):
                raw_rows.append(
                    run_one(
                        executable, dataset, size, digest, implementation, threads, "warmup",
                        repetition, args.damping, args.tolerance, args.max_iterations,
                        args.timeout, logs_dir,
                    )
                )
            for repetition in range(1, args.repetitions + 1):
                raw_rows.append(
                    run_one(
                        executable, dataset, size, digest, implementation, threads, "measured",
                        repetition, args.damping, args.tolerance, args.max_iterations,
                        args.timeout, logs_dir,
                    )
                )
        successful_rows = [
            row for row in raw_rows
            if row["dataset"] == dataset.name and row["outcome"] == "success"
        ]
        if successful_rows:
            metadata["nodes"] = successful_rows[0]["nodes"]
            metadata["edges"] = successful_rows[0]["edges"]
    write_csv(run_dir / "raw_runs.csv", raw_rows, RAW_FIELDS)
    summaries = summarize_rows(raw_rows, args.repetitions)
    summary_fields = [
        "dataset", "implementation", "threads", "successful_repetitions", "required_repetitions",
        "median_seconds", "sequential_median_seconds", "speedup", "efficiency", "serial_fraction",
        "serial_fraction_flag", "amdahl_speedup", "gustafson_speedup", "complete", "nodes", "edges",
    ]
    write_csv(run_dir / "summary.csv", summaries, summary_fields)
    (run_dir / "metrics.json").write_text(json.dumps(summaries, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    plots_dir = make_run_directory(plots_root, run_id) if datasets and not args.no_plots else plots_root / run_id
    plot_paths: list[str] = []
    if datasets and not args.no_plots:
        try:
            plot_paths = write_plots(summaries, plots_dir)
        except RuntimeError as error:
            print(f"Plot generation failed: {error}", file=sys.stderr)
            return 1

    (run_dir / "dataset_metadata.json").write_text(
        json.dumps(dataset_metadata, indent=2) + "\n", encoding="utf-8"
    )
    if not args.no_report:
        report_path = args.report if args.report.is_absolute() else ROOT / args.report
        generate_report(
            report_path,
            run_id,
            dataset_metadata,
            summaries,
            environment,
            run_dir.relative_to(ROOT) if run_dir.is_relative_to(ROOT) else run_dir,
            plot_paths,
            {
                "damping": args.damping,
                "tolerance": args.tolerance,
                "max_iterations": args.max_iterations,
                "repetitions": args.repetitions,
                "warmups": args.warmups,
            },
        )
        print(f"Updated report: {report_path}")
    print(f"Raw/processed results: {run_dir}")
    if not datasets:
        print("No LiveJournal sample/full dataset was found; no benchmark repetitions were run.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
