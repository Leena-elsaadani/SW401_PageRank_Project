# Performance Evaluation

## 1. Purpose

This evaluation compares the sequential PageRank implementation with its OpenMP counterpart, measuring solver runtime, speedup, thread efficiency, and observed scalability. All reported numerical results are generated from successful measured repetitions; no missing values are estimated.

## 2. Experimental environment

| Property | Recorded value |
|---|---|
| Operating system | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| CPU model | 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz |
| Logical CPUs visible | 8 |
| Available memory at run start | 3.133 GiB |
| Compiler | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 |
| Compiler flags | `-std=c++17 -O3 -fopenmp` |
| Python | 3.12.3 |
| Run identifier (UTC) | `20261116T155731Z` |

## 3. Datasets

The documented 100 MiB and 500 MiB inputs are prefixes of the cleaned edge ordering, not random samples. The full input is the cleaned directed LiveJournal graph. The runner records actual file size, SHA-256, node count, and edge count for each dataset it processes.

No project benchmark dataset was present when this report was generated. The required LiveJournal files and their performance results are therefore unavailable. The committed tiny graph is reserved for workflow validation and is not reported as a project benchmark.

## 4. Methodology

Both implementations use damping factor `0.85`, tolerance `1e-08`, and maximum `100` iterations. Each configuration has one unmeasured warm-up followed by 3 measured repetitions. Sequential PageRank is measured once per dataset; OpenMP is measured at 1, 2, 4, and 8 threads. The runner checks the actual OpenMP team size and records a mismatch as a failed run. Compilation and graph loading are excluded from solver time; the same harness loads each graph before timing the direct solver call. Timing uses `std::chrono::steady_clock` at sub-millisecond resolution. The implementation-provided elapsed time was not used because it is rounded to whole milliseconds and the OpenMP CLI does not report it.

No trial CSVs or per-run logs are included because no dataset was available and no benchmark repetitions ran. For a benchmark run, the runner saves all warm-up and measured attempts, including nonzero exits and timeouts, with per-run logs, compiler output, environment metadata, medians, and derived formulas under a unique `results/performance/` run directory.

## 5. Runtime results

| Dataset | Sequential median (s) | OpenMP 1 thread (s) | OpenMP 2 threads (s) | OpenMP 4 threads (s) | OpenMP 8 threads (s) |
|---|---:|---:|---:|---:|---:|
| No available benchmark dataset | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |

A median is reported only when all required measured repetitions for that configuration succeeded. A partial run set is marked unavailable rather than presented as a complete median.

## 6. Speedup, efficiency, and serial-fraction estimate

Speedup is `T_seq / T_parallel`; efficiency is `speedup / P` and is shown as a ratio (multiply by 100 for percent). The Karp–Flatt estimate is `s = (1/S(P) - 1/P) / (1 - 1/P)` and is omitted for P = 1. Estimates outside [0, 1] are retained and explicitly flagged; they may indicate measurement noise, parallel overhead, or behavior not captured by a simple fixed serial fraction. Karp–Flatt is an estimate from observed performance, not a direct measurement of serial code.

| Dataset | Threads | Median runtime (s) | Speedup (ratio) | Efficiency (ratio) | Karp–Flatt s | Amdahl S(P) | Gustafson S(P) | Estimate flag |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| No completed parallel runs | — | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | — |

## 7. Amdahl’s and Gustafson’s laws

Amdahl’s prediction, `S(P) = 1 / (s + (1-s)/P)`, illustrates a fixed-workload upper bound when the estimated serial fraction is valid. Gustafson’s prediction, `S(P) = P - s(P-1)`, describes the potential speedup when workload scales with processor count. These theoretical values are derived from Karp–Flatt estimates and are not benchmark measurements. They are unavailable when no valid completed median is available.

## 8. Scalability and interpretation

No scalability conclusion can be drawn because the project datasets were unavailable and no project benchmark measurements were completed.

## 9. Figures

No figures were generated because there are no complete dataset measurements.

The runner creates per-dataset plots for median runtime, measured speedup, efficiency, and the sequential/OpenMP runtime comparison. Each plotted point comes only from complete measured runs.

## 10. Limitations and sources of error

- Large LiveJournal inputs are not included in Git. Missing files leave all corresponding results unavailable.
- The current OpenMP implementation uses the same solver code path as the sequential version, but parallel reductions and scheduling can change floating-point summation order.
- Solver-only timing excludes graph parsing, so it isolates PageRank iteration cost rather than end-to-end application latency.
- Warm-up and operating-system caching, CPU frequency scaling, background load, and thread placement can affect measurements.
- The documented samples are prefixes of the original edge ordering and may not represent the full graph structurally.
- Amdahl and Gustafson predictions rely on a derived serial fraction and should not be treated as direct observations.

## 11. Conclusion

The benchmarking workflow is in place, but no project-dataset performance result can be stated until the local LiveJournal files are prepared and the benchmark is run.

## 12. Reproduction

See [`benchmarks/README.md`](../benchmarks/README.md) for build, smoke-test, and full benchmark commands. Recorded parameters: damping `0.85`, tolerance `1e-08`, maximum iterations `100`, measured repetitions `3`, warm-ups `1`.
