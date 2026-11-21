import contextlib
import io
import unittest
from unittest.mock import patch

from geolang.compiler import PythonCompiler
from geolang.errors import SemanticError
from geolang.parser import Parser


class PythonCompilerTests(unittest.TestCase):
    def compile_and_run(self, source: str) -> tuple[str, dict[str, object]]:
        generated = PythonCompiler().compile(Parser.from_source(source).parse())
        bytecode = compile(generated, "<compiled-geolang>", "exec")
        namespace: dict[str, object] = {}
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            exec(bytecode, namespace)
        return output.getvalue(), namespace

    def test_compiles_functions_instructions_and_geometry_to_python(self) -> None:
        output, namespace = self.compile_and_run(
            "function doubled(value)\n"
            "return value * 2\n"
            "end\n"
            "circle wheel radius = doubled(2)\n"
            "instruction draw()\n"
            "calculate wheel\n"
            "end\n"
            "perform draw()"
        )

        self.assertIn("Radius = 4.00", output)
        self.assertIn("Area = 50.27", output)
        self.assertIn("Execution completed successfully.", output)
        self.assertIn("_calculate", namespace)

    def test_compiles_control_flow_and_variable_assignments(self) -> None:
        output, _ = self.compile_and_run(
            "let count = 0\n"
            "while count < 2\n"
            "set count = count + 1\n"
            "end\n"
            "square result side = count\n"
            "calculate result"
        )

        self.assertIn("Side = 2.00", output)
        self.assertIn("Area = 4.00", output)

    def test_compiled_function_completion_error_is_valid_python(self) -> None:
        generated = PythonCompiler().compile(
            Parser.from_source(
                "function doubled(value)\n"
                "return value * 2\n"
                "end\n"
                "let answer = doubled(3)"
            ).parse()
        )

        compile(generated, "<compiled-geolang>", "exec")
        self.assertIn(
            "GeoLang function 'doubled' completed without returning",
            generated,
        )

    def test_compiler_rejects_mutated_dimension_division_by_zero_at_runtime(self) -> None:
        with self.assertRaises(RuntimeError) as error:
            self.compile_and_run(
                "let denominator = 1\n"
                "circle wheel radius = 10 / denominator\n"
                "set denominator = 0\n"
                "calculate wheel"
            )

        self.assertIn("Division by zero", str(error.exception))

    def test_compiles_strings_booleans_and_print(self) -> None:
        output, _ = self.compile_and_run(
            'print("hello")\n'
            "print(true)\n"
            "print(false)"
        )

        self.assertEqual(output.splitlines()[:3], ["hello", "true", "false"])

    def test_compiled_program_reads_numbers_for_custom_formula(self) -> None:
        generated = PythonCompiler().compile(
            Parser.from_source(
                'let length = input_number("Length: ")\n'
                'let width = input_number("Width: ")\n'
                "print(length * width)"
            ).parse()
        )
        output = io.StringIO()
        namespace: dict[str, object] = {}
        with patch("builtins.input", side_effect=["5", "3"]):
            with contextlib.redirect_stdout(output):
                exec(compile(generated, "<compiled-geolang>", "exec"), namespace)

        self.assertIn("15", output.getvalue().splitlines())

    def test_rejects_semantically_invalid_program(self) -> None:
        with self.assertRaises(SemanticError) as error:
            PythonCompiler().compile(Parser.from_source("square side = 0").parse())

        self.assertIn("greater than zero", str(error.exception))


if __name__ == "__main__":
    unittest.main()
