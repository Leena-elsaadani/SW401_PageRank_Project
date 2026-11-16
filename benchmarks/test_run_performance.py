import os
import tempfile
import unittest
from pathlib import Path

from run_performance import calculate_metrics, parse_harness_output, run_one, summarize_rows


class BenchmarkMetricTests(unittest.TestCase):
    def test_metrics_use_measured_speedup_and_skip_serial_fraction_at_one_thread(self):
        metrics = calculate_metrics(10.0, 8.0, 1)

        self.assertEqual(metrics["speedup"], 1.25)
        self.assertEqual(metrics["efficiency"], 1.25)
        self.assertIsNone(metrics["serial_fraction"])
        self.assertIsNone(metrics["amdahl_speedup"])
        self.assertIsNone(metrics["gustafson_speedup"])

    def test_karp_flatt_estimate_above_one_is_flagged_when_parallel_run_slows_down(self):
        metrics = calculate_metrics(10.0, 12.0, 4)

        self.assertGreater(metrics["serial_fraction"], 1.0)
        self.assertIn("implausible estimate", metrics["serial_fraction_flag"])

    def test_negative_karp_flatt_estimate_is_flagged(self):
        metrics = calculate_metrics(10.0, 2.0, 4)

        self.assertLess(metrics["serial_fraction"], 0.0)
        self.assertIn("implausible estimate", metrics["serial_fraction_flag"])

    def test_harness_output_requires_all_audit_fields(self):
        values = parse_harness_output(
            "nodes=6\nedges=8\niterations=12\nerror=1e-9\n"
            "elapsed_seconds=0.125\nactual_threads=4\n"
        )

        self.assertEqual(values["actual_threads"], "4")
        with self.assertRaises(ValueError):
            parse_harness_output("nodes=6\n")

    def test_summary_requires_all_successful_repetitions_and_uses_the_median(self):
        rows = []
        for implementation, threads, runtimes in (
            ("sequential", 1, [1.0, 3.0, 2.0]),
            ("openmp", 1, [1.0, 2.0, 4.0]),
        ):
            for repetition, runtime in enumerate(runtimes, 1):
                rows.append(
                    {
                        "dataset": "graph.txt",
                        "phase": "measured",
                        "implementation": implementation,
                        "requested_threads": threads,
                        "outcome": "success",
                        "solver_seconds": runtime,
                        "nodes": 3,
                        "edges": 2,
                    }
                )
        summaries = summarize_rows(rows, repetitions=3)

        self.assertEqual(summaries[0]["median_seconds"], 2.0)
        self.assertEqual(summaries[1]["median_seconds"], 2.0)
        self.assertEqual(summaries[1]["speedup"], 1.0)
        self.assertTrue(summaries[0]["complete"])
        self.assertTrue(summaries[1]["complete"])

        rows.pop()
        incomplete = summarize_rows(rows, repetitions=3)
        self.assertIsNone(incomplete[1]["median_seconds"])
        self.assertFalse(incomplete[1]["complete"])

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
            dataset = root / "graph.txt"
            dataset.write_text("0 1\n", encoding="utf-8")
            logs = root / "logs"
            logs.mkdir()

            row = run_one(
                executable,
                dataset,
                dataset.stat().st_size,
                "test-digest",
                "sequential",
                1,
                "measured",
                1,
                0.85,
                1e-8,
                100,
                0.05,
                logs,
            )

            self.assertEqual(row["outcome"], "timed_out")
            self.assertEqual(row["exit_status"], "")
            self.assertIn("timed out", Path(row["log_path"]).read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
