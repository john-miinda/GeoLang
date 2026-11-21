import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from geolang.errors import CompilerError
from geolang.native_compiler import NativeCompiler
from geolang.parser import Parser


try:
    NativeCompiler._find_msvc_environment()
except CompilerError:
    HAS_MSVC_X64 = False
else:
    HAS_MSVC_X64 = True


@unittest.skipUnless(HAS_MSVC_X64, "MSVC x64 tools are not installed")
class NativeCompilerTests(unittest.TestCase):
    def test_discovers_cl_when_environment_uses_mixed_case_path(self) -> None:
        developer_command = NativeCompiler._find_msvc_environment()
        environment = {"Path": "existing"}

        with patch("geolang.native_compiler.shutil.which", return_value=None):
            compiler = NativeCompiler._find_compiler(
                developer_command,
                environment,
            )

        if compiler is None:
            self.fail("MSVC x64 cl.exe was not discovered")
        self.assertTrue(compiler.lower().endswith(r"\hostx64\x64\cl.exe"))
        self.assertTrue(environment["Path"].startswith(str(Path(compiler).parent)))

    def compile_and_run(
        self,
        source: str,
        *,
        input_text: str | None = None,
    ) -> subprocess.CompletedProcess[str]:
        with tempfile.TemporaryDirectory() as directory:
            executable = Path(directory) / "program.exe"
            program = Parser.from_source(source).parse()
            NativeCompiler().compile(program, executable)
            return subprocess.run(
                [str(executable)],
                capture_output=True,
                text=True,
                input=input_text,
                check=False,
                timeout=10,
            )

    def test_compiles_and_runs_complete_native_program(self) -> None:
        result = self.compile_and_run(
            'function doubled(value)\n'
            'return value * 2\n'
            'end\n'
            'let count = 0\n'
            'circle wheel radius = doubled(2)\n'
            'instruction draw()\n'
            'calculate wheel\n'
            'end\n'
            'while count < 2\n'
            'perform draw()\n'
            'set count = count + 1\n'
            'end\n'
            'if count == 2\n'
            'print("native")\n'
            'print(true)\n'
            'print(0.1)\n'
            'print(2 + 3)\n'
            'else\n'
            'print(false)\n'
            'end\n'
            'let length = input_number("Length: ")\n'
            'let width = input_number("Width: ")\n'
            'print(length * width)',
            input_text="5\n3\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.count("Circle (wheel):"), 2)
        self.assertIn("Radius = 4.00", result.stdout)
        self.assertIn("native\ntrue\n0.1\n5\n", result.stdout)
        self.assertIn("Length: Width: 15\n", result.stdout)
        self.assertIn("Execution completed successfully.", result.stdout)

    def test_native_program_reports_runtime_arithmetic_failure(self) -> None:
        result = self.compile_and_run(
            "let divisor = 1\n"
            "circle wheel radius = 4 / divisor\n"
            "set divisor = 0\n"
            "calculate wheel"
        )

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("Division by zero", result.stderr)
