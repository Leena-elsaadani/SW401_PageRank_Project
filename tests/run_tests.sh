#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OUTPUT_BIN="${ROOT_DIR}/tests/test_pagerank"

mkdir -p "${ROOT_DIR}/tests"

"${CXX:-g++}" -std=c++17 -O3 -fopenmp \
  "${ROOT_DIR}/src/sequential/graph.cpp" \
  "${ROOT_DIR}/src/sequential/pagerank.cpp" \
  "${ROOT_DIR}/src/openmp/pagerank_omp.cpp" \
  "${ROOT_DIR}/tests/test_pagerank.cpp" \
  -I "${ROOT_DIR}" \
  -o "${OUTPUT_BIN}"

"${OUTPUT_BIN}"
