# PageRank Performance Evaluation

**Run:** `20261116T171048Z`  
**Experiment status:** `completed_validation_only`  
**Report category:** tiny-fixture workflow validation only

## Purpose and methodology

Compare sequential PageRank against OpenMP at 1, 2, 4, and 8 requested threads. Solver runtime is timed with `steady_clock`; graph loading is timed separately, and process wall time includes graph loading plus any correctness-reference work. `average_iteration_seconds_derived` is solver time divided by iterations, not direct per-iteration instrumentation. Compilation is excluded.

Parameters: damping `0.85`, tolerance `1e-06`, maximum iterations `100`, warm-ups `1`, measured repetitions `3`, comparison tolerance `1e-06`. The tolerance is the required default.

Warm-ups are excluded from statistics. Configuration order is reproducibly interleaved by random seed to reduce systematic thermal/frequency bias. Medians are primary; min/max and sample coefficient of variation identify variability. Five measured repetitions are recommended for final 100/500 MiB experiments.

Convergence requires final L1 error below the supplied tolerance before the iteration limit. Rank sums are checked against 1.0. Each OpenMP process also computes a sequential reference on the same loaded graph and reports maximum absolute rank difference, top-10 rankings, convergence statuses, and iteration counts. Iteration-count differences are recorded but are not alone deemed incorrect. Comparison tolerance is explicit in the run metadata.

## Experimental environment

| Property | Value |
|---|---|
| OS / kernel | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.39 / 6.18.54.1-microsoft-standard-WSL2 |
| Linux distribution | Ubuntu 24.04.5 LTS |
| WSL detected / version | True / WSL version: 3.0.3.0
Kernel version: 6.18.54.1-1
WSLg version: 1.0.79
MSRDC version: 1.2.7391
Direct3D version: 1.611.1-81528511
DXCore version: 10.0.26100.1-240331-1435.ge-release
Windows version: 10.0.26200.9457 |
| CPU | 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz |
| Physical cores / logical processors | 4 / 8 |
| SMT status | enabled or logical count exceeds physical core count |
| Available system memory | 3.146 GiB |
| Compiler | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 |
| Python | 3.12.3 |
| CPU governor | unavailable |
| WSL memory configuration | unavailable |
| Git branch / commit / dirty | member3-benchmarking / `d59af5fce93268f5b00038dc8cf6632d24afb435` / True |
| Effective OpenMP environment | `{"OMP_DYNAMIC": "FALSE", "OMP_NUM_THREADS": "per-run requested team size", "OMP_PLACES": "cores", "OMP_PROC_BIND": "close"}` |

Peak RSS is measured per harness process via Linux `getrusage(RUSAGE_SELF)` and reported in KiB. It is the process high-water mark including graph loading and, for OpenMP trials, the sequential correctness check; it is not system-wide memory or solver-only memory. `unavailable` is reported on unsupported platforms.

## Dataset validation

| Dataset | Type | State | Size (bytes) | Observed nodes | Directed edges | Validation | SHA-256 |
|---|---|---|---:|---:|---:|---|---|
| tiny_graph.txt | tiny_validation_fixture | available | 157 | 6 | 8 | matches_documented_counts | `4b54aefcd12d407051f275d0380f1690278f2081e78456efcebb8b6245b5dd9c` |
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.
- **tiny_graph.txt:** Fixture run is workflow validation only; not a LiveJournal experiment.

The documentation gives 8,015,157 and 37,672,977 edges for the 100 and 500 MiB prefixes, and 4,847,571 nodes / 68,993,773 directed edges for the full graph. Prefix node count is the observed maximum vertex ID plus one and is not assumed to equal the full graph node count. The loader stores incoming adjacency while retaining directed edge orientation; observed edge count is checked against the number of records loaded. Prefix sizes/order may alter graph structure and are not random samples.

## Configuration results

