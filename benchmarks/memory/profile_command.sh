#!/usr/bin/env bash
set -u

usage() {
    echo "Usage: $0 [-r REPEATS] [-o OUTPUT_DIR] [-l LABEL] -- COMMAND [ARG ...]" >&2
}

repeats=3
output_dir="results/memory"
label="profile"

while getopts ":r:o:l:h" option; do
    case "$option" in
        r) repeats="$OPTARG" ;;
        o) output_dir="$OPTARG" ;;
        l) label="$OPTARG" ;;
        h) usage; exit 0 ;;
        :) echo "Option -$OPTARG requires a value." >&2; usage; exit 2 ;;
        \?) echo "Unknown option: -$OPTARG" >&2; usage; exit 2 ;;
    esac
done
shift $((OPTIND - 1))
if [[ "${1:-}" == "--" ]]; then shift; fi

if [[ "$repeats" != +([0-9]) ]] 2>/dev/null || (( repeats < 1 )) || (( $# == 0 )); then
    usage
    exit 2
fi

safe_label=${label//[^A-Za-z0-9_.-]/_}
mkdir -p "$output_dir"
summary="$output_dir/${safe_label}_summary.csv"
echo "label,run,profiler,exit_code,wall_seconds,user_seconds,system_seconds,max_rss_kb,major_faults,minor_faults,voluntary_context_switches,involuntary_context_switches" > "$summary"

profiler="time"
perf_events="task-clock,cycles,instructions,cache-references,cache-misses,branches,branch-misses,page-faults,context-switches,cpu-migrations"
if command -v perf >/dev/null 2>&1 && perf stat -e cycles -- true >/dev/null 2>&1; then
    profiler="perf+time"
fi

echo "Profiler: $profiler" >&2
for ((run = 1; run <= repeats; ++run)); do
    metrics="$output_dir/${safe_label}_run${run}.time"
    stdout_log="$output_dir/${safe_label}_run${run}.stdout"
    stderr_log="$output_dir/${safe_label}_run${run}.stderr"
    perf_log="$output_dir/${safe_label}_run${run}.perf.csv"

    if [[ "$profiler" == "perf+time" ]]; then
        /usr/bin/time -f $'wall_seconds;%e\nuser_seconds;%U\nsystem_seconds;%S\nmax_rss_kb;%M\nmajor_faults;%F\nminor_faults;%R\nvoluntary_context_switches;%w\ninvoluntary_context_switches;%c' \
            -o "$metrics" perf stat -x ';' -o "$perf_log" -e "$perf_events" -- \
            "$@" >"$stdout_log" 2>"$stderr_log"
    else
        /usr/bin/time -f $'wall_seconds;%e\nuser_seconds;%U\nsystem_seconds;%S\nmax_rss_kb;%M\nmajor_faults;%F\nminor_faults;%R\nvoluntary_context_switches;%w\ninvoluntary_context_switches;%c' \
            -o "$metrics" "$@" >"$stdout_log" 2>"$stderr_log"
    fi
    status=$?

    declare -A value=()
    while IFS=';' read -r key metric_value; do
        value["$key"]="$metric_value"
    done < "$metrics"
    echo "$safe_label,$run,$profiler,$status,${value[wall_seconds]:-},${value[user_seconds]:-},${value[system_seconds]:-},${value[max_rss_kb]:-},${value[major_faults]:-},${value[minor_faults]:-},${value[voluntary_context_switches]:-},${value[involuntary_context_switches]:-}" >> "$summary"

    if (( status != 0 )); then
        echo "Run $run failed with exit code $status; see $stderr_log" >&2
        exit "$status"
    fi
done

echo "Wrote $summary" >&2
