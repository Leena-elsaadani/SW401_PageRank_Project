import csv
import contextlib
import io
import json
import math
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from run_performance import (
    DEFAULT_TOLERANCE,
    CONFIGURATIONS,
    amdahl_speedup,
    append_raw_row,
    append_unstarted_attempts,
    build_parser,
    calculate_metrics,
    check_dataset_resources,
    environment_metadata,
    generate_report,
    gustafson_speedup,
    git_metadata,
    initialize_raw_csv,
    karp_flatt_from_speedup,
    markdown_cell,
    make_schedule,
    parse_harness_output,
    parse_trial_status,
    requested_datasets,
    record_dataset_validation,
    run_one,
    sample_cv,
    summarize_rows,
    synthetic_row,
    write_plots,
)


def valid_harness_fields(**overrides):
    values = {
        "nodes": "6",
        "edges": "8",
        "actual_threads": "2",
        "solver_iterations": "12",
        "solver_error": "1e-8",
        "solver_converged": "true",
        "rank_sum": "1.0",
        "rank_sum_valid": "true",
        "top10": "0:0.2;1:0.1",
        "solver_seconds": "0.125",
        "average_iteration_seconds": "0.01",
        "graph_load_seconds": "0.002",
        "peak_rss_kib": "1024",
        "sequential_verification_iterations": "12",
        "sequential_verification_error": "1e-8",
        "sequential_verification_converged": "true",
        "sequential_verification_rank_sum": "1.0",
        "sequential_verification_rank_sum_valid": "true",
        "sequential_verification_top10": "0:0.2;1:0.1",
        "iteration_counts_match": "true",
        "max_abs_difference": "0.0",
        "numerical_consistency": "true",
        "comparison_tolerance": "1e-6",
    }
    values.update(overrides)
    return values


class BenchmarkConfigurationTests(unittest.TestCase):
    def test_project_default_tolerance_and_five_repetitions(self):
        args = build_parser().parse_args([])

        self.assertEqual(args.tolerance, 1e-6)
        self.assertEqual(args.tolerance, DEFAULT_TOLERANCE)
        self.assertEqual(args.repetitions, 5)
        self.assertEqual(args.max_iterations, 100)

    def test_custom_tolerance_is_retained_and_warned(self):
        args = build_parser().parse_args(["--tolerance", "1e-5"])
        parser = build_parser()

        with mock.patch("sys.stderr") as stderr:
            from run_performance import validate_args

            validate_args(parser, args)
            warning = "".join(call.args[0] for call in stderr.write.call_args_list)
            self.assertIn("non-default tolerance", warning)

    def test_explicit_dataset_paths_are_normalized(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "graph.txt"
            path.write_text("0 1\n", encoding="utf-8")
            self.assertEqual(requested_datasets([path], False), [path.resolve()])

    def test_execution_order_is_reproducible_and_interleaved(self):
        dataset = {"name": "graph", "kind": "custom_input"}

        first = make_schedule([dataset], warmups=1, repetitions=3, seed=47)
        second = make_schedule([dataset], warmups=1, repetitions=3, seed=47)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 4 * len(CONFIGURATIONS))
        measured_first_round = [
            (row["implementation"], row["threads"])
            for row in first if row["phase"] == "measured" and row["repetition"] == 1
        ]
        self.assertEqual(set(measured_first_round), set(CONFIGURATIONS))
        self.assertNotEqual(measured_first_round, CONFIGURATIONS)


