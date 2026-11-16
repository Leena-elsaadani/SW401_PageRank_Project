#!/usr/bin/env python3
"""Aggregate and plot outputs from run_microbenchmarks.sh."""

from __future__ import annotations

import argparse
import csv
import statistics
from collections import defaultdict
from pathlib import Path


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as source:
        return list(csv.DictReader(source))


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("results_dir", type=Path, nargs="?", default=Path("results/memory"))
    parser.add_argument("--plots", type=Path, default=Path("plots/memory"))
    args = parser.parse_args()
    args.plots.mkdir(parents=True, exist_ok=True)

    size_order = {"100MB": 0, "500MB": 1, "full": 2}
    csr_summary: list[dict[str, object]] = []
    for path in sorted(args.results_dir.glob("*/csr_locality.csv"),
                       key=lambda item: size_order.get(item.parent.name, 99)):
        by_mode: dict[str, list[float]] = defaultdict(list)
        for row in read_rows(path):
            by_mode[row["mode"]].append(float(row["seconds"]))
        ordered = statistics.median(by_mode["ordered_rows"])
        shuffled = statistics.median(by_mode["shuffled_rows"])
        csr_summary.append(
            {
                "dataset": path.parent.name,
                "ordered_median_seconds": ordered,
                "shuffled_median_seconds": shuffled,
                "shuffled_slowdown": shuffled / ordered,
            }
        )

    false_values: dict[tuple[int, str], list[float]] = defaultdict(list)
    sync_values: dict[tuple[int, str], list[float]] = defaultdict(list)
    for path in args.results_dir.glob("*/false_sharing.csv"):
        for row in read_rows(path):
            false_values[(int(row["threads"]), row["layout"])].append(
                float(row["updates_per_second"])
            )
    for path in args.results_dir.glob("*/sync_overhead.csv"):
        for row in read_rows(path):
            sync_values[(int(row["threads"]), row["operation"])].append(
                float(row["nanoseconds_per_round"])
            )

    false_summary = [
        {
            "threads": threads,
            "layout": layout,
            "trials": len(values),
            "median_updates_per_second": statistics.median(values),
        }
        for (threads, layout), values in sorted(false_values.items())
    ]
    sync_summary = [
        {
            "threads": threads,
            "operation": operation,
            "trials": len(values),
            "median_nanoseconds_per_round": statistics.median(values),
        }
        for (threads, operation), values in sorted(sync_values.items())
    ]

    outputs = (
        (args.results_dir / "csr_locality_summary.csv", csr_summary),
        (args.results_dir / "false_sharing_summary.csv", false_summary),
        (args.results_dir / "sync_overhead_summary.csv", sync_summary),
    )
    for output, rows in outputs:
        if not rows:
            continue
        with output.open("w", newline="", encoding="utf-8") as destination:
            writer = csv.DictWriter(destination, fieldnames=list(rows[0]))
            writer.writeheader()
            writer.writerows(rows)

    try:
        import matplotlib.pyplot as plt
    except ImportError:
        print("Wrote summary CSV files; matplotlib is unavailable, so plots were skipped.")
        return 0

    if csr_summary:
        labels = [str(row["dataset"]) for row in csr_summary]
        positions = list(range(len(labels)))
        width = 0.36
        figure, axis = plt.subplots(figsize=(7, 4))
        axis.bar([x - width / 2 for x in positions],
                 [float(row["ordered_median_seconds"]) for row in csr_summary],
                 width, label="Ordered rows")
        axis.bar([x + width / 2 for x in positions],
                 [float(row["shuffled_median_seconds"]) for row in csr_summary],
                 width, label="Shuffled rows")
        axis.set_xticks(positions, labels)
        axis.set_ylabel("Median traversal time (s)")
        axis.set_title("CSR traversal locality")
        axis.legend()
        figure.tight_layout()
        figure.savefig(args.plots / "csr_locality.png", dpi=160)
        plt.close(figure)

    if false_summary:
        figure, axis = plt.subplots(figsize=(7, 4))
        for layout in ("packed", "cache_line_padded"):
            rows = [row for row in false_summary if row["layout"] == layout]
            axis.plot([int(row["threads"]) for row in rows],
                      [float(row["median_updates_per_second"]) / 1e9 for row in rows],
                      marker="o", label=layout.replace("_", " "))
        axis.set_xlabel("Threads")
        axis.set_ylabel("Median billion updates/s")
        axis.set_title("False-sharing experiment")
        axis.set_xticks([1, 2, 4, 8])
        axis.legend()
        figure.tight_layout()
        figure.savefig(args.plots / "false_sharing.png", dpi=160)
        plt.close(figure)

    if sync_summary:
        figure, axis = plt.subplots(figsize=(7, 4))
        for operation in ("barrier", "reduction"):
            rows = [row for row in sync_summary if row["operation"] == operation]
            axis.plot([int(row["threads"]) for row in rows],
                      [float(row["median_nanoseconds_per_round"]) for row in rows],
                      marker="o", label=operation)
        axis.set_xlabel("Threads")
        axis.set_ylabel("Median nanoseconds per round")
        axis.set_title("OpenMP synchronization overhead")
        axis.set_xticks([1, 2, 4, 8])
        axis.legend()
        figure.tight_layout()
        figure.savefig(args.plots / "sync_overhead.png", dpi=160)
        plt.close(figure)

    print(f"Wrote consolidated summaries under {args.results_dir} and plots under {args.plots}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
