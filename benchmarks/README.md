# PageRank performance benchmarking

`run_performance.py` compares the sequential and OpenMP solver APIs without changing either implementation. It compiles the separate C++ harness first, loads each dataset outside the timed interval, then measures only the solver call with `std::chrono::steady_clock`. This is necessary because the existing API timings are rounded to whole milliseconds and the OpenMP CLI runs the sequential solver as well without reporting its own runtime.

The harness requests and verifies OpenMP team sizes 1, 2, 4, and 8. The runner performs an unmeasured warm-up followed by at least three measured repetitions per configuration, records failures and timeouts, and computes medians only when every required measured repetition succeeds. Compilation is excluded from solver measurements.

## Requirements

Run from the repository root in Ubuntu/WSL (or another GCC/OpenMP environment):

```bash
sudo apt update
sudo apt install -y python3-full
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r benchmarks/requirements.txt
```

Required tools are GCC with OpenMP support, Python 3.10+, and Matplotlib. For example, the project’s documented Linux compiler is GCC 13.3. On Windows, run these commands inside WSL because a Windows GCC/OpenMP toolchain is not assumed.

## Validate the workflow

The committed tiny graph validates compilation, execution, thread selection, result recording, median calculations, and figure generation. Its timings are a smoke test only and must not be used to claim LiveJournal performance:

```bash
python benchmarks/run_performance.py \
  --dataset tests/data/tiny_graph.txt \
  --output-root results/benchmark_validation \
  --plots-root plots/benchmark_validation \
  --no-report
```

Run the focused Python metric tests with:

```bash
python -m unittest discover -s benchmarks -p "test_*.py"
```

## Run project benchmarks

After preparing datasets as documented in [`../data/README.md`](../data/README.md), run the available 100 MiB and 500 MiB samples:

```bash
python benchmarks/run_performance.py --repetitions 3
```

Each run gets a unique directory under `results/performance/`, plus a corresponding plot directory under `plots/performance/`. The report at `report/performance_evaluation.md` is updated from that run’s results. Raw CSV rows include warm-ups, every measured attempt, timestamps, requested and observed threads, exit status, runtime, dataset digest, and per-run log path. `environment.json`, `build.log`, `dataset_metadata.json`, `summary.csv`, and `metrics.json` preserve environment, build, input, and derived values.

The 100 MiB and 500 MiB inputs are prefixes of the original edge ordering, not random samples. The runner records their actual sizes, edge counts, and checksums.

## Full dataset resource guard

The cleaned full graph is never selected by default. Before opting in, check available memory and expect up to 20 solver runs (one warm-up plus at least three measured runs for five configurations); the runtime may be substantial and depends on hardware and convergence. The runner uses a conservative working-set estimate of at least twice the input size and preserves at least 1 GiB of memory. Review the printed resource check, then explicitly opt in:

```bash
python benchmarks/run_performance.py --include-full --repetitions 3
```

Datasets larger than 600 MiB require `--include-full`, even when supplied via `--dataset`. A run is refused when the conservative memory check fails unless `--allow-low-memory` is explicitly supplied after review. No benchmark is launched on missing files.

## Metrics and plots

- Speedup: sequential median divided by OpenMP median.
- Efficiency: speedup divided by thread count, reported as a ratio.
- Karp–Flatt serial fraction: calculated only for thread counts greater than one; estimates outside [0, 1] are retained and flagged.
- Amdahl and Gustafson values are theoretical predictions based on the Karp–Flatt estimate, not observed measurements.

For complete dataset runs, four plots are generated per dataset: runtime versus thread count, speedup, efficiency, and sequential/OpenMP runtime comparison. Incomplete configurations are not used to calculate medians or plot points.
