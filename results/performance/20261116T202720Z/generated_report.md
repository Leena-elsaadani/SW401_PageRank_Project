# PageRank Performance Evaluation

**Run:** `20261116T202720Z`<br>
**Experiment status:** `completed`<br>
**Report category:** LiveJournal experiment or incomplete experiment

## Purpose and methodology

Compare sequential PageRank against OpenMP at 1, 2, 4, and 8 requested threads. Solver runtime is timed with `steady_clock`; graph loading is timed separately, and process wall time includes graph loading plus any correctness-reference work. `average_iteration_seconds_derived` is solver time divided by iterations, not direct per-iteration instrumentation. Compilation is excluded.

Parameters: damping `0.85`, tolerance `1e-06`, maximum iterations `100`, warm-ups `1`, measured repetitions `5`, comparison tolerance `1e-06`. The tolerance is the required default.

Warm-ups are excluded from statistics. Configuration order is reproducibly interleaved by random seed to reduce systematic thermal/frequency bias. Medians are primary; min/max and sample coefficient of variation identify variability. Five measured repetitions are recommended for final 100/500 MiB experiments.

Convergence requires final L1 error below the supplied tolerance before the iteration limit. Rank sums are checked against 1.0. Each OpenMP process also computes a sequential reference on the same loaded graph and reports maximum absolute rank difference, top-10 rankings, convergence statuses, and iteration counts. Iteration-count differences are recorded but are not alone deemed incorrect. Comparison tolerance is explicit in the run metadata.

## Experimental environment

| Property | Value |
|---|---|
| OS / kernel | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.39 / 6.18.54.1-microsoft-standard-WSL2 |
| Linux distribution | Ubuntu 24.04.5 LTS |
| WSL detected / version | True / WSL version: 3.0.3.0<br>Kernel version: 6.18.54.1-1<br>WSLg version: 1.0.79<br>MSRDC version: 1.2.7391<br>Direct3D version: 1.611.1-81528511<br>DXCore version: 10.0.26100.1-240331-1435.ge-release<br>Windows version: 10.0.26200.9457 |
| CPU | 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz |
| Physical cores / logical processors | 4 / 8 |
| SMT status | enabled or logical count exceeds physical core count |
| Available system memory | 3.196 GiB |
| Compiler | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 |
| Python | 3.12.3 |
| CPU governor | unavailable |
| WSL memory configuration | unavailable |
| Git branch / commit / dirty | member3-benchmarking / `364896bea68295bcade798a797098b84450902c4` / True |
| Effective OpenMP environment | `{"OMP_DYNAMIC": "FALSE", "OMP_NUM_THREADS": "per-run requested team size", "OMP_PLACES": "cores", "OMP_PROC_BIND": "close"}` |

Peak RSS is measured per harness process via Linux `getrusage(RUSAGE_SELF)` and reported in KiB. It is the process high-water mark including graph loading and, for OpenMP trials, the sequential correctness check; it is not system-wide memory or solver-only memory. `unavailable` is reported on unsupported platforms.

## Dataset validation

| Dataset | Type | State | Size (bytes) | Observed nodes | Directed edges | Validation | SHA-256 |
|---|---|---|---:|---:|---:|---|---|
| livejournal_100MB.txt | prefix_sample | available | 104857589 | 4847571 | 8015157 | matches_documented_counts | `1aca90f4a37fcb450fd0280d86e846bd97ab3100c6a3faf72f333dc3fe9cf5cf` |
- **livejournal_100MB.txt:** Prefix of original edge ordering; observed node count is max ID plus one, not assumed to be the full-graph count.
- **livejournal_100MB.txt:** Observed node count is 4,847,571 (max vertex ID + 1 in this graph), not assumed full-graph node count.

The documentation gives 8,015,157 and 37,672,977 edges for the 100 and 500 MiB prefixes, and 4,847,571 nodes / 68,993,773 directed edges for the full graph. Prefix node count is the observed maximum vertex ID plus one and is not assumed to equal the full graph node count. The loader stores incoming adjacency while retaining directed edge orientation; observed edge count is checked against the number of records loaded. Prefix sizes/order may alter graph structure and are not random samples.

## Configuration results