class BenchmarkMetricTests(unittest.TestCase):
    def test_amdahl_predictions_project_p2_estimate_to_p4_and_p8(self):
        metrics = calculate_metrics(10.0, {1: 8.0, 2: 5.0, 4: 2.5, 8: 1.25})

        self.assertEqual(metrics[2]["karp_flatt_p2"], 0.0)
        self.assertIsNone(metrics[2]["amdahl_prediction_from_p2"])
        self.assertEqual(metrics[4]["amdahl_prediction_from_p2"], 4.0)
        self.assertEqual(metrics[8]["amdahl_prediction_from_p2"], 8.0)
        self.assertEqual(metrics[4]["sequential_speedup"], 4.0)
        self.assertEqual(metrics[4]["openmp_self_speedup"], 3.2)

    def test_karp_flatt_out_of_range_disables_amdahl_projections(self):
        metrics = calculate_metrics(10.0, {1: 9.0, 2: 20.0, 4: 3.0, 8: 2.0})

        self.assertEqual(metrics[4]["karp_flatt_status"], "out_of_range")
        self.assertIsNone(metrics[4]["amdahl_prediction_from_p2"])

    def test_undefined_or_invalid_metrics_are_not_fabricated(self):
        self.assertIsNone(amdahl_speedup(-0.1, 4))
        self.assertIsNone(amdahl_speedup(0.5, 0))
        self.assertEqual(gustafson_speedup(0.25, 4), 3.25)
        self.assertIsNone(gustafson_speedup(float("nan"), 4))
        with self.assertRaises(ValueError):
            calculate_metrics(0.0, {1: 1.0})
        with self.assertRaises(ValueError):
            calculate_metrics(1.0, {1: 0.0})

    def test_cv_requires_multiple_values(self):
        self.assertIsNone(sample_cv([1.0]))
        self.assertGreater(sample_cv([1.0, 2.0, 3.0]), 0.0)

    def test_invalid_thread_count_and_nonfinite_serial_estimate_are_unavailable(self):
        self.assertIsNone(karp_flatt_from_speedup(2.0, 1))
        self.assertIsNone(karp_flatt_from_speedup(float("nan"), 4))

    def test_summary_uses_successful_measured_median_and_preserves_failures(self):
        dataset = {"name": "graph.txt", "kind": "custom_input", "state": "available"}
        rows = []
        for implementation, threads, runtimes in (
            ("sequential", 1, [1.0, 3.0, 2.0]),
            ("openmp", 1, [1.0, 2.0, 4.0]),
            ("openmp", 2, [0.5, 1.0, 1.5]),
        ):
            for runtime in runtimes:
                row = {
                    "dataset": "graph.txt",
                    "phase": "measured",
                    "implementation": implementation,
                    "requested_threads": threads,
                    "outcome": "success",
                    "solver_seconds": runtime,
                    "peak_rss_kib": 1000,
                    "nodes": 3,
                    "edges": 2,
                }
                rows.append(row)
        rows.append(
            {
                "dataset": "graph.txt",
                "phase": "measured",
                "implementation": "openmp",
                "requested_threads": 4,
                "outcome": "timed_out",
                "solver_seconds": "",
                "peak_rss_kib": "",
            }
        )
        summaries = summarize_rows(rows, repetitions=3, datasets=[dataset])
        sequential = next(row for row in summaries if row["implementation"] == "sequential")
        omp2 = next(row for row in summaries if row["implementation"] == "openmp" and row["threads"] == 2)
        omp4 = next(row for row in summaries if row["implementation"] == "openmp" and row["threads"] == 4)

        self.assertEqual(sequential["median_seconds"], 2.0)
        self.assertEqual(sequential["minimum_seconds"], 1.0)
        self.assertEqual(sequential["maximum_seconds"], 3.0)
        self.assertEqual(sequential["median_peak_rss_kib"], 1000.0)
        self.assertTrue(math.isclose(sequential["coefficient_of_variation"], 0.5))
        self.assertEqual(omp2["sequential_speedup"], 2.0)
        self.assertFalse(omp4["complete"])
        self.assertEqual(omp4["status"], "timed_out")

    def test_available_speedups_survive_missing_p2_configuration(self):
        dataset = {"name": "graph.txt", "kind": "custom_input", "state": "available"}
        rows = []
        for implementation, threads, outcome, runtime in (
            ("sequential", 1, "success", 10.0),
            ("openmp", 1, "success", 8.0),
            ("openmp", 2, "timed_out", None),
            ("openmp", 4, "success", 2.0),
        ):
            for repetition in range(3):
                rows.append({
                    "dataset": "graph.txt",
                    "phase": "measured",
                    "implementation": implementation,
                    "requested_threads": threads,
                    "outcome": outcome,
                    "solver_seconds": runtime,
                    "peak_rss_kib": 1000 if runtime is not None else "",
                    "nodes": 3,
                    "edges": 2,
                })
        summaries = summarize_rows(rows, repetitions=3, datasets=[dataset])
        omp4 = next(
            row for row in summaries
            if row["implementation"] == "openmp" and row["threads"] == 4
        )

        self.assertEqual(omp4["sequential_speedup"], 5.0)
        self.assertEqual(omp4["openmp_self_speedup"], 4.0)
        self.assertEqual(omp4["efficiency"], 1.25)
        self.assertEqual(omp4["karp_flatt_status"], "unavailable")
        self.assertIsNone(omp4["amdahl_prediction_from_p2"])


