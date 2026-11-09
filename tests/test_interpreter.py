import math
import unittest

from geolang.errors import RuntimeGeoLangError
from geolang.interpreter import Interpreter, format_number
from geolang.lexer import TokenType
from geolang.parser import Parser


class InterpreterTests(unittest.TestCase):
    def execute(self, source: str):
        return Interpreter().execute(Parser.from_source(source).parse())

    def test_calculates_circle_triangle_rectangle_and_square(self) -> None:
        results = self.execute(
            "circle radius = 7\n"
            "triangle base = 10 height = 6\n"
            "rectangle length = 12 width = 5\n"
            "square side = 4\n"
            "calculate circle\n"
            "calculate triangle\n"
            "calculate rectangle\n"
            "calculate square"
        )

        self.assertEqual(
            [result.kind for result in results],
            [
                TokenType.CIRCLE,
                TokenType.TRIANGLE,
                TokenType.RECTANGLE,
                TokenType.SQUARE,
            ],
        )
        self.assertAlmostEqual(dict(results[0].measurements)["area"], math.pi * 49)
        self.assertAlmostEqual(
            dict(results[0].measurements)["circumference"], math.pi * 14
        )
        self.assertEqual(dict(results[1].measurements), {"area": 30.0})
        self.assertEqual(
            dict(results[2].measurements),
            {"area": 60, "perimeter": 34},
        )
        self.assertEqual(
            dict(results[3].measurements),
            {"area": 16, "perimeter": 16},
        )

    def test_calculates_triangle_area_and_perimeter_from_three_sides(self) -> None:
        (result,) = self.execute(
            "triangle side_a = 3 side_b = 4 side_c = 5\ncalculate triangle"
        )

        self.assertAlmostEqual(dict(result.measurements)["area"], 6)
        self.assertEqual(dict(result.measurements)["perimeter"], 12)

    def test_calculates_named_shapes_using_variables(self) -> None:
        results = self.execute(
            "let radius = 3\n"
            "let wheel_radius = radius * 2\n"
            "circle wheel radius = wheel_radius\n"
            "circle coin radius = radius\n"
            "calculate wheel\n"
            "calculate coin"
        )

        self.assertEqual([result.name for result in results], ["wheel", "coin"])
        self.assertEqual(dict(results[0].dimensions), {"radius": 6})
        self.assertEqual(dict(results[1].dimensions), {"radius": 3})

    def test_function_returns_value_used_in_geometry_expression(self) -> None:
        (result,) = self.execute(
            "function squared(value)\n"
            "return value * value\n"
            "end\n"
            "let radius = squared(3)\n"
            "circle wheel radius = radius\n"
            "calculate wheel"
        )

        self.assertEqual(dict(result.dimensions), {"radius": 9})

    def test_instruction_executes_a_reusable_calculation(self) -> None:
        results = self.execute(
            "circle wheel radius = 2\n"
            "instruction draw()\n"
            "calculate wheel\n"
            "end\n"
            "perform draw()\n"
            "perform draw()"
        )

        self.assertEqual(len(results), 2)
        self.assertEqual([result.name for result in results], ["wheel", "wheel"])

    def test_function_calls_another_function(self) -> None:
        (result,) = self.execute(
            "function double(value)\n"
            "return value * 2\n"
            "end\n"
            "function add_one(value)\n"
            "return double(value) + 1\n"
            "end\n"
            "circle wheel radius = add_one(3)\n"
            "calculate wheel"
        )

        self.assertEqual(dict(result.dimensions), {"radius": 7})

    def test_recursive_function_call_has_a_runtime_depth_limit(self) -> None:
        with self.assertRaises(RuntimeGeoLangError) as error:
            self.execute(
                "function repeat(value)\n"
                "return repeat(value)\n"
                "end\n"
                "let result = repeat(1)"
            )

        self.assertIn("call-depth limit", str(error.exception))

    def test_if_else_executes_only_the_matching_branch(self) -> None:
        results = self.execute(
            "let value = 2\n"
            "circle small radius = 3\n"
            "circle large radius = 5\n"
            "if value < 3\n"
            "calculate small\n"
            "else\n"
            "calculate large\n"
            "end"
        )

        self.assertEqual([result.name for result in results], ["small"])

    def test_supports_all_comparison_operators(self) -> None:
        results = self.execute(
            "circle check radius = 1\n"
            "if 2 != 3\ncalculate check\nend\n"
            "if 3 > 2\ncalculate check\nend\n"
            "if 3 >= 3\ncalculate check\nend\n"
            "if 2 <= 3\ncalculate check\nend"
        )

        self.assertEqual(len(results), 4)

    def test_while_repeats_and_uses_updated_variables(self) -> None:
        results = self.execute(
            "let count = 0\n"
            "circle counter radius = count + 1\n"
            "while count < 3\n"
            "calculate counter\n"
            "set count = count + 1\n"
            "end"
        )

        self.assertEqual(
            [dict(result.dimensions)["radius"] for result in results],
            [1, 2, 3],
        )

    def test_loop_iteration_limit_prevents_infinite_execution(self) -> None:
        with self.assertRaises(RuntimeGeoLangError) as error:
            self.execute(
                "let count = 0\n"
                "while count >= 0\n"
                "set count = count + 1\n"
                "end"
            )

        self.assertIn("iteration limit", str(error.exception))

    def test_runtime_checks_mutated_geometry_dimensions(self) -> None:
        with self.assertRaises(RuntimeGeoLangError) as error:
            self.execute(
                "let side = 1\n"
                "square box side = side\n"
                "set side = 0\n"
                "calculate box"
            )

        self.assertIn("must be greater than zero", str(error.exception))

    def test_shape_uses_variable_value_after_loop_finishes(self) -> None:
        (result,) = self.execute(
            "let count = 0\n"
            "while count < 3\n"
            "set count = count + 1\n"
            "end\n"
            "square result side = count\n"
            "calculate result"
        )

        self.assertEqual(dict(result.dimensions), {"side": 3})

    def test_variable_can_capture_loop_result(self) -> None:
        (result,) = self.execute(
            "let count = 0\n"
            "while count < 3\n"
            "set count = count + 1\n"
            "end\n"
            "let final_count = count\n"
            "square result side = final_count\n"
            "calculate result"
        )

        self.assertEqual(dict(result.dimensions), {"side": 3})

    def test_calculate_order_is_preserved_with_forward_declarations(self) -> None:
        results = self.execute(
            "calculate square\ncalculate circle\n"
            "circle radius = 2\nsquare side = 3"
        )

        self.assertEqual(
            [result.kind for result in results],
            [TokenType.SQUARE, TokenType.CIRCLE],
        )

    def test_reports_results_outside_supported_range(self) -> None:
        with self.assertRaises(RuntimeGeoLangError) as error:
            self.execute(f"square side = {10**200}\ncalculate square")

        self.assertIn("outside the supported numeric range", str(error.exception))

    def test_formats_measurements_to_two_decimal_places(self) -> None:
        self.assertEqual(format_number(153.938), "153.94")
        self.assertEqual(format_number(30), "30.00")


if __name__ == "__main__":
    unittest.main()
