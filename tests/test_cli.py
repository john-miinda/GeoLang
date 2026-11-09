import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


class CommandLineTests(unittest.TestCase):
    def run_geolang(self, source: str, *arguments: str) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            source_path = Path(directory) / "program.geolang"
            source_path.write_text(source, encoding="utf-8")
            environment = os.environ.copy()
            environment["PYTHONPATH"] = str(PROJECT_ROOT / "src")
            return subprocess.run(
                [
                    sys.executable,
                    "-m",
                    "geolang",
                    *arguments,
                    str(source_path),
                ],
                cwd=PROJECT_ROOT,
                env=environment,
                capture_output=True,
                text=True,
                check=False,
                timeout=10,
            )

    def test_runs_geometry_program_and_formats_results(self) -> None:
        result = self.run_geolang(
            "circle radius = 7\ncalculate circle\n"
        )

        self.assertEqual(result.returncode, 0)
        self.assertIn("Area = 153.94", result.stdout)
        self.assertIn("Circumference = 43.98", result.stdout)
        self.assertIn("Execution completed successfully.", result.stdout)
        self.assertEqual(result.stderr, "")

    def test_runs_variable_and_control_flow_program(self) -> None:
        result = self.run_geolang(
            "let count = 0\n"
            "circle counter radius = count + 1\n"
            "while count < 2\n"
            "calculate counter\n"
            "set count = count + 1\n"
            "end"
        )

        self.assertEqual(result.returncode, 0)
        self.assertEqual(result.stdout.count("Circle (counter):"), 2)
        self.assertIn("Radius = 1.00", result.stdout)
        self.assertIn("Radius = 2.00", result.stdout)

    def test_reports_lexical_error_without_traceback(self) -> None:
        result = self.run_geolang("circle radius = 7\n@")

        self.assertEqual(result.returncode, 1)
        self.assertIn("GeoLang Lexical Error:", result.stderr)
        self.assertIn("Line 2, Column 1", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_reports_syntax_error_without_traceback(self) -> None:
        result = self.run_geolang("calculate\n")

        self.assertEqual(result.returncode, 1)
        self.assertIn("GeoLang Syntax Error:", result.stderr)
        self.assertIn("Expected a geometry type or shape name", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_reports_semantic_error_without_traceback(self) -> None:
        result = self.run_geolang("circle radius = -1")

        self.assertEqual(result.returncode, 1)
        self.assertIn("GeoLang Semantic Error:", result.stderr)
        self.assertIn("cannot be negative", result.stderr)
        self.assertNotIn("Traceback", result.stderr)

    def test_reports_runtime_error_without_partial_success_output(self) -> None:
        result = self.run_geolang(
            f"square side = {10**200}\ncalculate square"
        )

        self.assertEqual(result.returncode, 1)
        self.assertIn("GeoLang Runtime Error:", result.stderr)
        self.assertIn("supported numeric range", result.stderr)
        self.assertNotIn("Traceback", result.stderr)
        self.assertEqual(result.stdout, "")

    def test_token_inspection_remains_available(self) -> None:
        result = self.run_geolang("circle radius = 7", "--tokens")

        self.assertEqual(result.returncode, 0)
        self.assertIn("CIRCLE", result.stdout)
        self.assertIn("NUMBER", result.stdout)
        self.assertNotIn("Execution completed successfully", result.stdout)


if __name__ == "__main__":
    unittest.main()
