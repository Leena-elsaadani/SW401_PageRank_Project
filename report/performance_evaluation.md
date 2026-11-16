# Performance Evaluation

## 1. Purpose

This evaluation compares the sequential PageRank implementation with its OpenMP counterpart, measuring solver runtime, speedup, thread efficiency, and observed scalability. All reported numerical results are generated from successful measured repetitions; no missing values are estimated.

## 2. Experimental environment

| Property | Recorded value |
|---|---|
| Operating system | Linux-6.18.54.1-microsoft-standard-WSL2-x86_64-with-glibc2.39 |
| CPU model | 11th Gen Intel(R) Core(TM) i5-1135G7 @ 2.40GHz |
| Logical CPUs visible | 8 |
| Physical core count / SMT status | Unavailable (recorded by the benchmark runner per run) |
| Available memory observed during setup (not a benchmark run) | 3.133 GiB |
| Compiler | g++ (Ubuntu 13.3.0-6ubuntu2~24.04.1) 13.3.0 |
| Compiler flags | `-std=c++17 -O3 -fopenmp` |
| Python | 3.12.3 |
| Run identifier (UTC) | No benchmark experiment has been run |

## 3. Datasets

The documented 100 MiB and 500 MiB inputs are prefixes of the cleaned edge ordering, not random samples. The full input is the cleaned directed LiveJournal graph. The runner records actual file size, SHA-256, node count, and edge count for each dataset it processes.

No project benchmark dataset was present when this report was generated. The required LiveJournal files and their performance results are therefore unavailable. The committed tiny graph is reserved for workflow validation and is not reported as a project benchmark.

## 4. Methodology

The benchmark uses damping factor `0.85`, required tolerance `1e-6`, maximum `100` iterations, initial rank `1/N`, equal dangling-node redistribution, and directed edges. Member 1/2 CLI and API defaults remain at `1e-8`; the benchmark passes `1e-6` explicitly without changing teammate code. The required parameters are recorded in each run's metadata.

Each configuration receives an unmeasured warm-up followed by at least three measured repetitions (five by default; five is recommended for final sample experiments). Configuration order is reproducibly shuffled with a recorded seed to reduce systematic thermal/frequency-scaling bias. Medians are primary; min/max and sample coefficient of variation identify variability. OpenMP runs verify the actual team size and are compared with a sequential reference on the same loaded graph. Convergence, iterations, final L1 error, rank sum, deterministic top-10 ranks, and maximum absolute rank difference are recorded. Iteration-count differences alone do not imply incorrectness.

The harness uses `std::chrono::steady_clock` for solver-only time and separately measures graph loading. Process wall time includes graph loading and the OpenMP correctness reference; compilation is excluded. Mean time per iteration is derived from solver time and iteration count, not directly instrumented. Linux `getrusage(RUSAGE_SELF)` records process peak RSS in KiB, including graph loading and correctness-reference work; it is not system-wide memory.

No trial CSVs or per-run logs are included because no dataset was available and no benchmark repetitions ran. For a benchmark run, the runner saves all warm-up and measured attempts, including nonzero exits and timeouts, with per-run logs, compiler output, environment metadata, medians, and derived formulas under a unique `results/performance/` run directory.

## 5. Runtime results

| Dataset | Sequential median (s) | OpenMP 1 thread (s) | OpenMP 2 threads (s) | OpenMP 4 threads (s) | OpenMP 8 threads (s) |
|---|---:|---:|---:|---:|---:|
| No available benchmark dataset | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable |

A median is reported only when all required measured repetitions for that configuration succeeded and documented dataset counts match. A partial, non-converged, failed, timed-out, or resource-aborted run remains visible and is not presented as a complete median.

## 6. Speedup, efficiency, and serial-fraction estimate

Sequential speedup is `T_seq / T_omp(P)`, OpenMP self-relative speedup is `T_omp(1) / T_omp(P)`, and efficiency is sequential speedup divided by P. Efficiency is a ratio (multiply by 100 for percent). The effective Karp–Flatt fraction is estimated only from the P=2 sequential speedup. Estimates outside [0, 1] are flagged and not used for projections; this is an estimate from observed solver-only performance, not a direct measurement of serial code fraction or end-to-end application serial fraction.

| Dataset | Threads | Median runtime (s) | Sequential speedup | OpenMP self-speedup | Efficiency (ratio) | Karp–Flatt s from P=2 | Amdahl prediction from P=2 | Gustafson illustration | Estimate flag |
|---|---:|---:|---:|---:|---:|---:|---:|---|
| No completed parallel runs | — | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | Unavailable | — |

## 7. Amdahl’s and Gustafson’s laws

Amdahl’s prediction is calculated from the P=2 Karp–Flatt estimate and projected to P=4 and P=8, then compared with those measured speedups. The P=2 calibration point is not repeated as an independent prediction. Gustafson’s formula, `S(P) = P - s(P-1)`, remains an illustrative theoretical comparison: a fixed-size benchmark does not experimentally validate scaled speedup. Neither formula's output is a measured result.

## 8. Scalability and interpretation

No conclusion about LiveJournal scalability can be drawn without project-dataset measurements. Eight logical threads may use SMT on hardware with fewer physical cores. The tiny fixture is useful for correctness and workflow validation only and is not representative evidence of large-graph behavior.

## 9. Figures

No figures were generated because there are no complete dataset measurements.

The runner creates per-dataset plots for median runtime with min/max ranges, speedup and efficiency, sequential/OpenMP comparisons, Karp–Flatt, and measured versus Amdahl-projected speedup. Failed configurations are labeled and are never silently represented as measured points.

## 10. Limitations and sources of error

- Large LiveJournal inputs are not included in Git. Missing files leave all corresponding results unavailable.
- Sequential and OpenMP are separate solver implementations over the shared graph representation; OpenMP reduction order can change floating-point summation order.
- Solver-only timing excludes graph parsing, so it isolates PageRank iteration cost rather than end-to-end application latency.
- Warm-up and operating-system caching, CPU frequency scaling, background load, and thread placement can affect measurements.
- The documented samples are prefixes of the original edge ordering and may not represent the full graph structurally.
- Amdahl and Gustafson predictions rely on a derived serial fraction and should not be treated as direct observations.

## 11. Conclusion

The benchmarking workflow is in place, but no project-dataset performance result can be stated until the local LiveJournal files are prepared and the benchmark is run.

## 12. Reproduction

See [`benchmarks/README.md`](../benchmarks/README.md) for build, smoke-test, and full benchmark commands. Planned defaults: damping `0.85`, tolerance `1e-6`, maximum iterations `100`, measured repetitions `5`, warm-ups `1`. No run identifier or result is claimed until a dataset benchmark actually completes.
