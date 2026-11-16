
# SW401 – PageRank on LiveJournal

## Project Overview

This project implements and evaluates the PageRank algorithm using the SNAP LiveJournal social network dataset.

The project explores:
- Sequential PageRank implementation in C++.
- Parallel PageRank implementation using OpenMP.
- Performance evaluation and speedup analysis.
- Memory hierarchy and cache behavior.

## Dataset

Dataset: SNAP LiveJournal

Official source:
https://snap.stanford.edu/data/soc-LiveJournal1.html

Original dataset statistics:
- Nodes: 4,847,571
- Edges: 68,993,773

The raw dataset is not stored in this repository because of its size.

## Preprocessing

The preprocessing script is located at:

`preprocessing/preprocess.py`

It:
- Reads the original edge list.
- Skips comment and blank lines.
- Validates edge records.
- Generates a cleaned edge list.
- Creates smaller sample datasets.

## Environment

- Ubuntu 24.04 (WSL2)
- G++ 13.3.0
- OpenMP support
- Python 3

## Project Structure

```text
SW401_Project/
├── data/
├── preprocessing/
├── src/
├── results/
├── plots/
├── report/
└── README.md
```

## Team

SW401 – Parallel and Distributed Systems
