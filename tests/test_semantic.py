import unittest

from geolang.errors import SemanticError
from geolang.parser import Parser
from geolang.semantic import SemanticAnalyzer


class SemanticAnalyzerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.analyzer = SemanticAnalyzer()

    def analyze(self, source: str) -> None:
        self.analyzer.analyze(Parser.from_source(source).parse())

    def test_accepts_all_shapes_and_arithmetic_dimensions(self) -> None:
        self.analyze(
            "circle radius = (2 + 3) * 2\n"
            "triangle base = 10 height = 6\n"
            "rectangle length = 12 width = 5\n"
            "square side = 4\n"
            "calculate circle\n"
            "calculate triangle\n"
            "calculate rectangle\n"
            "calculate square"
        )

    def test_accepts_triangle_with_three_side_dimensions(self) -> None:
        self.analyze("triangle side_a = 3 side_b = 4 side_c = 5\ncalculate triangle")

    def test_rejects_negative_circle_radius(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("circle radius = 2 - 5")

        self.assertIn("cannot be negative", str(error.exception))
        self.assertEqual((error.exception.line, error.exception.column), (1, 8))

    def test_accepts_zero_circle_radius(self) -> None:
        self.analyze("circle radius = 0")

    def test_rejects_non_positive_non_circle_dimensions(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("square side = 0")

        self.assertIn("must be greater than zero", str(error.exception))

    def test_rejects_missing_dimensions(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("triangle base = 10")

        self.assertIn("requires either 'base' and 'height'", str(error.exception))

    def test_rejects_invalid_triangle_side_lengths(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("triangle side_a = 1 side_b = 2 side_c = 3")

        self.assertIn("triangle inequality", str(error.exception))

    def test_rejects_unsupported_dimensions(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("circle radius = 4 diameter = 8")

        self.assertIn("'diameter' is not a dimension of circle", str(error.exception))

    def test_rejects_duplicate_dimensions(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("circle radius = 4 radius = 8")

        self.assertIn("assigned more than once", str(error.exception))

    def test_rejects_duplicate_shape_declarations(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("square side = 4\nsquare side = 5")

        self.assertIn("Only one anonymous square", str(error.exception))

    def test_accepts_multiple_named_shapes_of_same_type(self) -> None:
        self.analyze(
            "circle wheel radius = 2\n"
            "circle coin radius = 3\n"
            "calculate wheel\n"
            "calculate coin"
        )

    def test_rejects_duplicate_named_shape(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze(
                "square first side = 4\n"
                "circle first radius = 2"
            )

        self.assertIn("Shape 'first' is declared more than once", str(error.exception))

    def test_accepts_variable_references_and_sequential_expressions(self) -> None:
        self.analyze(
            "let radius = 3\n"
            "let large_radius = radius * 2\n"
            "circle wheel radius = large_radius\n"
            "calculate wheel"
        )

    def test_accepts_functions_and_instructions(self) -> None:
        self.analyze(
            "function double(value)\n"
            "return value * 2\n"
            "end\n"
            "circle wheel radius = 3\n"
            "instruction draw()\n"
            "calculate wheel\n"
            "end\n"
            "let radius = double(3)\n"
            "perform draw()"
        )

    def test_rejects_call_to_undefined_routine(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("let radius = missing(2)")

        self.assertIn("Routine 'missing' is not defined", str(error.exception))

    def test_rejects_wrong_routine_argument_count(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze(
                "function double(value)\n"
                "return value * 2\n"
                "end\n"
                "let radius = double()"
            )

        self.assertIn("expects 1 argument(s), but received 0", str(error.exception))

    def test_rejects_return_outside_a_function(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("return 2")

        self.assertIn("only valid inside a function", str(error.exception))

    def test_rejects_undefined_variable(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("circle wheel radius = missing")

        self.assertIn("Variable 'missing' is not defined", str(error.exception))

    def test_rejects_duplicate_variable(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("let radius = 3\nlet radius = 4")

        self.assertIn("Variable 'radius' is declared more than once", str(error.exception))

    def test_rejects_named_calculation_without_shape(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("calculate missing")

        self.assertIn("Shape 'missing' has not been declared", str(error.exception))

    def test_rejects_undeclared_variable_in_condition(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("if missing < 2\nend")

        self.assertIn("Variable 'missing' is not defined", str(error.exception))

    def test_rejects_variable_declaration_inside_control_block(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("if 1 < 2\nlet inner = 3\nend")

        self.assertIn("Variables must be declared outside", str(error.exception))

    def test_rejects_assignment_to_undeclared_variable(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("set count = 1")

        self.assertIn("Variable 'count' is not defined", str(error.exception))

    def test_rejects_calculation_without_declaration(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("calculate rectangle")

        self.assertIn("No rectangle has been declared", str(error.exception))

    def test_allows_calculation_before_declaration(self) -> None:
        self.analyze("calculate square\nsquare side = 4")

    def test_rejects_division_by_zero_in_dimension_expression(self) -> None:
        with self.assertRaises(SemanticError) as error:
            self.analyze("circle radius = 10 / (3 - 3)")

        self.assertIn("Division by zero", str(error.exception))

    def test_rejects_non_finite_dimension_expression(self) -> None:
        with self.assertRaises(SemanticError) as overflow_error:
            self.analyze(
                "circle radius = "
                + ("9" * 309)
                + ".0 * "
                + ("9" * 309)
                + ".0"
            )

        self.assertIn("finite number", str(overflow_error.exception))


if __name__ == "__main__":
    unittest.main()
