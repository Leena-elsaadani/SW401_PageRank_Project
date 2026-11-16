# Memory hierarchy and optimization analysis (Member 4)

## Scope and method

The project stores the directed graph in Compressed Sparse Row (CSR) form. `row_offsets` is scanned by source vertex and `col_indices` is contiguous within a source row. This representation has low structural overhead and good spatial locality while traversing consecutive rows. PageRank still performs indirect rank accesses through node IDs, so the rank array may have weaker locality, especially as the graph exceeds the last-level cache.

The actual sequential and OpenMP PageRank executables must be measured with `benchmarks/memory/profile_command.sh`. Each configuration should be run at least three times on the same machine and summarized with `benchmarks/memory/summarize.py`. Required configurations are the available dataset sizes and OpenMP thread counts 1, 2, 4, and 8. Record median elapsed time, peak RSS, page faults, context switches, and—when `perf` counters are available—cache references, cache misses, cycles, instructions, and IPC.

No PageRank measurements are included because the repository does not yet contain the sequential or OpenMP implementation. The LiveJournal dataset is now available and was used for the standalone CSR experiments below. PageRank values must be inserted only after executing the real programs.

## Experiments

### CSR locality

`csr_locality` compares increasing source-row order with a deterministic shuffled source-row order. The edge set, arithmetic, and rank values are identical, and the checksum must match. Ordered traversal is expected to benefit from sequential reads of `row_offsets` and `col_indices`; shuffled traversal repeatedly jumps between CSR regions and should put more pressure on caches and hardware prefetching. Report measured runtime and cache-miss rate rather than relying on the expectation.

### Graph-size effect

Profile the 100 MiB prefix, 500 MiB prefix, and full graph when memory permits. Larger CSR and rank arrays eventually exceed private and shared caches, so runtime is expected to become increasingly memory-bandwidth-sensitive. Because the provided samples are prefixes ordered by source node, this comparison also changes graph structure and active node range; it is not a pure size-only experiment, and that limitation must be stated.

### False sharing

`false_sharing` compares packed per-thread counters against counters aligned to 64-byte cache lines. Threads update distinct counters in both cases. A packed layout can place counters modified by different cores on one cache line, causing coherence invalidations; padding isolates them. Apply the same principle to any per-thread PageRank accumulators or statistics. Large shared arrays indexed by vertex are a different problem and must be handled through an ownership strategy or a pull formulation, not merely padding.

### Synchronization overhead

`sync_overhead` measures barrier and reduction latency at 1, 2, 4, and 8 threads. The OpenMP PageRank iteration normally requires reductions for dangling mass and convergence error plus a barrier before swapping rank buffers. These are algorithmically necessary, but extra barriers, atomics inside the edge loop, or critical sections should be avoided. Compare the microbenchmark trend with the real OpenMP program's context switches, migrations, and runtime scaling.

## Results to insert after execution

| Configuration | Median time (s) | Peak RSS (MiB) | Cache references | Cache misses | Miss rate | IPC |
|---|---:|---:|---:|---:|---:|---:|
| Sequential, 100 MiB | TBD | TBD | TBD | TBD | TBD | TBD |
| OpenMP 1 thread, 100 MiB | TBD | TBD | TBD | TBD | TBD | TBD |
| OpenMP 2 threads, 100 MiB | TBD | TBD | TBD | TBD | TBD | TBD |
| OpenMP 4 threads, 100 MiB | TBD | TBD | TBD | TBD | TBD | TBD |
| OpenMP 8 threads, 100 MiB | TBD | TBD | TBD | TBD | TBD | TBD |

Add equivalent rows for the 500 MiB and full datasets. Include the generated cache-miss and peak-memory plots when counters are available.

## Measured standalone memory experiments

These measurements were collected on November 16, 2026 on an Intel Core i7-12650H with 16 logical CPUs, Linux 7.2.13 (Fedora 43), GCC 15.3.1, and `-O3`. Each reported value is the median of three trials. The environment differs from the WSL environment described in the project workflow, so final team comparisons must use one consistent machine.

The complete build-and-scan profiles show the expected increase in memory footprint and preprocessing time:

| Dataset | Edges | Median wall time (s) | Median peak RSS (MiB) |
|---|---:|---:|---:|
| 100 MiB prefix | 8,015,157 | 4.43 | 145.32 |
| 500 MiB prefix | 37,672,977 | 20.15 | 258.50 |
| Full graph | 68,993,773 | 39.56 | 377.72 |

The inner CSR traversal produced identical checksums for both orders. Shuffling source-row order was consistently slower:

| Dataset | Ordered median (s) | Shuffled median (s) | Shuffled slowdown |
|---|---:|---:|---:|
| 100 MiB prefix | 0.02113 | 0.09467 | 4.48× |
| 500 MiB prefix | 0.08458 | 0.29069 | 3.44× |
| Full graph | 0.18491 | 1.01702 | 5.50× |

This supports keeping source rows in contiguous ranges. It does not by itself measure PageRank convergence or prove a hardware cache-miss count.

The false-sharing benchmark reported median billions of counter updates per second:

| Threads | Packed | Cache-line padded |
|---:|---:|---:|
| 1 | 1.275 | 2.239 |
| 2 | 2.555 | 4.293 |
| 4 | 3.841 | 5.204 |
| 8 | 6.340 | 6.669 |

Padding improved throughput in all tested configurations, although the benefit narrowed at eight threads. The benchmark isolates one pattern and should motivate inspection of per-thread PageRank state rather than be treated as a direct PageRank speedup.

Synchronization cost increased with thread count:

| Threads | Barrier (ns/round) | Reduction (ns/round) |
|---:|---:|---:|
| 1 | 176.70 | 289.96 |
| 2 | 2,913.94 | 5,759.40 |
| 4 | 4,804.21 | 8,970.74 |
| 8 | 6,445.56 | 12,670.07 |

The trend reinforces the recommendation to avoid redundant barriers and reductions inside PageRank iterations.

Generated data is stored under `results/memory/`; the corresponding plots are `plots/memory/csr_locality.png`, `false_sharing.png`, `sync_overhead.png`, `profile_runtime.png`, and `peak_memory.png`.

## perf limitation

This environment currently has no `perf` executable, so cache-miss counts cannot be claimed from this machine. The profiling wrapper automatically fell back to `/usr/bin/time`, which provided elapsed time, peak RSS, page faults, and context-switch counts. For the final cache analysis, install Linux performance tools in an environment that exposes hardware counters, or explicitly report the limitation and use the fallback metrics. `gprof` identifies time-consuming functions but does not measure cache misses and should not be described as a cache profiler.

## Optimization recommendations

1. Keep CSR arrays and rank buffers contiguous, use compact integer indices where the node range permits, and reuse allocated buffers across iterations.
2. Traverse CSR rows in stable contiguous ranges per thread with static scheduling unless measurements show a load-balance problem.
3. Prefer a race-free pull-style update or well-defined ownership over atomics in the inner edge loop.
4. Store per-thread scalar state on separate cache lines when it is frequently written.
5. Combine independent scalar reductions when practical and avoid redundant barriers.
6. Bind OpenMP threads to cores (`OMP_PROC_BIND=close`, `OMP_PLACES=cores`) during controlled experiments and document the setting.

These recommendations are hypotheses until confirmed by the real PageRank profiles; the final report should connect each adopted optimization to measured evidence.