| Dataset | Impl. | Threads | Successful / required | Status | Median solver (s) | Min (s) | Max (s) | CV (ratio) | Unstable (CV > 0.1) | Median peak RSS (KiB) | Convergence / correctness |
|---|---|---:|---:|---|---:|---:|---:|---:|---|---:|---|
| tiny_graph.txt | sequential | 1 | 3 / 3 | complete | 1.2011e-05 | 1.1303e-05 | 1.2809e-05 | 0.0625735 | False | 23484 | complete |
| tiny_graph.txt | openmp | 1 | 3 / 3 | complete | 0.000127824 | 0.000119103 | 0.000162562 | 0.168436 | True | 23484 | complete |
| tiny_graph.txt | openmp | 2 | 3 / 3 | complete | 0.000131353 | 0.000121655 | 0.000141143 | 0.0741647 | False | 23484 | complete |
| tiny_graph.txt | openmp | 4 | 3 / 3 | complete | 0.000401458 | 0.000356667 | 0.000405212 | 0.0696507 | False | 23484 | complete |
| tiny_graph.txt | openmp | 8 | 3 / 3 | complete | 0.000464095 | 0.000455556 | 0.000516432 | 0.0688529 | False | 23484 | complete |

Per-run convergence, final error, iterations, rank sum, deterministic top-10, requested/actual threads, numerical difference, process wall time, graph-load time, and peak RSS are recorded in `raw_runs.csv`. Non-converged, failed, timed-out, memory-aborted, and not-started configurations remain visible in raw and summary outputs.

## Performance metrics

Sequential speedup is `T_seq / T_omp(P)`. OpenMP self-relative speedup is `T_omp(1) / T_omp(P)`. Efficiency is sequential speedup divided by P. Values are calculated only from complete successful medians. A serial fraction is estimated from P=2 only. Amdahl predictions at P=4 and P=8 use that P=2 estimate, so the calibration point is not repeated as purported independent prediction. Values outside [0,1] are flagged and not used for projections. Gustafson values are illustrative theory; fixed-size runs do not validate scaled speedup. A solver-only serial fraction need not describe the end-to-end application.

| Dataset | Threads | Sequential speedup | OpenMP self-speedup | Efficiency | Karp–Flatt s (from P=2) | Amdahl prediction from P=2 | Measured − predicted | Gustafson illustration | Estimate status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| tiny_graph.txt | 1 | 0.0939651 | 1 | 0.0939651 | 20.8721 | Unavailable | Unavailable | Unavailable | out_of_range |
| tiny_graph.txt | 2 | 0.0914406 | 0.973133 | 0.0457203 | 20.8721 | Unavailable | Unavailable | Unavailable | out_of_range |
| tiny_graph.txt | 4 | 0.0299184 | 0.318399 | 0.00747961 | 20.8721 | Unavailable | Unavailable | Unavailable | out_of_range |
| tiny_graph.txt | 8 | 0.0258805 | 0.275426 | 0.00323506 | 20.8721 | Unavailable | Unavailable | Unavailable | out_of_range |

## Figures

![tiny_graph_runtime](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_runtime.png)
![tiny_graph_speedup](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_speedup.png)
![tiny_graph_openmp_speedup](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_openmp_speedup.png)
![tiny_graph_efficiency](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_efficiency.png)
![tiny_graph_comparison](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_comparison.png)
![tiny_graph_amdahl](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_amdahl.png)
![tiny_graph_karp_flatt](../../../plots/benchmark_validation/20261116T171048Z/tiny_graph_karp_flatt.png)

Plots include min–max runtime ranges, sequential and OpenMP self-relative speedup (with ideal linear references), efficiency, comparison bars, P=2 Karp–Flatt estimate, and Amdahl projections versus measured P=4/P=8 speedup. Failed configurations are labeled rather than silently omitted.

## Limitations and interpretation

- Sequential and OpenMP CLI/API defaults are currently `1e-8`; the benchmark explicitly supplies the project-required `1e-6` unless overridden. Teammate source files were not changed.
- The benchmark times solver calls, excluding edge-list parsing; process wall includes graph load and correctness-reference work.
- OpenMP's static contiguous node partition can have load imbalance for skewed in-degree distributions; no scheduling implementation was changed.
- Frequency scaling, cache state, system load, WSL resource limits, and SMT can influence observed timing.
- Full LiveJournal data is memory intensive. Guard estimates are heuristics, not measured RSS.
- Amdahl and Gustafson are models, not measured speedup; Gustafson scaled behavior is not tested.

Full raw data, environment, manifest, and build logs are in `/mnt/d/Y4S1/Parallel and Distributed Computing/Project/Parallel Project/results/benchmark_validation/20261116T171048Z`. No dataset, missing result, or tiny-fixture timing should be presented as a completed LiveJournal experiment.