| Dataset | Impl. | Threads | Successful / required | Status | Median solver (s) | Min (s) | Max (s) | CV (ratio) | Unstable (CV > 0.1) | Median peak RSS (KiB) | Convergence / correctness |
|---|---|---:|---:|---|---:|---:|---:|---:|---|---:|---|
| livejournal_100MB.txt | sequential | 1 | 5 / 5 | complete | 2.88515 | 2.70789 | 3.42865 | 0.106325 | True | 211544 | complete |
| livejournal_100MB.txt | openmp | 1 | 5 / 5 | complete | 3.15033 | 2.62146 | 3.58697 | 0.128925 | True | 281528 | complete |
| livejournal_100MB.txt | openmp | 2 | 5 / 5 | complete | 3.44494 | 2.90358 | 3.97201 | 0.120671 | True | 281476 | complete |
| livejournal_100MB.txt | openmp | 4 | 5 / 5 | complete | 2.83951 | 2.74597 | 3.06567 | 0.0437731 | False | 281480 | complete |
| livejournal_100MB.txt | openmp | 8 | 5 / 5 | complete | 3.10713 | 2.24158 | 3.73957 | 0.18626 | True | 281560 | complete |

Per-run convergence, final error, iterations, rank sum, deterministic top-10, requested/actual threads, numerical difference, process wall time, graph-load time, and peak RSS are recorded in `raw_runs.csv`. Non-converged, failed, timed-out, memory-aborted, and not-started configurations remain visible in raw and summary outputs.

## Performance metrics

Sequential speedup is `T_seq / T_omp(P)`. OpenMP self-relative speedup is `T_omp(1) / T_omp(P)`. Efficiency is sequential speedup divided by P. Values are calculated only from complete successful medians. A serial fraction is estimated from P=2 only. Amdahl predictions at P=4 and P=8 use that P=2 estimate, so the calibration point is not repeated as purported independent prediction. Values outside [0,1] are flagged and not used for projections. Gustafson values are illustrative theory; fixed-size runs do not validate scaled speedup. A solver-only serial fraction need not describe the end-to-end application.

| Dataset | Threads | Sequential speedup | OpenMP self-speedup | Efficiency | Karp–Flatt s (from P=2) | Amdahl prediction from P=2 | Measured − predicted | Gustafson illustration | Estimate status |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| livejournal_100MB.txt | 1 | 0.915825 | 1 | 0.915825 | 1.38804 | Unavailable | Unavailable | Unavailable | out_of_range |
| livejournal_100MB.txt | 2 | 0.837505 | 0.914482 | 0.418753 | 1.38804 | Unavailable | Unavailable | Unavailable | out_of_range |
| livejournal_100MB.txt | 4 | 1.01607 | 1.10946 | 0.254018 | 1.38804 | Unavailable | Unavailable | Unavailable | out_of_range |
| livejournal_100MB.txt | 8 | 0.928558 | 1.0139 | 0.11607 | 1.38804 | Unavailable | Unavailable | Unavailable | out_of_range |

## Figures

![livejournal_100MB_runtime](../../../plots/performance/20261116T202720Z/livejournal_100MB_runtime.png)
![livejournal_100MB_speedup](../../../plots/performance/20261116T202720Z/livejournal_100MB_speedup.png)
![livejournal_100MB_openmp_speedup](../../../plots/performance/20261116T202720Z/livejournal_100MB_openmp_speedup.png)
![livejournal_100MB_efficiency](../../../plots/performance/20261116T202720Z/livejournal_100MB_efficiency.png)
![livejournal_100MB_comparison](../../../plots/performance/20261116T202720Z/livejournal_100MB_comparison.png)
![livejournal_100MB_amdahl](../../../plots/performance/20261116T202720Z/livejournal_100MB_amdahl.png)
![livejournal_100MB_karp_flatt](../../../plots/performance/20261116T202720Z/livejournal_100MB_karp_flatt.png)

Plots include min–max runtime ranges, sequential and OpenMP self-relative speedup (with ideal linear references), efficiency, comparison bars, P=2 Karp–Flatt estimate, and Amdahl projections versus measured P=4/P=8 speedup. Failed configurations are labeled rather than silently omitted.

## Limitations and interpretation

- Sequential and OpenMP CLI/API defaults are currently `1e-8`; the benchmark explicitly supplies the project-required `1e-6` unless overridden. Teammate source files were not changed.
- The benchmark times solver calls, excluding edge-list parsing; process wall includes graph load and correctness-reference work.
- OpenMP's static contiguous node partition can have load imbalance for skewed in-degree distributions; no scheduling implementation was changed.
- Frequency scaling, cache state, system load, WSL resource limits, and SMT can influence observed timing.
- Full LiveJournal data is memory intensive. Guard estimates are heuristics, not measured RSS.
- Amdahl and Gustafson are models, not measured speedup; Gustafson scaled behavior is not tested.

Full raw data, environment, manifest, and build logs are in `/mnt/d/Y4S1/Parallel and Distributed Computing/Project/Parallel Project/results/performance/20261116T202720Z`. No dataset, missing result, or tiny-fixture timing should be presented as a completed LiveJournal experiment.
