#!/usr/bin/env python3
"""Reproducibly benchmark sequential and OpenMP PageRank implementations."""

from __future__ import annotations

import argparse
import csv
import datetime as dt
import hashlib
import json
import math
import os
import platform
import random
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
CONFIGURATIONS = [("sequential", 1), *(("openmp", count) for count in THREAD_COUNTS)]
DEFAULT_TOLERANCE = 1e-6
DEFAULT_REPETITIONS = 5
DEFAULT_SEED = 4013
DEFAULT_COMPARISON_TOLERANCE = 1e-6
LARGE_DATASET_THRESHOLD = 600 * 1024 * 1024
MIN_MEMORY_RESERVE = 1024 * 1024 * 1024
DOCUMENTED_DATASETS = {
    "livejournal_100MB.txt": {
        "kind": "prefix_sample",
        "expected_edges": 8_015_157,
        "expected_bytes": 104_857_589,
    },
    "livejournal_500MB.txt": {
        "kind": "prefix_sample",
        "expected_edges": 37_672_977,
        "expected_bytes": 524_287_992,
    },
    "livejournal_clean.txt": {
        "kind": "full_cleaned_graph",
        "expected_nodes": 4_847_571,
        "expected_edges": 68_993_773,
        "expected_bytes": 1_011_604_076,
    },
}
RAW_FIELDS = (
    "dataset",
    "dataset_kind",
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
    "execution_order",
    "timestamp_utc",
    "solver_seconds",
    "average_iteration_seconds_derived",
    "graph_load_seconds",
    "process_wall_seconds",
    "peak_rss_kib",
    "iterations",
    "error",
    "converged",
    "rank_sum",
    "rank_sum_valid",
    "top10",
    "sequential_verification_iterations",
    "sequential_verification_error",
    "sequential_verification_converged",
    "sequential_verification_rank_sum",
    "sequential_verification_top10",
    "iteration_counts_match",
    "max_abs_difference",
    "numerical_consistency",
    "comparison_tolerance",
    "correctness_status",
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


def lscpu_values() -> dict[str, str]:
    if not shutil.which("lscpu"):
        return {}
    try:
        result = subprocess.run(
            ["lscpu"],
            check=True,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )
    except (OSError, subprocess.CalledProcessError):
        return {}
    values: dict[str, str] = {}
    for line in result.stdout.splitlines():
        if ":" in line:
            key, value = line.split(":", 1)
            values[key.strip()] = value.strip()
    return values


def physical_core_count(lscpu: dict[str, str]) -> int | None:
    try:
        cores_per_socket = int(lscpu["Core(s) per socket"])
        sockets = int(lscpu["Socket(s)"])
        return cores_per_socket * sockets
    except (KeyError, ValueError):
        return None


def git_metadata() -> dict[str, Any]:
    def git(*args: str) -> str | None:
        try:
            result = subprocess.run(
                ["git", "-C", str(ROOT), *args],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
            )
            return result.stdout.strip()
        except (OSError, subprocess.CalledProcessError):
            return None

    branch = git("branch", "--show-current")
    commit = git("rev-parse", "HEAD")
    status = git("status", "--porcelain")
    return {
        "branch": branch or "unavailable",
        "commit": commit or "unavailable",
        "working_tree_dirty": bool(status) if status is not None else "unavailable",
    }


def environment_metadata(
    compiler: str | None,
    compiler_version: str | None,
    compiler_flags: str,
    repetitions: int,
    warmups: int,
    seed: int,
    damping: float,
    tolerance: float,
    max_iterations: int,
    comparison_tolerance: float,
    effective_omp: dict[str, str],
    run_id: str,
) -> dict[str, Any]:
    lscpu = lscpu_values()
    logical_count = os.cpu_count()
    physical_count = physical_core_count(lscpu)
    governor_paths = sorted(Path("/sys/devices/system/cpu").glob("cpu*/cpufreq/scaling_governor"))
    governors = sorted({path.read_text(encoding="ascii").strip() for path in governor_paths})
    os_release: dict[str, str] = {}
    try:
        for line in Path("/etc/os-release").read_text(encoding="utf-8").splitlines():
            key, sep, value = line.partition("=")
            if sep:
                os_release[key] = value.strip().strip('"')
    except OSError:
        pass
    kernel = platform.release()
    wsl_detected = "microsoft" in kernel.lower() or "WSL_INTEROP" in os.environ
    distro = os_release.get("PRETTY_NAME", "unavailable")
    wsl_version = "unavailable"
    if wsl_detected and shutil.which("wsl.exe"):
        try:
            result = subprocess.run(
                ["wsl.exe", "--version"],
                check=True,
                text=False,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                timeout=5,
            )
            wsl_version = result.stdout.decode("utf-16le", errors="replace").replace("\x00", "").strip()
        except (OSError, subprocess.SubprocessError):
            pass
    available = available_memory_bytes()
    return {
        "timestamp_utc": utc_now(),
        "run_id": run_id,
        "operating_system": platform.platform(),
        "kernel": kernel,
        "linux_distribution": distro,
        "wsl_detected": wsl_detected,
        "wsl_version": wsl_version,
        "cpu_model": cpu_model() or "unavailable",
        "physical_core_count": physical_count if physical_count is not None else "unavailable",
        "logical_processor_count": logical_count if logical_count is not None else "unavailable",
        "smt_status": (
            "enabled or logical count exceeds physical core count"
            if physical_count is not None and logical_count and logical_count > physical_count
            else "not detected or unavailable"
        ),
        "available_system_memory_bytes": available if available is not None else "unavailable",
        "available_system_memory_gib": (
            round(available / (1024**3), 3) if available is not None else "unavailable"
        ),
        "peak_rss_measurement": "Linux getrusage(RUSAGE_SELF), KiB, process high-water mark including graph load",
        "cpu_governor": governors or "unavailable",
        "wsl_memory_configuration": "unavailable",
        "compiler": compiler or "unavailable",
        "compiler_version": compiler_version or "unavailable",
        "compiler_flags": compiler_flags,
        "python_version": platform.python_version(),
        "git": git_metadata(),
        "omp_environment": effective_omp,
        "configuration": {
            "thread_counts": list(THREAD_COUNTS),
            "repetitions": repetitions,
            "warmups": warmups,
            "random_seed": seed,
            "damping": damping,
            "tolerance": tolerance,
            "max_iterations": max_iterations,
            "comparison_tolerance": comparison_tolerance,
        },
    }


def karp_flatt_from_speedup(speedup: float, threads: int) -> float | None:
    if threads <= 1 or not math.isfinite(speedup) or speedup <= 0.0:
        return None
    return (1.0 / speedup - 1.0 / threads) / (1.0 - 1.0 / threads)


def amdahl_speedup(serial_fraction: float, threads: int) -> float | None:
    if threads <= 0 or not math.isfinite(serial_fraction) or not 0.0 <= serial_fraction <= 1.0:
        return None
    denominator = serial_fraction + (1.0 - serial_fraction) / threads
    return 1.0 / denominator if denominator > 0.0 else None


def gustafson_speedup(serial_fraction: float, threads: int) -> float | None:
    if threads <= 0 or not math.isfinite(serial_fraction):
        return None
    return threads - serial_fraction * (threads - 1)


def calculate_metrics(
    sequential_seconds: float,
    openmp_seconds: dict[int, float | None],
) -> dict[int, dict[str, Any]]:
    if not math.isfinite(sequential_seconds) or sequential_seconds <= 0.0:
        raise ValueError("Sequential runtime must be finite and positive.")
    valid: dict[int, float | None] = {}
    for threads, runtime in openmp_seconds.items():
        if runtime is not None and (not math.isfinite(runtime) or runtime <= 0.0):
            raise ValueError(f"OpenMP runtime for {threads} threads must be finite and positive.")
        valid[threads] = runtime
    omp_one = valid.get(1)
    omp_two = valid.get(2)
    p2_speedup = sequential_seconds / omp_two if omp_two else None
    serial_fraction = karp_flatt_from_speedup(p2_speedup, 2) if p2_speedup else None
    serial_status = "unavailable"
    if serial_fraction is not None:
        serial_status = "valid" if 0.0 <= serial_fraction <= 1.0 else "out_of_range"
    results: dict[int, dict[str, Any]] = {}
    for threads, runtime in valid.items():
        seq_speedup = sequential_seconds / runtime if runtime is not None else None
        omp_self_speedup = omp_one / runtime if omp_one and runtime is not None else None
        amdahl_prediction = (
            amdahl_speedup(serial_fraction, threads)
            if serial_status == "valid" and threads in (4, 8)
            else None
        )
        gustafson_prediction = (
            gustafson_speedup(serial_fraction, threads)
            if serial_status == "valid"
            else None
        )
        results[threads] = {
            "sequential_speedup": seq_speedup,
            "openmp_self_speedup": omp_self_speedup,
            "efficiency": seq_speedup / threads if seq_speedup is not None else None,
            "karp_flatt_p2": serial_fraction,
            "karp_flatt_status": serial_status,
            "amdahl_prediction_from_p2": amdahl_prediction,
            "amdahl_prediction_difference": (
                seq_speedup - amdahl_prediction
                if seq_speedup is not None and amdahl_prediction is not None
                else None
            ),
            "gustafson_illustration_from_p2": gustafson_prediction,
        }
    return results


def parse_harness_output(output: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for line in output.splitlines():
        if "=" in line:
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    required = {
        "nodes",
        "edges",
        "actual_threads",
        "solver_iterations",
        "solver_error",
        "solver_converged",
        "rank_sum",
        "rank_sum_valid",
        "top10",
        "solver_seconds",
        "average_iteration_seconds",
        "graph_load_seconds",
        "peak_rss_kib",
    }
    missing = required.difference(values)
    if missing:
        raise ValueError(f"Benchmark harness omitted output fields: {', '.join(sorted(missing))}")
    return values


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", action="append", type=Path, default=[], help="Benchmark this dataset; repeatable.")
    parser.add_argument("--include-full", action="store_true", help="Request the cleaned full dataset after reviewing resources.")
    parser.add_argument("--repetitions", type=int, default=DEFAULT_REPETITIONS, help="Measured repetitions, minimum 3 (recommend 5).")
    parser.add_argument("--warmups", type=int, default=1, help="Unmeasured warm-up runs per configuration.")
    parser.add_argument("--timeout", type=float, default=3600.0, help="Per-process timeout in seconds.")
    parser.add_argument("--seed", type=int, default=DEFAULT_SEED, help="Seed for reproducible configuration interleaving.")
    parser.add_argument("--damping", type=float, default=0.85)
    parser.add_argument("--tolerance", type=float, default=DEFAULT_TOLERANCE)
    parser.add_argument("--max-iterations", type=int, default=100)
    parser.add_argument(
        "--comparison-tolerance",
        type=float,
        default=DEFAULT_COMPARISON_TOLERANCE,
        help="Maximum absolute rank difference accepted for sequential/OpenMP consistency.",
    )
    parser.add_argument("--compiler", default=os.environ.get("CXX", "g++"))
    parser.add_argument("--output-root", type=Path, default=ROOT / "results" / "performance")
    parser.add_argument("--plots-root", type=Path, default=ROOT / "plots" / "performance")
    parser.add_argument("--update-report", action="store_true", help="Explicitly replace report/performance_evaluation.md.")
    parser.add_argument("--no-plots", action="store_true", help="Skip Matplotlib plots.")
    parser.add_argument("--allow-low-memory", action="store_true", help="Override the conservative memory guard.")
    return parser


def validate_args(parser: argparse.ArgumentParser, args: argparse.Namespace) -> None:
    if args.repetitions < 3:
        parser.error("--repetitions must be at least 3.")
    if args.warmups < 0 or args.timeout <= 0:
        parser.error("--warmups must be nonnegative and --timeout must be positive.")
    if args.max_iterations <= 0 or args.tolerance <= 0 or not 0 < args.damping < 1:
        parser.error("Use positive tolerance/iterations and a damping factor strictly between 0 and 1.")
    if args.comparison_tolerance <= 0 or not math.isfinite(args.comparison_tolerance):
        parser.error("--comparison-tolerance must be finite and positive.")
    if args.tolerance != DEFAULT_TOLERANCE:
        print(
            f"Warning: non-default tolerance {args.tolerance:g} supplied; "
            f"project default is {DEFAULT_TOLERANCE:g}.",
            file=sys.stderr,
        )


def requested_datasets(explicit: list[Path], include_full: bool) -> list[Path]:
    if explicit:
        paths = explicit
    else:
        paths = [
            Path("data/samples/livejournal_100MB.txt"),
            Path("data/samples/livejournal_500MB.txt"),
        ]
        if include_full:
            paths.append(Path("data/processed/livejournal_clean.txt"))
    resolved: list[Path] = []
    seen: set[Path] = set()
    for candidate in paths:
        path = candidate.expanduser()
        if not path.is_absolute():
            path = ROOT / path
        path = path.resolve()
        if path not in seen:
            resolved.append(path)
            seen.add(path)
    return resolved


def dataset_kind(path: Path) -> str:
    documented = DOCUMENTED_DATASETS.get(path.name)
    if documented:
        return documented["kind"]
    if path.name == "tiny_graph.txt":
        return "tiny_validation_fixture"
    return "custom_input"


def dataset_record(path: Path) -> dict[str, Any]:
    kind = dataset_kind(path)
    metadata = DOCUMENTED_DATASETS.get(path.name, {})
    record: dict[str, Any] = {
        "name": path.name,
        "path": str(path),
        "kind": kind,
        "state": "available" if path.is_file() else "missing_dataset",
        "bytes": path.stat().st_size if path.is_file() else None,
        "sha256": sha256_file(path) if path.is_file() else None,
        "expected_documentation": metadata,
        "validation": "not_run",
        "validation_notes": [],
    }
    if kind == "prefix_sample":
        record["validation_notes"].append(
            "Prefix of original edge ordering; observed node count is max ID plus one, not assumed to be the full-graph count."
        )
    elif kind == "full_cleaned_graph":
        record["validation_notes"].append(
            "Expected full cleaned directed LiveJournal graph; observed counts will be checked against project documentation."
        )
    return record


def check_dataset_resources(path: Path) -> tuple[bool, dict[str, Any]]:
    size = path.stat().st_size
    available = available_memory_bytes()
    estimated_working_set = max(MIN_MEMORY_RESERVE, size * 2)
    details = {
        "input_bytes": size,
        "available_system_memory_bytes": available if available is not None else "unavailable",
        "working_set_estimate_bytes": estimated_working_set,
        "working_set_estimate_is_measured": False,
        "minimum_memory_reserve_bytes": MIN_MEMORY_RESERVE,
    }
    if available is None:
        details["decision"] = "warning_memory_unavailable"
        print(f"Warning: available memory could not be determined for {path.name}.", file=sys.stderr)
        return True, details
    allowed = available >= estimated_working_set + MIN_MEMORY_RESERVE
    details["decision"] = "allowed" if allowed else "memory_aborted"
    return allowed, details


def make_run_directory(root: Path, run_id: str) -> Path:
    root.mkdir(parents=True, exist_ok=True)
    candidate = root / run_id
    suffix = 1
    while candidate.exists():
        candidate = root / f"{run_id}_{suffix}"
        suffix += 1
    candidate.mkdir()
    return candidate


def atomic_write_json(path: Path, value: Any) -> None:
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    with temporary.open("rb") as source:
        os.fsync(source.fileno())
    temporary.replace(path)


def initialize_raw_csv(path: Path) -> Any:
    handle = path.open("w", newline="", encoding="utf-8")
    csv.DictWriter(handle, fieldnames=RAW_FIELDS).writeheader()
    handle.flush()
    os.fsync(handle.fileno())
    return handle


def append_raw_row(handle: Any, row: dict[str, Any]) -> None:
    csv.DictWriter(handle, fieldnames=RAW_FIELDS, extrasaction="ignore").writerow(row)
    handle.flush()
    os.fsync(handle.fileno())


def cgroup_oom_kill_count() -> int | None:
    candidates = (
        Path("/sys/fs/cgroup/memory.events"),
        Path("/sys/fs/cgroup/memory/memory.oom_control"),
    )
    for path in candidates:
        try:
            values = {}
            for line in path.read_text(encoding="ascii").splitlines():
                parts = line.split()
                if len(parts) == 2:
                    values[parts[0]] = int(parts[1])
            if "oom_kill" in values:
                return values["oom_kill"]
            if "oom_kill_disable" in values and "under_oom" in values:
                return values["under_oom"]
        except (OSError, ValueError):
            continue
    return None


def parse_trial_status(
    parsed: dict[str, str],
    implementation: str,
    tolerance: float,
    comparison_tolerance: float,
) -> tuple[str, str]:
    try:
        if int(parsed["nodes"]) <= 0 or int(parsed["edges"]) <= 0:
            return "invalid_result", "invalid graph dimensions"
        if parsed["solver_converged"].lower() != "true":
            return "non_converged", "solver reached the iteration limit before meeting tolerance"
        if parsed["rank_sum_valid"].lower() != "true":
            return "rank_sum_invalid", "rank sum is outside the accepted tolerance"
        if implementation == "openmp":
            if int(parsed["actual_threads"]) <= 0:
                return "thread_mismatch", "OpenMP team size unavailable"
            if parsed["sequential_verification_converged"].lower() != "true":
                return "reference_non_converged", "sequential correctness reference did not converge"
            if parsed["sequential_verification_rank_sum_valid"].lower() != "true":
                return "reference_rank_sum_invalid", "sequential reference rank sum is invalid"
            if parsed["numerical_consistency"].lower() != "true":
                return "numerical_mismatch", (
                    f"maximum rank difference exceeds comparison tolerance {comparison_tolerance:g}"
                )
        return "success", ""
    except (KeyError, ValueError) as error:
        return "invalid_result", f"invalid harness output: {error}"


def run_one(
    executable: Path,
    dataset: dict[str, Any],
    implementation: str,
    threads: int,
    phase: str,
    repetition: int,
    order: int,
    damping: float,
    tolerance: float,
    max_iterations: int,
    comparison_tolerance: float,
    timeout: float,
    log_dir: Path,
    effective_omp: dict[str, str],
) -> dict[str, Any]:
    path = Path(dataset["path"])
    label = f"{path.stem}_{implementation}_{threads}t_{phase}_{repetition}"
    log_path = log_dir / f"{label}.log"
    command = [
        str(executable),
        implementation,
        str(path),
        str(damping),
        str(tolerance),
        str(max_iterations),
        str(threads),
        str(comparison_tolerance),
    ]
    started_at = utc_now()
    start = time.perf_counter()
    outcome = "failed"
    exit_status: int | str = ""
    parsed: dict[str, str] = {}
    process_output = ""
    oom_before = cgroup_oom_kill_count()
    try:
        completed = subprocess.run(
            command,
            cwd=ROOT,
            env={**os.environ, **effective_omp},
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            timeout=timeout,
            check=False,
        )
        process_output = completed.stdout
        exit_status = completed.returncode
        if completed.returncode != 0:
            oom_after = cgroup_oom_kill_count()
            if oom_before is not None and oom_after is not None and oom_after > oom_before:
                outcome = "memory_aborted"
                process_output += "\nCgroup OOM kill counter increased during this run.\n"
            elif completed.returncode < 0:
                outcome = "abnormal_exit"
                process_output += f"\nTerminated by signal {-completed.returncode}.\n"
            else:
                outcome = "failed"
        else:
            parsed = parse_harness_output(completed.stdout)
            if int(parsed["actual_threads"]) != threads:
                outcome = "thread_mismatch"
                process_output += f"\nExpected {threads} threads, observed {parsed['actual_threads']}.\n"
            else:
                outcome, reason = parse_trial_status(
                    parsed, implementation, tolerance, comparison_tolerance
                )
                if reason:
                    process_output += f"\nRun validation failed: {reason}\n"
    except subprocess.TimeoutExpired as error:
        outcome = "timed_out"
        partial = error.stdout or ""
        if isinstance(partial, bytes):
            partial = partial.decode("utf-8", errors="replace")
        process_output = str(partial) + f"\nBenchmark timed out after {timeout} seconds.\n"
    except (OSError, ValueError) as error:
        outcome = "failed"
        process_output += f"\nBenchmark runner error: {error}\n"
    process_wall = time.perf_counter() - start
    log_path.write_text(
        f"timestamp_utc={started_at}\ncommand={shlex.join(command)}\n"
        f"omp_environment={json.dumps(effective_omp, sort_keys=True)}\n"
        f"timeout_seconds={timeout}\noutcome={outcome}\nexit_status={exit_status}\n\n"
        f"{process_output}",
        encoding="utf-8",
    )
    row: dict[str, Any] = {
        "dataset": dataset["name"],
        "dataset_kind": dataset["kind"],
        "dataset_path": str(path),
        "dataset_bytes": dataset.get("bytes", ""),
        "dataset_sha256": dataset.get("sha256") or "",
        "nodes": parsed.get("nodes", ""),
        "edges": parsed.get("edges", ""),
        "implementation": implementation,
        "requested_threads": threads,
        "actual_threads": parsed.get("actual_threads", ""),
        "phase": phase,
        "repetition": repetition,
        "execution_order": order,
        "timestamp_utc": started_at,
        "solver_seconds": parsed.get("solver_seconds", ""),
        "average_iteration_seconds_derived": parsed.get("average_iteration_seconds", ""),
        "graph_load_seconds": parsed.get("graph_load_seconds", ""),
        "process_wall_seconds": f"{process_wall:.9f}",
        "peak_rss_kib": parsed.get("peak_rss_kib", ""),
        "iterations": parsed.get("solver_iterations", ""),
        "error": parsed.get("solver_error", ""),
        "converged": parsed.get("solver_converged", ""),
        "rank_sum": parsed.get("rank_sum", ""),
        "rank_sum_valid": parsed.get("rank_sum_valid", ""),
        "top10": parsed.get("top10", ""),
        "sequential_verification_iterations": parsed.get("sequential_verification_iterations", ""),
        "sequential_verification_error": parsed.get("sequential_verification_error", ""),
        "sequential_verification_converged": parsed.get("sequential_verification_converged", ""),
        "sequential_verification_rank_sum": parsed.get("sequential_verification_rank_sum", ""),
        "sequential_verification_top10": parsed.get("sequential_verification_top10", ""),
        "iteration_counts_match": parsed.get("iteration_counts_match", ""),
        "max_abs_difference": parsed.get("max_abs_difference", ""),
        "numerical_consistency": parsed.get("numerical_consistency", ""),
        "comparison_tolerance": parsed.get("comparison_tolerance", comparison_tolerance),
        "correctness_status": (
            "not_compared" if implementation == "sequential"
            else "pass" if outcome == "success"
            else "fail"
        ),
        "outcome": outcome,
        "exit_status": exit_status,
        "log_path": str(log_path),
    }
    print(
        f"{dataset['name']}: {implementation} {threads} thread(s), "
        f"{phase} {repetition}: {outcome}"
        + (f", solver={row['solver_seconds']} s" if row["solver_seconds"] else "")
    )
    return row


def synthetic_row(
    dataset: dict[str, Any],
    implementation: str,
    threads: int,
    phase: str,
    repetition: int,
    order: int,
    outcome: str,
    reason: str,
) -> dict[str, Any]:
    return {
        "dataset": dataset["name"],
        "dataset_kind": dataset["kind"],
        "dataset_path": dataset["path"],
        "dataset_bytes": dataset.get("bytes") or "",
        "dataset_sha256": dataset.get("sha256") or "",
        "nodes": "",
        "edges": "",
        "implementation": implementation,
        "requested_threads": threads,
        "actual_threads": "",
        "phase": phase,
        "repetition": repetition,
        "execution_order": order,
        "timestamp_utc": utc_now(),
        "solver_seconds": "",
        "average_iteration_seconds_derived": "",
        "graph_load_seconds": "",
        "process_wall_seconds": "",
        "peak_rss_kib": "",
        "iterations": "",
        "error": "",
        "converged": "",
        "rank_sum": "",
        "rank_sum_valid": "",
        "top10": "",
        "sequential_verification_iterations": "",
        "sequential_verification_error": "",
        "sequential_verification_converged": "",
        "sequential_verification_rank_sum": "",
        "sequential_verification_top10": "",
        "iteration_counts_match": "",
        "max_abs_difference": "",
        "numerical_consistency": "",
        "comparison_tolerance": "",
        "correctness_status": "not_run",
        "outcome": outcome,
        "exit_status": "",
        "log_path": reason,
    }


def append_unstarted_attempts(
    schedule: list[dict[str, Any]],
    rows: list[dict[str, Any]],
    raw_handle: Any,
    manifest: dict[str, Any],
    reason: str,
) -> None:
    recorded_orders = {int(row["execution_order"]) for row in rows if row.get("execution_order")}
    for item in schedule:
        if item["order"] in recorded_orders:
            continue
        row = synthetic_row(
            item["dataset"],
            item["implementation"],
            item["threads"],
            item["phase"],
            item["repetition"],
            item["order"],
            reason,
            "attempt not started; completed rows remain preserved",
        )
        rows.append(row)
        append_raw_row(raw_handle, row)
        recorded_orders.add(item["order"])
        manifest["completed_attempts"] += 1
        manifest["last_completed_order"] = item["order"]
        manifest["last_outcome"] = reason
        atomic_write_json(Path(manifest["run_directory"]) / "run_manifest.json", manifest)


def sample_cv(values: list[float]) -> float | None:
    if len(values) < 2:
        return None
    mean = statistics.mean(values)
    if mean == 0:
        return None
    return statistics.stdev(values) / mean


def summarize_rows(
    rows: list[dict[str, Any]],
    repetitions: int,
    datasets: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    by_dataset = {dataset["name"]: dataset for dataset in datasets}
    for dataset_name, dataset in by_dataset.items():
        measured = [
            row for row in rows
            if row["dataset"] == dataset_name and row["phase"] == "measured"
        ]
        stats: dict[tuple[str, int], dict[str, Any]] = {}
        for implementation, threads in CONFIGURATIONS:
            attempts = [
                row for row in measured
                if row["implementation"] == implementation
                and int(row["requested_threads"]) == threads
            ]
            successes = [row for row in attempts if row["outcome"] == "success"]
            values = [float(row["solver_seconds"]) for row in successes]
            complete = (
                len(successes) == repetitions
                and len(attempts) == repetitions
                and dataset["state"] not in ("dataset_validation_mismatch", "memory_aborted")
            )
            median = statistics.median(values) if complete else None
            failures = sorted({row["outcome"] for row in attempts if row["outcome"] != "success"})
            status = "complete" if complete else (
                dataset["state"] if dataset["state"] in ("dataset_validation_mismatch", "memory_aborted") else
                ",".join(failures) if failures else
                "incomplete_repetitions" if attempts else dataset["state"]
            )
            rss_values = [
                float(row["peak_rss_kib"]) for row in successes if row.get("peak_rss_kib")
                and row["peak_rss_kib"] != "unavailable"
            ]
            stats[(implementation, threads)] = {
                "successful_repetitions": len(successes),
                "attempted_repetitions": len(attempts),
                "required_repetitions": repetitions,
                "median_seconds": median,
                "minimum_seconds": min(values) if values else None,
                "maximum_seconds": max(values) if values else None,
                "coefficient_of_variation": sample_cv(values),
                "median_peak_rss_kib": statistics.median(rss_values) if rss_values else None,
                "minimum_peak_rss_kib": min(rss_values) if rss_values else None,
                "maximum_peak_rss_kib": max(rss_values) if rss_values else None,
                "complete": complete,
                "status": status,
                "failed_outcomes": failures,
                "unstable": sample_cv(values) is not None and sample_cv(values) > 0.1,
                "nodes": next((row.get("nodes") for row in attempts if row.get("nodes")), ""),
                "edges": next((row.get("edges") for row in attempts if row.get("edges")), ""),
            }
        seq = stats[("sequential", 1)]
        openmp_times = {
            threads: stats[("openmp", threads)]["median_seconds"]
            for threads in THREAD_COUNTS
        }
        metrics: dict[int, dict[str, Any]] = {}
        if seq["median_seconds"] is not None:
            metrics = calculate_metrics(seq["median_seconds"], openmp_times)
        for implementation, threads in CONFIGURATIONS:
            row = {
                "dataset": dataset_name,
                "dataset_kind": dataset["kind"],
                "implementation": implementation,
                "threads": threads,
                **stats[(implementation, threads)],
                **metrics.get(threads, {
                    "sequential_speedup": None,
                    "openmp_self_speedup": None,
                    "efficiency": None,
                    "karp_flatt_p2": None,
                    "karp_flatt_status": "unavailable",
                    "amdahl_prediction_from_p2": None,
                    "amdahl_prediction_difference": None,
                    "gustafson_illustration_from_p2": None,
                }),
            }
            result.append(row)
    return result


SUMMARY_FIELDS = (
    "dataset", "dataset_kind", "implementation", "threads", "successful_repetitions",
    "attempted_repetitions", "required_repetitions", "median_seconds", "minimum_seconds",
    "maximum_seconds", "coefficient_of_variation", "median_peak_rss_kib",
    "minimum_peak_rss_kib", "maximum_peak_rss_kib", "unstable", "complete", "status",
    "failed_outcomes", "nodes", "edges", "sequential_speedup", "openmp_self_speedup",
    "efficiency", "karp_flatt_p2", "karp_flatt_status",
    "amdahl_prediction_from_p2", "amdahl_prediction_difference",
    "gustafson_illustration_from_p2",
)


def write_summaries(run_dir: Path, rows: list[dict[str, Any]], repetitions: int, datasets: list[dict[str, Any]]) -> list[dict[str, Any]]:
    summaries = summarize_rows(rows, repetitions, datasets)
    csv_path = run_dir / "summary.csv"
    temporary = csv_path.with_suffix(".csv.tmp")
    with temporary.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=SUMMARY_FIELDS, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(summaries)
        destination.flush()
        os.fsync(destination.fileno())
    temporary.replace(csv_path)
    atomic_write_json(run_dir / "metrics.json", summaries)
    return summaries


def record_dataset_validation(dataset: dict[str, Any], rows: list[dict[str, Any]]) -> None:
    observed = [row for row in rows if row["dataset"] == dataset["name"] and row["nodes"] and row["edges"]]
    if not observed:
        dataset["validation"] = "not_verified"
        return
    nodes = int(observed[0]["nodes"])
    edges = int(observed[0]["edges"])
    observed_bytes = int(dataset["bytes"])
    expected = dataset["expected_documentation"]
    notes: list[str] = list(dataset["validation_notes"])
    matches = True
    if expected.get("expected_edges") is not None and edges != expected["expected_edges"]:
        matches = False
        notes.append(f"Observed {edges:,} directed records; documentation lists {expected['expected_edges']:,}.")
    if expected.get("expected_nodes") is not None and nodes != expected["expected_nodes"]:
        matches = False
        notes.append(f"Observed {nodes:,} nodes; documentation lists {expected['expected_nodes']:,}.")
    if expected.get("expected_bytes") is not None and observed_bytes != expected["expected_bytes"]:
        notes.append(
            f"Observed size {observed_bytes:,} bytes differs from documented reference "
            f"{expected['expected_bytes']:,}; check preprocessing/version."
        )
    if dataset["kind"] == "prefix_sample":
        notes.append(f"Observed node count is {nodes:,} (max vertex ID + 1 in this graph), not assumed full-graph node count.")
    if dataset["kind"] == "tiny_validation_fixture":
        notes.append("Fixture run is workflow validation only; not a LiveJournal experiment.")
    dataset["observed_nodes"] = nodes
    dataset["observed_directed_edges"] = edges
    dataset["validation_notes"] = list(dict.fromkeys(notes))
    dataset["validation"] = "matches_documented_counts" if matches else "count_mismatch"
    if not matches:
        dataset["state"] = "dataset_validation_mismatch"


def markdown_number(value: Any, digits: int = 6) -> str:
    if value is None or value == "":
        return "Unavailable"
    try:
        number = float(value)
    except (TypeError, ValueError):
        return str(value)
    return f"{number:.{digits}g}" if math.isfinite(number) else "Unavailable"


def markdown_cell(value: Any) -> str:
    return str(value).replace("|", r"\|").replace("\r\n", "\n").replace("\n", "<br>")


def write_plots(summaries: list[dict[str, Any]], plots_dir: Path) -> list[str]:
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.patches import Patch
    except ImportError as error:
        raise RuntimeError(
            "Matplotlib is required to generate plots. Install benchmarks/requirements.txt."
        ) from error

    generated: list[str] = []
    for dataset in sorted({row["dataset"] for row in summaries}):
        rows = [row for row in summaries if row["dataset"] == dataset]
        seq = next((row for row in rows if row["implementation"] == "sequential"), None)
        parallel = sorted(
            (row for row in rows if row["implementation"] == "openmp"),
            key=lambda row: row["threads"],
        )
        has_runtime_data = (
            seq is not None and seq["median_seconds"] is not None
        ) or any(row["median_seconds"] is not None for row in parallel)
        if not parallel or not has_runtime_data:
            continue
        plots_dir.mkdir(parents=True, exist_ok=True)
        stem = re.sub(r"[^A-Za-z0-9_.-]+", "_", Path(dataset).stem)
        x = [row["threads"] for row in parallel]
        status_text = [
            f"{row['threads']} thread(s): {row['status']}"
            for row in parallel if row["median_seconds"] is None
        ]

        def finish_plot(figure: Any, axis: Any, filename: str) -> None:
            if status_text:
                axis.text(
                    0.01,
                    -0.25,
                    "Unavailable configurations: " + "; ".join(status_text),
                    transform=axis.transAxes,
                    va="top",
                    fontsize=8,
                )
                figure.subplots_adjust(bottom=0.28)
            else:
                figure.tight_layout()
            target = plots_dir / f"{stem}_{filename}.png"
            figure.savefig(target, dpi=160, bbox_inches="tight")
            plt.close(figure)
            generated.append(str(target))

        figure, axis = plt.subplots(figsize=(7, 4.5))
        valid = [row for row in parallel if row["median_seconds"] is not None]
        if valid:
            axis.errorbar(
                [row["threads"] for row in valid],
                [row["median_seconds"] for row in valid],
                yerr=[
                    [row["median_seconds"] - row["minimum_seconds"] for row in valid],
                    [row["maximum_seconds"] - row["median_seconds"] for row in valid],
                ],
                marker="o",
                capsize=4,
                label="OpenMP median (min–max)",
            )
            if seq and seq["median_seconds"] is not None:
                axis.axhline(seq["median_seconds"], linestyle="--", label="Sequential median")
        for row in parallel:
            if row["median_seconds"] is None:
                axis.scatter(row["threads"], 0, marker="x", color="red")
        axis.set(title=f"Solver runtime — {dataset}", xlabel="OpenMP threads", ylabel="Solver runtime (s)")
        axis.set_xticks(x)
        axis.grid(True, alpha=0.3)
        if axis.get_legend_handles_labels()[0]:
            axis.legend()
        finish_plot(figure, axis, "runtime")

        for metric, title, ylabel, filename, ideal in (
            ("sequential_speedup", "Sequential speedup", "Speedup (ratio)", "speedup", True),
            ("openmp_self_speedup", "OpenMP self-relative speedup", "Speedup (ratio)", "openmp_speedup", True),
            ("efficiency", "Parallel efficiency", "Efficiency (ratio)", "efficiency", False),
        ):
            figure, axis = plt.subplots(figsize=(7, 4.5))
            points = [row for row in parallel if row[metric] is not None]
            if points:
                axis.plot(
                    [row["threads"] for row in points],
                    [row[metric] for row in points],
                    marker="o",
                    label=metric.replace("_", " "),
                )
            if ideal:
                axis.plot(x, x, linestyle="--", color="gray", label="Ideal linear scaling")
            if metric == "efficiency":
                axis.axhline(1.0, linestyle="--", color="gray", label="Ideal efficiency")
            for row in parallel:
                if row[metric] is None:
                    axis.scatter(row["threads"], 0, marker="x", color="red")
            axis.set(title=f"{title} — {dataset}", xlabel="OpenMP threads", ylabel=ylabel)
            axis.set_xticks(x)
            axis.grid(True, alpha=0.3)
            if axis.get_legend_handles_labels()[0]:
                axis.legend()
            finish_plot(figure, axis, filename)

        figure, axis = plt.subplots(figsize=(8, 4.5))
        valid = [row for row in parallel if row["median_seconds"] is not None]
        labels = (["Sequential"] if seq and seq["median_seconds"] is not None else []) + [
            f"OpenMP {row['threads']}t" for row in valid
        ]
        values = ([seq["median_seconds"]] if seq and seq["median_seconds"] is not None else []) + [
            row["median_seconds"] for row in valid
        ]
        if values:
            axis.bar(labels, values, color=["tab:gray"] + ["tab:blue"] * (len(values) - 1))
            axis.legend(handles=[
                Patch(facecolor="tab:gray", label="Sequential"),
                Patch(facecolor="tab:blue", label="OpenMP"),
            ])
        axis.set(title=f"Sequential and OpenMP runtime — {dataset}", xlabel="Implementation", ylabel="Solver runtime (s)")
        axis.tick_params(axis="x", rotation=20)
        axis.grid(axis="y", alpha=0.3)
        finish_plot(figure, axis, "comparison")

        figure, axis = plt.subplots(figsize=(7, 4.5))
        prediction_rows = [
            row for row in parallel
            if row["threads"] in (4, 8)
            and row["sequential_speedup"] is not None
            and row["amdahl_prediction_from_p2"] is not None
        ]
        if prediction_rows:
            axis.plot(
                [row["threads"] for row in prediction_rows],
                [row["sequential_speedup"] for row in prediction_rows],
                marker="o",
                label="Measured sequential speedup",
            )
            axis.plot(
                [row["threads"] for row in prediction_rows],
                [row["amdahl_prediction_from_p2"] for row in prediction_rows],
                marker="s",
                linestyle="--",
                label="Amdahl prediction from P=2 estimate",
            )
        else:
            axis.text(0.5, 0.5, "Amdahl projections unavailable", ha="center", va="center", transform=axis.transAxes)
        axis.set(title=f"Amdahl model comparison — {dataset}", xlabel="OpenMP threads", ylabel="Speedup (ratio)")
        axis.set_xticks([4, 8])
        axis.grid(True, alpha=0.3)
        if axis.get_legend_handles_labels()[0]:
            axis.legend()
        finish_plot(figure, axis, "amdahl")

        figure, axis = plt.subplots(figsize=(6, 4))
        p2 = next((row for row in parallel if row["threads"] == 2), None)
        if p2 and p2["karp_flatt_p2"] is not None:
            axis.bar(["P=2 estimate"], [p2["karp_flatt_p2"]], color="tab:purple")
            axis.axhspan(0, 1, color="green", alpha=0.08, label="Plausible [0, 1]")
            axis.set_ylim(min(-0.1, p2["karp_flatt_p2"] - 0.1), max(1.1, p2["karp_flatt_p2"] + 0.1))
        else:
            axis.text(0.5, 0.5, "Karp–Flatt estimate unavailable", ha="center", va="center", transform=axis.transAxes)
        axis.set(title=f"Karp–Flatt effective serial fraction — {dataset}", ylabel="Estimated fraction")
        axis.grid(axis="y", alpha=0.3)
        if axis.get_legend_handles_labels()[0]:
            axis.legend()
        finish_plot(figure, axis, "karp_flatt")

    datasets_with_results = sorted({row["dataset"] for row in summaries})
    if len(datasets_with_results) > 1:
        for metric, title, ylabel, filename in (
            ("median_seconds", "Comparable runtime across datasets", "Solver runtime (s)", "combined_runtime"),
            ("sequential_speedup", "Comparable speedup across datasets", "Speedup (ratio)", "combined_speedup"),
        ):
            figure, axis = plt.subplots(figsize=(8, 5))
            for dataset in datasets_with_results:
                points = sorted(
                    (
                        row for row in summaries
                        if row["dataset"] == dataset
                        and row["implementation"] == "openmp"
                        and row[metric] is not None
                    ),
                    key=lambda row: row["threads"],
                )
                if points:
                    axis.plot(
                        [row["threads"] for row in points],
                        [row[metric] for row in points],
                        marker="o",
                        label=dataset,
                    )
                else:
                    axis.plot([], [], marker="x", linestyle="none", label=f"{dataset} (no complete runs)")
            if metric == "sequential_speedup":
                axis.plot(THREAD_COUNTS, THREAD_COUNTS, linestyle="--", color="gray", label="Ideal linear scaling")
            axis.set(title=title, xlabel="OpenMP threads", ylabel=ylabel)
            axis.set_xticks(THREAD_COUNTS)
            axis.grid(True, alpha=0.3)
            axis.legend()
            target = plots_dir / f"{filename}.png"
            figure.tight_layout()
            figure.savefig(target, dpi=160, bbox_inches="tight")
            plt.close(figure)
            generated.append(str(target))
    return generated


def generate_report(
    report_path: Path,
    run_id: str,
    datasets: list[dict[str, Any]],
    summaries: list[dict[str, Any]],
    environment: dict[str, Any],
    run_dir: Path,
    plots: list[str],
    parameters: dict[str, Any],
    run_status: str,
) -> None:
    lines = [
        "# PageRank Performance Evaluation",
        "",
        f"**Run:** `{run_id}`  ",
        f"**Experiment status:** `{run_status}`  ",
        f"**Report category:** {'tiny-fixture workflow validation only' if datasets and all(d['kind'] == 'tiny_validation_fixture' for d in datasets) else 'LiveJournal experiment or incomplete experiment'}",
        "",
        "## Purpose and methodology",
        "",
        "Compare sequential PageRank against OpenMP at 1, 2, 4, and 8 requested threads. Solver runtime is timed with `steady_clock`; graph loading is timed separately, and process wall time includes graph loading plus any correctness-reference work. `average_iteration_seconds_derived` is solver time divided by iterations, not direct per-iteration instrumentation. Compilation is excluded.",
        "",
        f"Parameters: damping `{parameters['damping']}`, tolerance `{parameters['tolerance']}`, maximum iterations `{parameters['max_iterations']}`, warm-ups `{parameters['warmups']}`, measured repetitions `{parameters['repetitions']}`, comparison tolerance `{parameters['comparison_tolerance']}`. "
        + ("The tolerance differs from the project benchmark default and is recorded explicitly." if parameters["tolerance"] != DEFAULT_TOLERANCE else "The tolerance is the required default."),
        "",
        "Warm-ups are excluded from statistics. Configuration order is reproducibly interleaved by random seed to reduce systematic thermal/frequency bias. Medians are primary; min/max and sample coefficient of variation identify variability. Five measured repetitions are recommended for final 100/500 MiB experiments.",
        "",
        "Convergence requires final L1 error below the supplied tolerance before the iteration limit. Rank sums are checked against 1.0. Each OpenMP process also computes a sequential reference on the same loaded graph and reports maximum absolute rank difference, top-10 rankings, convergence statuses, and iteration counts. Iteration-count differences are recorded but are not alone deemed incorrect. Comparison tolerance is explicit in the run metadata.",
        "",
        "## Experimental environment",
        "",
        "| Property | Value |",
        "|---|---|",
        f"| OS / kernel | {markdown_cell(environment.get('operating_system'))} / {markdown_cell(environment.get('kernel'))} |",
        f"| Linux distribution | {markdown_cell(environment.get('linux_distribution'))} |",
        f"| WSL detected / version | {markdown_cell(environment.get('wsl_detected'))} / {markdown_cell(environment.get('wsl_version'))} |",
        f"| CPU | {markdown_cell(environment.get('cpu_model'))} |",
        f"| Physical cores / logical processors | {markdown_cell(environment.get('physical_core_count'))} / {markdown_cell(environment.get('logical_processor_count'))} |",
        f"| SMT status | {markdown_cell(environment.get('smt_status'))} |",
        f"| Available system memory | {markdown_cell(environment.get('available_system_memory_gib'))} GiB |",
        f"| Compiler | {markdown_cell(environment.get('compiler_version'))} |",
        f"| Python | {markdown_cell(environment.get('python_version'))} |",
        f"| CPU governor | {markdown_cell(environment.get('cpu_governor'))} |",
        f"| WSL memory configuration | {markdown_cell(environment.get('wsl_memory_configuration'))} |",
        f"| Git branch / commit / dirty | {markdown_cell(environment['git']['branch'])} / `{markdown_cell(environment['git']['commit'])}` / {markdown_cell(environment['git']['working_tree_dirty'])} |",
        f"| Effective OpenMP environment | `{markdown_cell(json.dumps(environment['omp_environment'], sort_keys=True))}` |",
        "",
        "Peak RSS is measured per harness process via Linux `getrusage(RUSAGE_SELF)` and reported in KiB. It is the process high-water mark including graph loading and, for OpenMP trials, the sequential correctness check; it is not system-wide memory or solver-only memory. `unavailable` is reported on unsupported platforms.",
        "",
        "## Dataset validation",
        "",
        "| Dataset | Type | State | Size (bytes) | Observed nodes | Directed edges | Validation | SHA-256 |",
        "|---|---|---|---:|---:|---:|---|---|",
    ]
    if datasets:
        lines.extend(
            f"| {d['name']} | {d['kind']} | {d['state']} | {d.get('bytes') or 'Unavailable'} | "
            f"{d.get('observed_nodes', 'Unavailable')} | {d.get('observed_directed_edges', 'Unavailable')} | "
            f"{d.get('validation', 'not_run')} | `{d.get('sha256') or 'Unavailable'}` |"
            for d in datasets
        )
        for dataset in datasets:
            for note in dataset.get("validation_notes", []):
                lines.append(f"- **{dataset['name']}:** {note}")
    else:
        lines.append("| None | — | missing_dataset | — | — | — | Not run | — |")
    lines.extend(
        [
            "",
            "The documentation gives 8,015,157 and 37,672,977 edges for the 100 and 500 MiB prefixes, and 4,847,571 nodes / 68,993,773 directed edges for the full graph. Prefix node count is the observed maximum vertex ID plus one and is not assumed to equal the full graph node count. The loader stores incoming adjacency while retaining directed edge orientation; observed edge count is checked against the number of records loaded. Prefix sizes/order may alter graph structure and are not random samples.",
            "",
            "## Configuration results",
            "",
            "| Dataset | Impl. | Threads | Successful / required | Status | Median solver (s) | Min (s) | Max (s) | CV (ratio) | Unstable (CV > 0.1) | Median peak RSS (KiB) | Convergence / correctness |",
            "|---|---|---:|---:|---|---:|---:|---:|---:|---|---:|---|",
        ]
    )
    for summary in summaries:
        lines.append(
            f"| {summary['dataset']} | {summary['implementation']} | {summary['threads']} | "
            f"{summary['successful_repetitions']} / {summary['required_repetitions']} | {summary['status']} | "
            f"{markdown_number(summary['median_seconds'])} | {markdown_number(summary['minimum_seconds'])} | "
            f"{markdown_number(summary['maximum_seconds'])} | {markdown_number(summary['coefficient_of_variation'])} | "
            f"{summary['unstable']} | {markdown_number(summary['median_peak_rss_kib'])} | {summary['status']} |"
        )
    if not summaries:
        lines.append("| No configurations | — | — | 0 / 0 | not_run | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | not_run |")
    lines.extend(
        [
            "",
            "Per-run convergence, final error, iterations, rank sum, deterministic top-10, requested/actual threads, numerical difference, process wall time, graph-load time, and peak RSS are recorded in `raw_runs.csv`. Non-converged, failed, timed-out, memory-aborted, and not-started configurations remain visible in raw and summary outputs.",
            "",
            "## Performance metrics",
            "",
            "Sequential speedup is `T_seq / T_omp(P)`. OpenMP self-relative speedup is `T_omp(1) / T_omp(P)`. Efficiency is sequential speedup divided by P. Values are calculated only from complete successful medians. A serial fraction is estimated from P=2 only. Amdahl predictions at P=4 and P=8 use that P=2 estimate, so the calibration point is not repeated as purported independent prediction. Values outside [0,1] are flagged and not used for projections. Gustafson values are illustrative theory; fixed-size runs do not validate scaled speedup. A solver-only serial fraction need not describe the end-to-end application.",
            "",
            "| Dataset | Threads | Sequential speedup | OpenMP self-speedup | Efficiency | Karp–Flatt s (from P=2) | Amdahl prediction from P=2 | Measured − predicted | Gustafson illustration | Estimate status |",
            "|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
        ]
    )
    for summary in summaries:
        if summary["implementation"] != "openmp":
            continue
        lines.append(
            f"| {summary['dataset']} | {summary['threads']} | {markdown_number(summary['sequential_speedup'])} | "
            f"{markdown_number(summary['openmp_self_speedup'])} | {markdown_number(summary['efficiency'])} | "
            f"{markdown_number(summary['karp_flatt_p2'])} | {markdown_number(summary['amdahl_prediction_from_p2'])} | "
            f"{markdown_number(summary['amdahl_prediction_difference'])} | "
            f"{markdown_number(summary['gustafson_illustration_from_p2'])} | {summary['karp_flatt_status']} |"
        )
    if not any(s["implementation"] == "openmp" for s in summaries):
        lines.append("| No OpenMP measurements | — | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | unavailable |")
    lines.extend(
        [
            "",
            "## Figures",
            "",
        ]
    )
    if plots:
        lines.extend(
            f"![{Path(plot).stem}]({Path(os.path.relpath(plot, report_path.parent)).as_posix()})"
            for plot in plots
        )
    else:
        lines.append("No plots were generated because no successful measured data points were available.")
    lines.extend(
        [
            "",
            "Plots include min–max runtime ranges, sequential and OpenMP self-relative speedup (with ideal linear references), efficiency, comparison bars, P=2 Karp–Flatt estimate, and Amdahl projections versus measured P=4/P=8 speedup. Failed configurations are labeled rather than silently omitted.",
            "",
            "## Limitations and interpretation",
            "",
            "- Sequential and OpenMP CLI/API defaults are currently `1e-8`; the benchmark explicitly supplies the project-required `1e-6` unless overridden. Teammate source files were not changed.",
            "- The benchmark times solver calls, excluding edge-list parsing; process wall includes graph load and correctness-reference work.",
            "- OpenMP's static contiguous node partition can have load imbalance for skewed in-degree distributions; no scheduling implementation was changed.",
            "- Frequency scaling, cache state, system load, WSL resource limits, and SMT can influence observed timing.",
            "- Full LiveJournal data is memory intensive. Guard estimates are heuristics, not measured RSS.",
            "- Amdahl and Gustafson are models, not measured speedup; Gustafson scaled behavior is not tested.",
            "",
            f"Full raw data, environment, manifest, and build logs are in `{run_dir.as_posix()}`. "
            "No dataset, missing result, or tiny-fixture timing should be presented as a completed LiveJournal experiment.",
            "",
        ]
    )
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text("\n".join(lines), encoding="utf-8")


def write_raw_output_rows(handle: Any, rows: list[dict[str, Any]]) -> None:
    for row in rows:
        append_raw_row(handle, row)


def make_schedule(
    datasets: list[dict[str, Any]],
    warmups: int,
    repetitions: int,
    seed: int,
) -> list[dict[str, Any]]:
    generator = random.Random(seed)
    schedule: list[dict[str, Any]] = []
    order = 0
    for dataset in datasets:
        for phase, count in (("warmup", warmups), ("measured", repetitions)):
            for repetition in range(1, count + 1):
                configurations = list(CONFIGURATIONS)
                generator.shuffle(configurations)
                for implementation, threads in configurations:
                    order += 1
                    schedule.append(
                        {
                            "dataset": dataset,
                            "phase": phase,
                            "repetition": repetition,
                            "implementation": implementation,
                            "threads": threads,
                            "order": order,
                        }
                    )
    return schedule


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    validate_args(parser, args)
    if args.tolerance != DEFAULT_TOLERANCE:
        tolerance_note = "non_default_tolerance"
    else:
        tolerance_note = "project_default_tolerance"

    run_id = unique_run_id()
    output_root = args.output_root if args.output_root.is_absolute() else ROOT / args.output_root
    plots_root = args.plots_root if args.plots_root.is_absolute() else ROOT / args.plots_root
    run_dir = make_run_directory(output_root, run_id)
    logs_dir = run_dir / "logs"
    logs_dir.mkdir()
    raw_handle = initialize_raw_csv(run_dir / "raw_runs.csv")

    requested = requested_datasets(args.dataset, args.include_full)
    datasets = [dataset_record(path) for path in requested]
    missing = [dataset for dataset in datasets if dataset["state"] == "missing_dataset"]
    full_requested = any(dataset["kind"] == "full_cleaned_graph" for dataset in datasets)
    for dataset in datasets:
        if dataset["state"] == "available":
            if dataset["kind"] == "full_cleaned_graph" and not args.include_full:
                dataset["state"] = "not_run_requires_include_full"
            elif dataset["bytes"] > LARGE_DATASET_THRESHOLD and not args.include_full:
                dataset["state"] = "not_run_requires_include_full"
            else:
                allowed, resources = check_dataset_resources(Path(dataset["path"]))
                dataset["resource_check"] = resources
                if not allowed and not args.allow_low_memory:
                    dataset["state"] = "memory_aborted"
    effective_omp = {
        key: value for key, value in os.environ.items() if key.startswith("OMP_")
    }
    effective_omp.update(
        {
            "OMP_DYNAMIC": "FALSE",
            "OMP_NUM_THREADS": "requested-per-run",
            "OMP_PLACES": "cores",
            "OMP_PROC_BIND": "close",
        }
    )
    effective_omp["OMP_NUM_THREADS"] = "per-run requested team size"
    metadata = environment_metadata(
        None,
        None,
        "-std=c++17 -O3 -fopenmp",
        args.repetitions,
        args.warmups,
        args.seed,
        args.damping,
        args.tolerance,
        args.max_iterations,
        args.comparison_tolerance,
        effective_omp,
        run_id,
    )
    metadata["tolerance_note"] = tolerance_note
    metadata["requested_datasets"] = datasets
    metadata["execution_order"] = []
    metadata["resource_guard_override"] = args.allow_low_memory
    metadata["report_updated_explicitly"] = args.update_report
    atomic_write_json(run_dir / "environment.json", metadata)
    manifest: dict[str, Any] = {
        "run_id": run_id,
        "status": "running",
        "started_at_utc": utc_now(),
        "completed_attempts": 0,
        "requested_attempts": sum(
            (args.warmups + args.repetitions) * len(CONFIGURATIONS)
            for dataset in datasets if dataset["state"] == "available"
        ),
        "missing_datasets": [dataset["path"] for dataset in missing],
        "run_directory": str(run_dir),
    }
    atomic_write_json(run_dir / "run_manifest.json", manifest)
    rows: list[dict[str, Any]] = []
    status = "incomplete"
    exit_code = 0

    try:
        if requested and not datasets:
            raise RuntimeError("No requested datasets were recorded.")

        compiler: str | None = None
        compiler_version: str | None = None
        executable = ROOT / "build" / (
            "performance_harness.exe" if os.name == "nt" else "performance_harness"
        )
        build_status = "not_needed"
        available_data = [d for d in datasets if d["state"] == "available"]
        if available_data:
            resolved = shutil.which(args.compiler)
            if not resolved:
                build_status = "build_failed"
                manifest["build_error"] = f"C++ compiler not found: {args.compiler}"
            else:
                compiler = resolved
                try:
                    version_run = subprocess.run(
                        [compiler, "--version"],
                        check=True,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                    )
                    compiler_version = version_run.stdout.splitlines()[0]
                except (OSError, subprocess.CalledProcessError) as error:
                    build_status = "build_failed"
                    manifest["build_error"] = str(error)
                if build_status != "build_failed":
                    executable.parent.mkdir(exist_ok=True)
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
                    started = time.perf_counter()
                    compiled = subprocess.run(
                        compile_command,
                        cwd=ROOT,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.STDOUT,
                        check=False,
                    )
                    build_seconds = time.perf_counter() - started
                    (run_dir / "build.log").write_text(
                        f"command={shlex.join(compile_command)}\n"
                        f"compile_seconds={build_seconds:.9f}\n"
                        f"exit_status={compiled.returncode}\n\n{compiled.stdout}",
                        encoding="utf-8",
                    )
                    build_status = "success" if compiled.returncode == 0 else "build_failed"
                    if build_status == "build_failed":
                        manifest["build_error"] = compiled.stdout[-4000:]
                        exit_code = 1
            manifest["build_status"] = build_status
            metadata["compiler"] = compiler or "unavailable"
            metadata["compiler_version"] = compiler_version or "unavailable"
            metadata["compiler_flags"] = "-std=c++17 -O3 -fopenmp"
            atomic_write_json(run_dir / "environment.json", metadata)

        schedule = make_schedule(datasets, args.warmups, args.repetitions, args.seed)
        manifest["requested_attempts"] = len(schedule)
        metadata["execution_order"] = [
            {
                "order": item["order"],
                "dataset": item["dataset"]["name"],
                "phase": item["phase"],
                "repetition": item["repetition"],
                "implementation": item["implementation"],
                "threads": item["threads"],
            }
            for item in schedule
        ]
        atomic_write_json(run_dir / "environment.json", metadata)

        for item in schedule:
            dataset = item["dataset"]
            if dataset["state"] == "missing_dataset":
                row = synthetic_row(
                    dataset, item["implementation"], item["threads"], item["phase"],
                    item["repetition"], item["order"], "missing_dataset", "input file missing",
                )
            elif dataset["state"] == "memory_aborted":
                row = synthetic_row(
                    dataset, item["implementation"], item["threads"], item["phase"],
                    item["repetition"], item["order"], "memory_aborted",
                    "conservative resource check failed; prior run data retained",
                )
            elif dataset["state"] != "available":
                row = synthetic_row(
                    dataset, item["implementation"], item["threads"], item["phase"],
                    item["repetition"], item["order"], dataset["state"],
                    "explicit full-dataset opt-in required",
                )
            elif build_status != "success":
                row = synthetic_row(
                    dataset, item["implementation"], item["threads"], item["phase"],
                    item["repetition"], item["order"], "build_failed",
                    manifest.get("build_error", "harness build failed"),
                )
            else:
                row = run_one(
                    executable,
                    dataset,
                    item["implementation"],
                    item["threads"],
                    item["phase"],
                    item["repetition"],
                    item["order"],
                    args.damping,
                    args.tolerance,
                    args.max_iterations,
                    args.comparison_tolerance,
                    args.timeout,
                    logs_dir,
                    {
                        **{
                            key: value for key, value in os.environ.items()
                            if key.startswith("OMP_")
                        },
                        "OMP_DYNAMIC": "FALSE",
                        "OMP_NUM_THREADS": str(item["threads"]),
                        "OMP_PLACES": "cores",
                        "OMP_PROC_BIND": "close",
                    },
                )
            rows.append(row)
            append_raw_row(raw_handle, row)
            manifest["completed_attempts"] += 1
            manifest["last_completed_order"] = item["order"]
            manifest["last_outcome"] = row["outcome"]
            atomic_write_json(run_dir / "run_manifest.json", manifest)
            write_summaries(run_dir, rows, args.repetitions, datasets)
            for record in datasets:
                record_dataset_validation(record, rows)
            atomic_write_json(run_dir / "dataset_metadata.json", datasets)
    except KeyboardInterrupt:
        status = "interrupted"
        exit_code = 130
        if "schedule" in locals():
            append_unstarted_attempts(
                schedule, rows, raw_handle, manifest, "not_run_interrupted"
            )
        print("Benchmark interrupted; completed raw rows were flushed to disk.", file=sys.stderr)
    except (OSError, RuntimeError) as error:
        status = "failed"
        exit_code = 1
        manifest["fatal_error"] = str(error)
        if "schedule" in locals():
            append_unstarted_attempts(
                schedule, rows, raw_handle, manifest, "not_run_after_error"
            )
        print(f"Benchmark setup/execution error: {error}", file=sys.stderr)
    finally:
        raw_handle.close()
        summaries = write_summaries(run_dir, rows, args.repetitions, datasets)
        for record in datasets:
            record_dataset_validation(record, rows)
        atomic_write_json(run_dir / "dataset_metadata.json", datasets)
        if status == "incomplete":
            failures = [
                row for row in rows
                if row["outcome"] != "success" and row["phase"] == "measured"
            ]
            missing_or_guarded = any(
                dataset["state"] != "available" for dataset in datasets
            )
            expected_trials = len(schedule) if "schedule" in locals() else 0
            if manifest.get("completed_attempts", 0) < expected_trials:
                status = "interrupted"
            elif missing_or_guarded or failures or build_status == "build_failed":
                status = "incomplete"
                exit_code = 1
            elif datasets and all(d["kind"] == "tiny_validation_fixture" for d in datasets):
                status = "completed_validation_only"
            else:
                status = "completed"
        manifest["status"] = status
        manifest["finished_at_utc"] = utc_now()
        manifest["completed_attempts"] = len(rows)
        manifest["failed_measured_attempts"] = sum(
            row["phase"] == "measured" and row["outcome"] != "success" for row in rows
        )
        atomic_write_json(run_dir / "run_manifest.json", manifest)

        plot_paths: list[str] = []
        if not args.no_plots and any(d["state"] == "available" for d in datasets):
            try:
                plot_dir = make_run_directory(
                    plots_root, run_id if not (plots_root / run_id).exists() else f"{run_id}_results"
                )
                plot_paths = write_plots(summaries, plot_dir)
            except (OSError, RuntimeError) as error:
                status = "failed_plot_generation"
                exit_code = 1
                manifest["plot_error"] = str(error)
                manifest["status"] = status
                atomic_write_json(run_dir / "run_manifest.json", manifest)
                print(f"Plot generation failed: {error}", file=sys.stderr)

        report_path = (
            ROOT / "report" / "performance_evaluation.md"
            if args.update_report
            else run_dir / "generated_report.md"
        )
        generate_report(
            report_path,
            run_id,
            datasets,
            summaries,
            metadata,
            run_dir,
            plot_paths,
            {
                "damping": args.damping,
                "tolerance": args.tolerance,
                "max_iterations": args.max_iterations,
                "repetitions": args.repetitions,
                "warmups": args.warmups,
                "comparison_tolerance": args.comparison_tolerance,
            },
            status,
        )
        manifest["report_path"] = str(report_path)
        atomic_write_json(run_dir / "run_manifest.json", manifest)
        print(f"Run status: {status}")
        print(f"Results: {run_dir}")
        print(f"Report: {report_path}")
    if exit_code != 0:
        return exit_code
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
