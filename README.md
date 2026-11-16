# SW401 – PageRank on LiveJournal

## 1. Project Overview

This project focuses on implementing and evaluating the PageRank algorithm using the SNAP LiveJournal social network dataset as part of the SW401 – Parallel and Distributed Systems course.

The project explores sequential and parallel implementations of PageRank and investigates their performance, scalability, and memory behavior.

The main objectives are:

- Implement a sequential PageRank algorithm using C++.
- Develop a parallel PageRank implementation using OpenMP.
- Evaluate performance using different thread counts.
- Analyze execution time, speedup, and parallel efficiency.
- Investigate memory hierarchy, cache behavior, and data locality.

## 2. Dataset

**Dataset:** SNAP LiveJournal Social Network

**Official source:**  
https://snap.stanford.edu/data/soc-LiveJournal1.html

### Original Dataset Statistics

| Property | Value |
|---|---:|
| Number of nodes | 4,847,571 |
| Number of edges | 68,993,773 |
| Dataset type | Directed graph |

The dataset represents the LiveJournal online social network.

The original dataset is not stored in this repository because of its large size. Each team member can download it from the official SNAP source and run the preprocessing script.

## 3. Preprocessing

The preprocessing script is located at:

`preprocessing/preprocess.py`

It performs the following operations:

- Reads the original edge-list dataset.
- Skips comment lines and blank lines.
- Validates edge records.
- Generates a cleaned edge-list dataset.
- Creates smaller sample datasets for testing.

### Preprocessing Results

| Dataset | Edges | File size |
|---|---:|---:|
| Cleaned dataset | 68,993,773 | 1,011,604,076 bytes |
| 100 MB sample | 8,015,157 | 104,857,589 bytes |
| 500 MB sample | 37,672,977 | 524,287,992 bytes |

No invalid records were found during preprocessing.

Generated datasets are kept locally and excluded from GitHub because of their size.

## 4. Development Environment

The project is developed and tested using the following environment:

- Operating System: Ubuntu 24.04 (WSL2)
- C++ Compiler: G++ 13.3.0
- Parallel Programming: OpenMP
- Python: Python 3
- Version Control: Git and GitHub
- IDE: Visual Studio Code

## 5. Repository Structure

```text
SW401_Project/
│
├── data/
│   ├── raw/
│   ├── processed/
│   └── samples/
│
├── preprocessing/
│   └── preprocess.py
│
├── src/
│   ├── sequential/
│   └── openmp/
│
├── tests/
│
├── benchmarks/
│
├── results/
│
├── plots/
│
├── report/
│
├── .gitignore
└── README.md
```

### Folder Description

| Folder | Purpose |
|---|---|
| `data/` | Stores the raw, processed, and sample datasets locally. |
| `preprocessing/` | Contains scripts for dataset preprocessing. |
| `src/sequential/` | Contains the sequential PageRank implementation. |
| `src/openmp/` | Contains the OpenMP parallel implementation. |
| `tests/` | Contains correctness and validation tests. |
| `benchmarks/` | Contains benchmarking scripts and experiment configurations. |
| `results/` | Stores experimental results and measurements. |
| `plots/` | Stores performance graphs and visualizations. |
| `report/` | Contains project documentation and the final report. |

## 6. PageRank Algorithm

PageRank measures the importance of nodes in a directed graph.

The PageRank equation is:

\[
PR(v) = \frac{1-d}{N} + d\sum_{u \rightarrow v}\frac{PR(u)}{outdegree(u)}
\]

Where:

- \(PR(v)\): PageRank score of node \(v\).
- \(d\): Damping factor, typically 0.85.
- \(N\): Total number of nodes.
- \(u \rightarrow v\): An edge from node \(u\) to node \(v\).
- \(outdegree(u)\): Number of outgoing edges from node \(u\).

Dangling nodes (nodes with no outgoing edges) must also be handled by redistributing their rank equally among all nodes.

## 7. Quick Start

Build the sequential and OpenMP implementations from the project root:

```bash
g++ -std=c++17 -O3 src/sequential/graph.cpp src/sequential/pagerank.cpp src/sequential/main.cpp -I src/sequential -o sequential_pagerank
g++ -std=c++17 -O3 -fopenmp src/sequential/graph.cpp src/sequential/pagerank.cpp src/openmp/pagerank_omp.cpp src/openmp/main.cpp -I src -I src/openmp -I src/sequential -o openmp_pagerank
```

Run the reproducible correctness tests:

```bash
./tests/run_tests.sh
```

Run the reproducible sequential/OpenMP performance benchmarks (GCC with OpenMP and Python/Matplotlib required):

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r benchmarks/requirements.txt
python3 benchmarks/run_performance.py --dataset tests/data/tiny_graph.txt --no-report
python3 benchmarks/run_performance.py --repetitions 5
```

On Ubuntu/WSL, install `python3-full` first if venv/pip is unavailable. The tiny graph command validates the workflow only; it is not a LiveJournal performance result. Normal runs write `generated_report.md` inside each unique results run directory and never overwrite the hand-authored report. Use `--update-report` only when intentionally replacing it. The benchmark explicitly passes the required `1e-6` tolerance; the sequential/OpenMP CLI defaults remain `1e-8`. See [`benchmarks/README.md`](benchmarks/README.md) for setup, output locations, resource checks, and full-dataset commands.

Run PageRank on the cleaned dataset or a sample:

```bash
./sequential_pagerank --graph data/processed/livejournal_clean.txt --damping 0.85 --tol 1e-8 --max-iter 100
./openmp_pagerank --graph data/samples/livejournal_100MB.txt --damping 0.85 --tol 1e-8 --max-iter 100 --threads 4
```

The sequential and OpenMP implementations use the same damping factor, tolerance, and convergence criterion, and they are validated against each other on small directed graphs.

## 8. Team

**Course:** SW401 – Parallel and Distributed Systems

**Team size:** 4 members

All team members contribute to the implementation, testing, performance evaluation, and final project documentation.


**Project:** PageRank on LiveJournal  
**Course:** SW401 – Parallel and Distributed Systems