import unittest

from geolang.ast_nodes import (
    BinaryExpression,
    CalculateStatement,
    CallExpression,
    CallableDeclaration,
    GeometryDeclaration,
    NumberExpression,
    PerformStatement,
    ReturnStatement,
    UnaryExpression,
    VariableDeclaration,
)
from geolang.errors import SyntaxError
from geolang.lexer import TokenType
from geolang.parser import Parser
from geolang.semantic import SemanticAnalyzer


class ParserTests(unittest.TestCase):
    def test_parses_geometry_program_and_optional_language_header(self) -> None:
        program = Parser.from_source(
            "language GeoLang\n\n"
            "circle radius = 7\n"
            "triangle base = 10 height = 6\n"
            "calculate circle\n"
        ).parse()

        self.assertEqual(program.language, "GeoLang")
        self.assertEqual(len(program.statements), 3)
        circle = program.statements[0]
        self.assertIsInstance(circle, GeometryDeclaration)
        self.assertEqual(circle.kind, TokenType.CIRCLE)
        self.assertEqual(circle.fields[0].name, "radius")
        self.assertEqual(circle.fields[0].value, NumberExpression(7, 3, 17))
        triangle = program.statements[1]
        self.assertIsInstance(triangle, GeometryDeclaration)
        self.assertEqual([field.name for field in triangle.fields], ["base", "height"])
        calculate = program.statements[2]
        self.assertIsInstance(calculate, CalculateStatement)
        self.assertEqual(calculate.kind, TokenType.CIRCLE)

    def test_parses_arithmetic_precedence_and_parentheses(self) -> None:
        program = Parser.from_source(
            "circle radius = 2 + 3 * (4 - 1)"
        ).parse()
        declaration = program.statements[0]
        self.assertIsInstance(declaration, GeometryDeclaration)

        expression = declaration.fields[0].value
        self.assertIsInstance(expression, BinaryExpression)
        self.assertEqual(expression.operator, TokenType.PLUS)
        self.assertIsInstance(expression.right, BinaryExpression)
        self.assertEqual(expression.right.operator, TokenType.STAR)
        self.assertIsInstance(expression.right.right, BinaryExpression)
        self.assertEqual(expression.right.right.operator, TokenType.MINUS)

    def test_parses_unary_expression(self) -> None:
        program = Parser.from_source("circle radius = -7").parse()
        declaration = program.statements[0]
        self.assertIsInstance(declaration, GeometryDeclaration)
        expression = declaration.fields[0].value
        self.assertIsInstance(expression, UnaryExpression)
        self.assertEqual(expression.operator, TokenType.MINUS)
        self.assertEqual(expression.operand, NumberExpression(7, 1, 18))

    def test_accepts_program_without_language_header(self) -> None:
        program = Parser.from_source("square side = 4\ncalculate square").parse()

        self.assertIsNone(program.language)
        self.assertEqual(len(program.statements), 2)

    def test_parses_variables_named_shapes_and_named_calculations(self) -> None:
        program = Parser.from_source(
            "let radius = 7\n"
            "circle wheel radius = radius\n"
            "calculate wheel"
        ).parse()

        variable = program.statements[0]
        self.assertEqual(variable.name, "radius")
        shape = program.statements[1]
        self.assertIsInstance(shape, GeometryDeclaration)
        self.assertEqual(shape.name, "wheel")
        self.assertEqual(shape.fields[0].value.name, "radius")
        calculation = program.statements[2]
        self.assertIsInstance(calculation, CalculateStatement)
        self.assertIsNone(calculation.kind)
        self.assertEqual(calculation.name, "wheel")

    def test_parses_if_else_and_while_blocks(self) -> None:
        program = Parser.from_source(
            "let count = 0\n"
            "while count < 2\n"
            "  if count == 0\n"
            "    set count = count + 1\n"
            "  else\n"
            "    set count = count + 1\n"
            "  end\n"
            "end"
        ).parse()

        loop = program.statements[1]
        self.assertEqual(type(loop).__name__, "WhileStatement")
        conditional = loop.body[0]
        self.assertEqual(type(conditional).__name__, "IfStatement")
        self.assertEqual(len(conditional.then_branch), 1)
        self.assertEqual(len(conditional.else_branch), 1)

    def test_reports_missing_end_for_control_block(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("if 1 < 2\ncalculate circle").parse()

        self.assertIn("Expected 'end' to close the if statement", str(error.exception))

    def test_parses_rectangle_and_square_declarations(self) -> None:
        program = Parser.from_source(
            "rectangle length = 12 width = 5\n"
            "square side = 4\n"
            "calculate rectangle\n"
            "calculate square"
        ).parse()

        self.assertEqual(
            [statement.kind for statement in program.statements],
            [
                TokenType.RECTANGLE,
                TokenType.SQUARE,
                TokenType.RECTANGLE,
                TokenType.SQUARE,
            ],
        )

    def test_parses_functions_instructions_and_calls(self) -> None:
        program = Parser.from_source(
            "function double(value)\n"
            "return value * 2\n"
            "end\n"
            "circle result radius = 3\n"
            "instruction draw(radius)\n"
            "calculate result\n"
            "end\n"
            "let size = double(3)\n"
            "perform draw(size)"
        ).parse()

        function = program.statements[0]
        self.assertIsInstance(function, CallableDeclaration)
        self.assertTrue(function.returns_value)
        self.assertEqual(function.parameters, ("value",))
        self.assertIsInstance(function.body[0], ReturnStatement)
        call = function.body[0].value
        self.assertIsInstance(call, BinaryExpression)
        instruction = program.statements[2]
        self.assertIsInstance(instruction, CallableDeclaration)
        self.assertFalse(instruction.returns_value)
        declaration = program.statements[3]
        self.assertIsInstance(declaration, VariableDeclaration)
        self.assertIsInstance(declaration.value, CallExpression)
        perform = program.statements[4]
        self.assertIsInstance(perform, PerformStatement)
        self.assertEqual(perform.name, "draw")

    def test_reports_missing_field_value_at_source_location(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("circle radius =\n").parse()

        self.assertEqual((error.exception.line, error.exception.column), (1, 16))
        self.assertIn("Expected a numeric value", str(error.exception))

    def test_reports_missing_calculation_shape(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("calculate\n").parse()

        self.assertEqual((error.exception.line, error.exception.column), (1, 10))
        self.assertIn("Expected a geometry type", str(error.exception))

    def test_reports_unknown_statement(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("unknown command").parse()

        self.assertEqual((error.exception.line, error.exception.column), (1, 1))

    def test_reports_missing_dimension(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("circle\n").parse()

        self.assertIn("Expected at least one dimension", str(error.exception))

    def test_reports_missing_equals_after_dimension(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("circle radius 7").parse()

        self.assertEqual((error.exception.line, error.exception.column), (1, 15))
        self.assertIn("Expected '='", str(error.exception))

    def test_reports_unexpected_token_at_end_of_statement(self) -> None:
        with self.assertRaises(SyntaxError) as error:
            Parser.from_source("calculate circle 7").parse()

        self.assertEqual((error.exception.line, error.exception.column), (1, 18))
        self.assertIn("Expected the end of the line", str(error.exception))

    def test_parser_ast_passes_semantic_analysis(self) -> None:
        program = Parser.from_source(
            "circle radius = 2 + 3 * 4\n"
            "triangle base = 10 height = 6\n"
            "rectangle length = 12 width = 5\n"
            "square side = 4\n"
            "calculate circle\n"
            "calculate triangle\n"
            "calculate rectangle\n"
            "calculate square\n"
        ).parse()

        SemanticAnalyzer().analyze(program)


if __name__ == "__main__":
    unittest.main()
