# PageRank performance benchmarking

`run_performance.py` compares sequential and OpenMP solver calls without changing either implementation. It compiles the separate C++ harness first, measures graph loading separately, and times the selected solver with `std::chrono::steady_clock`. Process wall time includes graph loading and, for OpenMP trials, a sequential correctness reference run. Compilation is excluded from all measurements. Existing solver API timings are rounded to whole milliseconds; the OpenMP CLI also runs sequential PageRank without reporting the OpenMP runtime.

The benchmark passes damping 0.85, tolerance 1e-6, maximum 100 iterations, initial rank 1/N (from the existing solver), equal dangling-rank redistribution, and the directed input graph. Member 1/2 CLI and API defaults remain at tolerance 1e-8; the harness explicitly supplies 1e-6 and does not change those implementations. A warning and metadata entry identify any custom non-default tolerance.

The harness requests and verifies OpenMP teams of 1, 2, 4, and 8. Each OpenMP process also runs sequential PageRank as a correctness reference and records convergence, iteration counts, rank sum, deterministic top-10 ranks, and maximum absolute rank difference. Rank-vector comparison tolerance defaults to 1e-6. Different iteration counts are recorded, not alone treated as incorrect. Final error must be below tolerance for a run to count as successful.

Five measured repetitions are the default (minimum three); five are recommended for the 100 and 500 MiB inputs. One unmeasured warm-up per configuration is default. Configuration order is shuffled reproducibly with a recorded seed and order, reducing systematic effects of thermal and frequency scaling. Raw CSV rows are flushed and synchronized to disk after each attempt. A run interrupted or stopped partway retains its raw rows and identifies incomplete configurations in the manifest and summary. Medians use only complete sets of successful measured runs; minimum, maximum, sample coefficient of variation, and an instability flag (CV > 0.1) are also reported.

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
  --plots-root plots/benchmark_validation
```

Run the focused Python metric tests with:

```bash
python -m unittest discover -s benchmarks -p "test_*.py"
```

## Run project benchmarks

After preparing datasets as documented in [`../data/README.md`](../data/README.md), run the available 100 MiB and 500 MiB samples:

```bash
python benchmarks/run_performance.py --repetitions 5
```

Run individual dataset experiments with:

```bash
python benchmarks/run_performance.py --dataset data/samples/livejournal_100MB.txt --repetitions 5
python benchmarks/run_performance.py --dataset data/samples/livejournal_500MB.txt --repetitions 5
python benchmarks/run_performance.py --dataset data/processed/livejournal_clean.txt --include-full --repetitions 5
```

Each run gets a unique directory under `results/performance/`, plus a corresponding plot directory under `plots/performance/`. A generated `generated_report.md` is saved inside the run directory by default. The hand-authored `report/performance_evaluation.md` is never overwritten unless `--update-report` is explicitly supplied. Raw CSV rows include warm-ups, every measured attempt, execution order, timestamps, requested and observed threads, process outcome, convergence/correctness, solver/process/load timings, peak RSS, dataset digest, and log path. `environment.json`, `run_manifest.json`, `build.log`, `dataset_metadata.json`, `summary.csv`, and `metrics.json` preserve environment, build, input, completion, and derived values.

Environment metadata records OS/kernel/distribution, WSL detection/version when available, CPU model and physical/logical counts, SMT indication, available system memory, CPU governor when accessible, compiler/Python, effective `OMP_*` settings, git branch/commit/dirty state, parameters, and execution order. Each process receives `OMP_DYNAMIC=FALSE`, its requested `OMP_NUM_THREADS`, `OMP_PLACES=cores`, and `OMP_PROC_BIND=close`; eight logical threads may use SMT when physical core count is lower. Unknown details are explicitly `unavailable`.

Peak RSS is read from Linux `getrusage(RUSAGE_SELF)` in KiB. It is the process high-water mark including graph load and the sequential correctness check; it is not total system memory or solver-only memory. Graph load is timed separately. Per-iteration time is a derived average (solver time / iteration count), not directly instrumented.

The 100 MiB and 500 MiB inputs are prefixes of the original edge ordering, not random samples. The runner checks and records actual bytes, directed edge count, observed node count (`max vertex ID + 1`), and SHA-256 against documented reference values. Prefix node counts need not equal full-graph node count.

## Full dataset resource guard

The cleaned full graph is never selected by default. Before opting in, check available memory and expect 30 solver runs by default (one warm-up plus five measured runs for five configurations); runtime may be substantial and depends on hardware and convergence. The runner uses a conservative working-set heuristic of at least twice the input size and preserves at least 1 GiB of memory; this is not measured peak RSS. A denied resource check is recorded as `memory_aborted`, while prior results are retained. Review the resource metadata before explicitly opting in:

```bash
python benchmarks/run_performance.py --include-full --repetitions 5
```

Datasets larger than 600 MiB require `--include-full`, even when supplied via `--dataset`. A memory refusal is recorded and causes a nonzero exit unless `--allow-low-memory` is explicitly supplied after review. Missing requested datasets are recorded and cause a nonzero exit; a missing dataset is never reported as a successful experiment. SIGKILL is called an OOM abort only when a cgroup OOM counter confirms it; otherwise it is recorded as an abnormal signal exit.

## Metrics and plots

- Sequential speedup: sequential median divided by OpenMP median.
- OpenMP self-relative speedup: OpenMP 1-thread median divided by OpenMP P-thread median.
- Efficiency: sequential speedup divided by thread count, reported as a ratio.
- Karp–Flatt effective serial fraction is estimated only from the P=2 sequential speedup. Negative or >1 estimates are flagged and not used for projections.
- Amdahl projections use the P=2 estimate to predict P=4/P=8 and are compared with measurements; no same-P calibration is presented as independent validation.
- Gustafson values are illustrative theory only; fixed-size experiments do not validate scaled speedup.
- Solver-only serial fraction does not necessarily describe the end-to-end application.

Plots include median runtime with min/max ranges and sequential baseline, sequential and OpenMP self-relative speedup with ideal linear reference, efficiency, sequential/OpenMP comparison, Karp–Flatt, and Amdahl projected-versus-measured speedup. Failed configurations are labeled. Missing results are never synthesized.

## Outcomes and reproducibility limits

Each raw run is explicitly `success`, `non_converged`, `rank_sum_invalid`, `reference_non_converged`, `numerical_mismatch`, `thread_mismatch`, `timed_out`, `memory_aborted`, `abnormal_exit`, or another recorded setup/failure state. A run is only successful when convergence, rank-sum, thread, and (for OpenMP) numerical-consistency checks pass.

The source implementation uses a static contiguous vertex loop; skewed in-degree can cause load imbalance. The benchmark does not change scheduling. CPU power policy, WSL memory settings, hardware counters, cache state, system load, and physical/SMT topology limit cross-machine comparisons; metadata marks inaccessible fields unavailable.

The actual datasets are not committed. Prepare them as documented in `data/README.md`. Missing 100 MiB/500 MiB inputs cause an incomplete, nonzero run. A tiny fixture is validation only and cannot be described as a completed LiveJournal experiment.
