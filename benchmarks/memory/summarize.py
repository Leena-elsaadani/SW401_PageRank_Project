#!/usr/bin/env python3
"""Summarize profile_command.sh outputs and create memory-analysis plots."""

from __future__ import annotations

import argparse
import csv
import math
import statistics
from collections import defaultdict
from pathlib import Path


def finite_numbers(rows: list[dict[str, str]], key: str) -> list[float]:
    values: list[float] = []
    for row in rows:
        try:
            value = float(row[key])
        except (KeyError, TypeError, ValueError):
            continue
        if math.isfinite(value):
            values.append(value)
    return values


def median_or_blank(values: list[float]) -> float | str:
    return statistics.median(values) if values else ""


def load_perf_events(root: Path, label: str) -> dict[str, list[float]]:
    events: dict[str, list[float]] = defaultdict(list)
    for path in sorted(root.glob(f"{label}_run*.perf.csv")):
        with path.open(encoding="utf-8", errors="replace") as source:
            for raw_row in csv.reader(source, delimiter=";"):
                if len(raw_row) < 3:
                    continue
                value_text, _, event = raw_row[:3]
                try:
                    value = float(value_text.strip().replace(",", ""))
                except ValueError:
                    continue
                events[event.strip()].append(value)
    return events


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path, nargs="?", default=Path("results/memory"))
    parser.add_argument("--plots", type=Path, default=Path("plots/memory"))
    args = parser.parse_args()

    summaries: list[dict[str, object]] = []
    for path in sorted(args.results_dir.glob("*_summary.csv")):
        with path.open(newline="", encoding="utf-8") as source:
            rows = list(csv.DictReader(source))
        if not rows:
            continue
        label = rows[0]["label"]
        successful = [row for row in rows if row.get("exit_code") == "0"]
        events = load_perf_events(args.results_dir, label)
        cache_refs = median_or_blank(events.get("cache-references", []))
        cache_misses = median_or_blank(events.get("cache-misses", []))
        cycles = median_or_blank(events.get("cycles", []))
        instructions = median_or_blank(events.get("instructions", []))
        miss_percent: float | str = ""
        ipc: float | str = ""
        if isinstance(cache_refs, float) and cache_refs > 0 and isinstance(cache_misses, float):
            miss_percent = cache_misses * 100.0 / cache_refs
        if isinstance(cycles, float) and cycles > 0 and isinstance(instructions, float):
            ipc = instructions / cycles
        rss_kb = finite_numbers(successful, "max_rss_kb")
        summaries.append(
            {
                "label": label,
                "runs": len(rows),
                "successful_runs": len(successful),
                "profiler": rows[0].get("profiler", ""),
                "median_wall_seconds": median_or_blank(finite_numbers(successful, "wall_seconds")),
                "median_max_rss_mb": (statistics.median(rss_kb) / 1024.0) if rss_kb else "",
                "median_cache_references": cache_refs,
                "median_cache_misses": cache_misses,
                "cache_miss_percent": miss_percent,
                "median_cycles": cycles,
                "median_instructions": instructions,
                "instructions_per_cycle": ipc,
            }
        )

    if not summaries:
        raise SystemExit(f"No *_summary.csv files found in {args.results_dir}")

    output = args.results_dir / "memory_summary.csv"
    with output.open("w", newline="", encoding="utf-8") as destination:
        writer = csv.DictWriter(destination, fieldnames=list(summaries[0]))
        writer.writeheader()
        writer.writerows(summaries)

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print(f"Wrote {output}; matplotlib is unavailable, so plots were skipped.")
        return 0

    args.plots.mkdir(parents=True, exist_ok=True)
    for key, title, ylabel, filename in (
        ("median_wall_seconds", "Profiled runtime", "Seconds", "profile_runtime.png"),
        ("median_max_rss_mb", "Peak resident memory", "MiB", "peak_memory.png"),
        ("cache_miss_percent", "Cache miss rate", "Percent", "cache_miss_rate.png"),
    ):
        points = [(str(row["label"]), row[key]) for row in summaries if isinstance(row[key], float)]
        if not points:
            continue
        labels, values = zip(*points)
        figure, axis = plt.subplots(figsize=(max(6, len(labels) * 1.2), 4))
        axis.bar(labels, values)
        axis.set_title(title)
        axis.set_ylabel(ylabel)
        axis.tick_params(axis="x", rotation=30)
        figure.tight_layout()
        figure.savefig(args.plots / filename, dpi=160)
        plt.close(figure)

    print(f"Wrote {output} and available plots under {args.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