class BenchmarkValidationTests(unittest.TestCase):
    def test_harness_output_requires_every_audit_field(self):
        output = "\n".join(f"{key}={value}" for key, value in valid_harness_fields().items())
        self.assertEqual(parse_harness_output(output)["actual_threads"], "2")
        with self.assertRaises(ValueError):
            parse_harness_output("nodes=6\n")

    def test_nonconverged_solver_is_not_a_success(self):
        parsed = valid_harness_fields(solver_converged="false")
        status, _ = parse_trial_status(parsed, "sequential", 1e-6, 1e-6)
        self.assertEqual(status, "non_converged")

    def test_openmp_reference_and_numerical_failures_are_rejected(self):
        cases = (
            ({"rank_sum_valid": "false"}, "rank_sum_invalid"),
            ({"sequential_verification_converged": "false"}, "reference_non_converged"),
            ({"numerical_consistency": "false"}, "numerical_mismatch"),
        )
        for overrides, expected in cases:
            with self.subTest(expected=expected):
                status, _ = parse_trial_status(
                    valid_harness_fields(**overrides), "openmp", 1e-6, 1e-6
                )
                self.assertEqual(status, expected)

    def test_openmp_thread_mismatch_is_caught_by_runner(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "fake_harness"
            output = valid_harness_fields(actual_threads="1")
            executable.write_text(
                "#!/usr/bin/env python3\nprint("
                + repr("\n".join(f"{key}={value}" for key, value in output.items()))
                + ")\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            graph = root / "graph.txt"
            graph.write_text("0 1\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            row = run_one(
                executable, {"name": "graph.txt", "kind": "custom_input", "path": str(graph),
                             "bytes": graph.stat().st_size, "sha256": "digest"},
                "openmp", 2, "measured", 1, 1, 0.85, 1e-6, 100, 1e-6, 3, logs,
                {"OMP_NUM_THREADS": "2"},
            )
            self.assertEqual(row["outcome"], "thread_mismatch")
            self.assertEqual(row["actual_threads"], "1")

    def test_iteration_count_difference_is_recorded_not_auto_rejected(self):
        parsed = valid_harness_fields(
            sequential_verification_iterations="13",
            iteration_counts_match="false",
        )
        status, _ = parse_trial_status(parsed, "openmp", 1e-6, 1e-6)
        self.assertEqual(status, "success")

    def test_unstarted_attempts_are_persisted_after_interruption(self):
        dataset = {"name": "graph", "kind": "custom_input", "path": "/tmp/graph"}
        schedule = make_schedule([dataset], warmups=0, repetitions=1, seed=3)
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            raw = initialize_raw_csv(root / "raw.csv")
            manifest = {
                "completed_attempts": 0,
                "run_directory": str(root),
            }
            rows = []
            try:
                append_unstarted_attempts(
                    schedule, rows, raw, manifest, "not_run_interrupted"
                )
            finally:
                raw.close()
            self.assertEqual(len(rows), len(CONFIGURATIONS))
            self.assertTrue(all(row["outcome"] == "not_run_interrupted" for row in rows))
            with (root / "raw.csv").open(newline="", encoding="utf-8") as source:
                self.assertEqual(len(list(csv.DictReader(source))), len(CONFIGURATIONS))

    def test_incremental_raw_results_are_flushed_after_each_completed_trial(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "raw.csv"
            handle = initialize_raw_csv(path)
            try:
                append_raw_row(handle, {"dataset": "one", "outcome": "failed"})
                with path.open(newline="", encoding="utf-8") as source:
                    self.assertEqual(len(list(csv.DictReader(source))), 1)
                append_raw_row(handle, {"dataset": "two", "outcome": "success"})
            finally:
                handle.close()
            with path.open(newline="", encoding="utf-8") as source:
                self.assertEqual(len(list(csv.DictReader(source))), 2)

    def test_interruption_preserves_completed_attempt_and_marks_remaining_schedule(self):
        from run_performance import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / "graph.txt"
            graph.write_text("0 1\n1 0\n", encoding="utf-8")
            output = root / "results"
            real_subprocess_run = subprocess.run

            def fake_subprocess_run(command, *args, **kwargs):
                if command[0] == "git":
                    return real_subprocess_run(command, *args, **kwargs)
                if command[0] == "wsl.exe":
                    return subprocess.CompletedProcess(
                        command, 0, stdout="WSL version: test".encode("utf-16le")
                    )
                return subprocess.CompletedProcess(command, 0, stdout="g++ test version\n")

            def interrupted_run(*args, **kwargs):
                dataset, implementation, threads, phase, repetition, order = args[1:7]
                if interrupted_run.calls:
                    raise KeyboardInterrupt
                interrupted_run.calls = 1
                row = synthetic_row(
                    dataset, implementation, threads, phase, repetition, order,
                    "success", "simulated completed attempt",
                )
                row.update({"solver_seconds": "0.1", "peak_rss_kib": "1024", "nodes": "2", "edges": "2"})
                return row

            interrupted_run.calls = 0
            with (
                mock.patch("run_performance.shutil.which", return_value="g++"),
                mock.patch("run_performance.subprocess.run", side_effect=fake_subprocess_run),
                mock.patch("run_performance.run_one", side_effect=interrupted_run),
            ):
                exit_code = main([
                    "--dataset", str(graph),
                    "--output-root", str(output),
                    "--repetitions", "3",
                    "--warmups", "0",
                    "--no-plots",
                ])

            run = next(output.iterdir())
            with (run / "raw_runs.csv").open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(exit_code, 130)
            self.assertEqual(manifest["status"], "interrupted")
            self.assertEqual(len(rows), len(CONFIGURATIONS) * 3)
            self.assertEqual(sum(row["outcome"] == "success" for row in rows), 1)
            self.assertEqual(sum(row["outcome"] == "not_run_interrupted" for row in rows), len(rows) - 1)

    def test_abnormal_exit_is_recorded(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / "graph.txt"
            graph.write_text("0 1\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            with (
                mock.patch("run_performance.cgroup_oom_kill_count", return_value=None),
                mock.patch(
                    "run_performance.subprocess.run",
                    return_value=subprocess.CompletedProcess(["harness"], -15, stdout=""),
                ),
            ):
                row = run_one(
                    root / "harness",
                    {"name": "graph.txt", "kind": "custom_input", "path": str(graph),
                     "bytes": graph.stat().st_size, "sha256": "digest"},
                    "sequential", 1, "measured", 1, 1, 0.85, 1e-6, 100, 1e-6, 3,
                    logs, {"OMP_NUM_THREADS": "1"},
                )
            self.assertEqual(row["outcome"], "abnormal_exit")
            self.assertEqual(row["exit_status"], -15)

    def test_confirmed_oom_exit_is_recorded_as_memory_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / "graph.txt"
            graph.write_text("0 1\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            with (
                mock.patch("run_performance.cgroup_oom_kill_count", side_effect=[2, 3]),
                mock.patch(
                    "run_performance.subprocess.run",
                    return_value=subprocess.CompletedProcess(["harness"], -9, stdout=""),
                ),
            ):
                row = run_one(
                    root / "harness",
                    {"name": "graph.txt", "kind": "custom_input", "path": str(graph),
                     "bytes": graph.stat().st_size, "sha256": "digest"},
                    "sequential", 1, "measured", 1, 1, 0.85, 1e-6, 100, 1e-6, 3,
                    logs, {"OMP_NUM_THREADS": "1"},
                )
            self.assertEqual(row["outcome"], "memory_aborted")
            self.assertIn("OOM kill counter increased", Path(row["log_path"]).read_text(encoding="utf-8"))

    @unittest.skipUnless(os.name == "posix", "executing temporary POSIX helpers is Linux-specific")
    def test_timeout_is_recorded_as_a_failed_attempt(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            executable = root / "sleeper"
            executable.write_text(
                "#!/usr/bin/env python3\nimport time\ntime.sleep(1)\n",
                encoding="utf-8",
            )
            executable.chmod(0o755)
            graph = root / "graph.txt"
            graph.write_text("0 1\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()
            row = run_one(
                executable, {"name": "graph.txt", "kind": "custom_input", "path": str(graph),
                             "bytes": graph.stat().st_size, "sha256": "digest"},
                "sequential", 1, "measured", 1, 1, 0.85, 1e-6, 100, 1e-6, 0.05, logs,
                {"OMP_NUM_THREADS": "1"},
            )
            self.assertEqual(row["outcome"], "timed_out")
            self.assertIn("timed out", Path(row["log_path"]).read_text(encoding="utf-8"))

    def test_default_report_does_not_overwrite_main_report(self):
        from run_performance import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            hand_report = Path(__file__).resolve().parents[1] / "report" / "performance_evaluation.md"
            before = hand_report.read_bytes()
            missing = root / "missing_graph.txt"
            output = root / "results"
            exit_code = main([
                "--dataset", str(missing),
                "--output-root", str(output),
                "--no-plots",
            ])
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(hand_report.read_bytes(), before)
            run = next(output.iterdir())
            self.assertTrue((run / "generated_report.md").is_file())
            self.assertTrue((run / "raw_runs.csv").is_file())

    def test_explicit_update_report_option_targets_main_report(self):
        from run_performance import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            report = root / "report" / "performance_evaluation.md"
            report.parent.mkdir()
            report.write_text("human-authored report\n", encoding="utf-8")
            missing = root / "missing_graph.txt"
            with mock.patch("run_performance.ROOT", root):
                exit_code = main([
                    "--dataset", str(missing),
                    "--output-root", str(root / "results"),
                    "--update-report",
                    "--no-plots",
                ])
            self.assertNotEqual(exit_code, 0)
            self.assertNotEqual(report.read_text(encoding="utf-8"), "human-authored report\n")
            self.assertIn("incomplete", report.read_text(encoding="utf-8"))

    def test_missing_dataset_is_nonzero_and_recorded_in_outputs(self):
        from run_performance import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            output = root / "results"
            exit_code = main([
                "--dataset", str(root / "absent.txt"),
                "--output-root", str(output),
                "--no-plots",
            ])
            self.assertNotEqual(exit_code, 0)
            run = next(output.iterdir())
            manifest = json.loads((run / "run_manifest.json").read_text(encoding="utf-8"))
            self.assertEqual(manifest["status"], "incomplete")
            with (run / "raw_runs.csv").open(newline="", encoding="utf-8") as source:
                raw = list(csv.DictReader(source))
            self.assertTrue(raw)
            self.assertTrue(all(row["outcome"] == "missing_dataset" for row in raw))

    def test_environment_metadata_records_repository_and_openmp_settings(self):
        metadata = environment_metadata(
            "g++", "GCC test", "-O3", 5, 1, 9, 0.85, 1e-6, 100, 1e-6,
            {"OMP_NUM_THREADS": "2", "OMP_PLACES": "cores", "OMP_PROC_BIND": "close"},
            "test-run",
        )
        for key in ("physical_core_count", "logical_processor_count", "available_system_memory_bytes",
                    "linux_distribution", "wsl_detected", "cpu_governor", "git", "omp_environment"):
            self.assertIn(key, metadata)
        self.assertEqual(metadata["omp_environment"]["OMP_PROC_BIND"], "close")

    def test_unavailable_environment_fields_are_explicit(self):
        with (
            mock.patch("run_performance.lscpu_values", return_value={}),
            mock.patch("run_performance.cpu_model", return_value=None),
            mock.patch("run_performance.os.cpu_count", return_value=None),
            mock.patch("run_performance.available_memory_bytes", return_value=None),
            mock.patch("run_performance.git_metadata", return_value={
                "branch": "unavailable",
                "commit": "unavailable",
                "working_tree_dirty": "unavailable",
            }),
            mock.patch("run_performance.shutil.which", return_value=None),
        ):
            metadata = environment_metadata(
                None, None, "-O3", 3, 1, 7, 0.85, 1e-6, 100, 1e-6, {}, "test-run"
            )

        self.assertEqual(metadata["physical_core_count"], "unavailable")
        self.assertEqual(metadata["logical_processor_count"], "unavailable")
        self.assertEqual(metadata["available_system_memory_bytes"], "unavailable")
        self.assertEqual(metadata["available_system_memory_gib"], "unavailable")
        self.assertEqual(metadata["cpu_model"], "unavailable")

    def test_failed_git_metadata_does_not_claim_clean_tree(self):
        with mock.patch("run_performance.subprocess.run", side_effect=OSError("git unavailable")):
            metadata = git_metadata()

        self.assertEqual(metadata["branch"], "unavailable")
        self.assertEqual(metadata["commit"], "unavailable")
        self.assertEqual(metadata["working_tree_dirty"], "unavailable")

    def test_dataset_count_mismatch_is_visible_and_invalidates_summary(self):
        dataset = {
            "name": "livejournal_100MB.txt",
            "path": "/tmp/livejournal_100MB.txt",
            "kind": "prefix_sample",
            "state": "available",
            "bytes": 104_857_589,
            "sha256": "digest",
            "expected_documentation": {"expected_edges": 8_015_157},
            "validation_notes": ["existing note", "existing note"],
        }
        rows = [{
            "dataset": dataset["name"],
            "nodes": "6",
            "edges": "7",
            "outcome": "success",
        }]
        record_dataset_validation(dataset, rows)

        self.assertEqual(dataset["validation"], "count_mismatch")
        self.assertEqual(dataset["state"], "dataset_validation_mismatch")
        self.assertTrue(any("Observed 7 directed records" in note for note in dataset["validation_notes"]))
        self.assertEqual(dataset["validation_notes"].count("existing note"), 1)

    def test_markdown_table_cells_escape_pipes_and_collapse_newlines(self):
        self.assertEqual(markdown_cell("WSL 3\nKernel | details"), r"WSL 3<br>Kernel \| details")

    def test_plots_label_failed_configurations_and_theoretical_references(self):
        summaries = [{
            "dataset": "graph.txt",
            "implementation": "sequential",
            "threads": 1,
            "median_seconds": 10.0,
            "minimum_seconds": 9.0,
            "maximum_seconds": 11.0,
        }]
        for threads, runtime in ((1, 8.0), (2, 5.0), (4, 2.5)):
            speedup = 10.0 / runtime
            summaries.append({
                "dataset": "graph.txt",
                "implementation": "openmp",
                "threads": threads,
                "median_seconds": runtime,
                "minimum_seconds": runtime * 0.9,
                "maximum_seconds": runtime * 1.1,
                "status": "complete",
                "sequential_speedup": speedup,
                "openmp_self_speedup": 8.0 / runtime,
                "efficiency": speedup / threads,
                "karp_flatt_p2": 0.0,
                "karp_flatt_status": "valid",
                "amdahl_prediction_from_p2": 4.0 if threads == 4 else None,
                "amdahl_prediction_difference": 0.0 if threads == 4 else None,
            })
        summaries.append({
            "dataset": "graph.txt",
            "implementation": "openmp",
            "threads": 8,
            "median_seconds": None,
            "minimum_seconds": None,
            "maximum_seconds": None,
            "status": "timed_out",
            "sequential_speedup": None,
            "openmp_self_speedup": None,
            "efficiency": None,
            "karp_flatt_p2": 0.0,
            "karp_flatt_status": "valid",
            "amdahl_prediction_from_p2": None,
            "amdahl_prediction_difference": None,
        })

        import matplotlib.pyplot as plt

        axes = []
        original_subplots = plt.subplots

        def capture_subplots(*args, **kwargs):
            figure, axis = original_subplots(*args, **kwargs)
            axes.append(axis)
            return figure, axis

        with tempfile.TemporaryDirectory() as temporary:
            with mock.patch("matplotlib.pyplot.subplots", side_effect=capture_subplots):
                generated = write_plots(summaries, Path(temporary))

            self.assertEqual(len(generated), 7)
            self.assertTrue(all(Path(plot).is_file() for plot in generated))
            self.assertEqual(axes[0].get_ylabel(), "Solver runtime (s)")
            self.assertIn(
                "Unavailable configurations: 8 thread(s): timed_out",
                [text.get_text() for text in axes[0].texts],
            )
            speedup_labels = axes[1].get_legend_handles_labels()[1]
            self.assertIn("Ideal linear scaling", speedup_labels)
            self.assertEqual(
                [text.get_text() for text in axes[4].get_legend().get_texts()],
                ["Sequential", "OpenMP"],
            )
            self.assertEqual(axes[3].get_ylabel(), "Efficiency (ratio)")
            amdahl_labels = axes[5].get_legend_handles_labels()[1]
            self.assertIn("Amdahl prediction from P=2 estimate", amdahl_labels)
            self.assertEqual(axes[6].get_ylabel(), "Estimated fraction")

    def test_low_memory_guard_reports_unavailable_measurement_and_abort(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dataset.txt"
            with path.open("wb") as target:
                target.truncate(700 * 1024 * 1024)
            with mock.patch("run_performance.available_memory_bytes", return_value=2 * 1024**3):
                allowed, metadata = check_dataset_resources(path)
            self.assertFalse(allowed)
            self.assertEqual(metadata["decision"], "memory_aborted")
            self.assertFalse(metadata["working_set_estimate_is_measured"])

    def test_unavailable_memory_is_reported_and_warns_before_proceeding(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "dataset.txt"
            path.write_text("0 1\n", encoding="utf-8")
            stderr = io.StringIO()
            with (
                mock.patch("run_performance.available_memory_bytes", return_value=None),
                contextlib.redirect_stderr(stderr),
            ):
                allowed, metadata = check_dataset_resources(path)

        self.assertTrue(allowed)
        self.assertEqual(metadata["available_system_memory_bytes"], "unavailable")
        self.assertEqual(metadata["decision"], "warning_memory_unavailable")
        self.assertIn("could not be determined", stderr.getvalue())

    def test_memory_guard_failure_is_recorded_in_runner_outputs(self):
        from run_performance import main

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            graph = root / "large_graph.txt"
            with graph.open("wb") as target:
                target.truncate(700 * 1024 * 1024)
            output = root / "results"
            with mock.patch(
                "run_performance.check_dataset_resources",
                return_value=(False, {
                    "decision": "memory_aborted",
                    "available_system_memory_bytes": 100,
                    "working_set_estimate_is_measured": False,
                }),
            ):
                exit_code = main([
                    "--dataset", str(graph),
                    "--include-full",
                    "--output-root", str(output),
                    "--repetitions", "3",
                    "--warmups", "0",
                    "--no-plots",
                ])

            run = next(output.iterdir())
            with (run / "raw_runs.csv").open(newline="", encoding="utf-8") as source:
                rows = list(csv.DictReader(source))
            self.assertNotEqual(exit_code, 0)
            self.assertEqual(len(rows), len(CONFIGURATIONS) * 3)
            self.assertTrue(all(row["outcome"] == "memory_aborted" for row in rows))


if __name__ == "__main__":
    unittest.main()
