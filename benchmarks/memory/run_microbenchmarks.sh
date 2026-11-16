#!/usr/bin/env bash
set -euo pipefail

if (( $# < 1 || $# > 2 )); then
    echo "Usage: $0 EDGE_LIST [OUTPUT_DIR]" >&2
    exit 2
fi

script_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
project_dir=$(cd "$script_dir/../.." && pwd)
dataset=$1
output_dir=${2:-"$project_dir/results/memory"}

make -C "$script_dir" all
mkdir -p "$output_dir"

"$project_dir/build/memory/csr_locality" "$dataset" 3 > "$output_dir/csr_locality.csv"
"$project_dir/build/memory/false_sharing" 10000000 8 > "$output_dir/false_sharing.csv"
"$project_dir/build/memory/sync_overhead" 10000 8 > "$output_dir/sync_overhead.csv"

echo "Wrote microbenchmark results to $output_dir"
