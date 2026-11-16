# Member 4: Memory hierarchy experiments

This directory contains the reproducible part of the Member 4 workstream. It does not invent PageRank measurements: the real sequential and OpenMP executables must be supplied by Members 1 and 2 and profiled with `profile_command.sh`.

## Build and smoke test

```bash
make -C benchmarks/memory test
```

## Profile the real PageRank programs

The wrapper accepts any command after `--`, so it does not depend on a particular command-line interface:

```bash
benchmarks/memory/profile_command.sh -l sequential_100MB -- \
  ./build/pagerank_seq data/samples/livejournal_100MB.txt

OMP_NUM_THREADS=4 OMP_PROC_BIND=close OMP_PLACES=cores \
benchmarks/memory/profile_command.sh -l openmp_4t_100MB -- \
  ./build/pagerank_omp data/samples/livejournal_100MB.txt
```

Repeat for 1, 2, 4, and 8 threads and for each available graph size. The wrapper always records elapsed time, peak resident memory, page faults, and context switches through `/usr/bin/time`. When Linux `perf` is installed and hardware counters are accessible, it additionally records cycles, instructions, cache references/misses, branches, and migrations. This automatic fallback is useful on WSL systems where performance counters may be unavailable.

Summarize all wrapper results and create available plots:

```bash
python3 benchmarks/memory/summarize.py results/memory --plots plots/memory
```

## Cache-sensitive microbenchmarks

```bash
benchmarks/memory/run_microbenchmarks.sh \
  data/samples/livejournal_100MB.txt
```

After running the microbenchmarks in `results/memory/100MB`, `500MB`,
and `full`, consolidate their medians and plots with:

```bash
python3 benchmarks/memory/plot_microbenchmarks.py \
  results/memory --plots plots/memory
```

- `csr_locality` builds the same outgoing-CSR shape used by PageRank and compares ordered row traversal with a deterministic shuffled row traversal. Both modes perform the same edge/rank reads and produce the same checksum; traversal order is the independent variable.
- `false_sharing` compares adjacent per-thread counters with 64-byte cache-line-padded counters at 1, 2, 4, and 8 threads.
- `sync_overhead` measures the cost per OpenMP barrier and small reduction at the same thread counts.

Run the microbenchmarks while the machine is otherwise idle. Use at least three trials for reported PageRank results, keep compiler flags fixed, and record CPU, OS/WSL, compiler version, thread affinity, and dataset checksum. Prefix samples are useful for scaling experiments but are not structurally random samples.

Raw generated outputs belong in `results/memory/`; plots belong in `plots/memory/`. Do not commit the LiveJournal data.
