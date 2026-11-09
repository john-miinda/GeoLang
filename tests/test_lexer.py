import unittest

from geolang.errors import LexicalError
from geolang.lexer import Lexer, TokenType


class LexerTests(unittest.TestCase):
    def test_scans_geometry_program_and_tracks_positions(self) -> None:
        tokens = Lexer("language GeoLang\ncircle radius = 7").tokenize()

        self.assertEqual(
            [token.type for token in tokens],
            [
                TokenType.LANGUAGE,
                TokenType.IDENTIFIER,
                TokenType.NEWLINE,
                TokenType.CIRCLE,
                TokenType.IDENTIFIER,
                TokenType.EQUALS,
                TokenType.NUMBER,
                TokenType.EOF,
            ],
        )
        self.assertEqual(tokens[6].literal, 7)
        self.assertEqual((tokens[6].line, tokens[6].column), (2, 17))
        self.assertEqual((tokens[-1].line, tokens[-1].column), (2, 18))

    def test_scans_decimal_numbers_and_arithmetic_punctuation(self) -> None:
        tokens = Lexer("(12.5 + 3) / 2, -1").tokenize()

        self.assertEqual(
            [token.type for token in tokens],
            [
                TokenType.LEFT_PAREN,
                TokenType.NUMBER,
                TokenType.PLUS,
                TokenType.NUMBER,
                TokenType.RIGHT_PAREN,
                TokenType.SLASH,
                TokenType.NUMBER,
                TokenType.COMMA,
                TokenType.MINUS,
                TokenType.NUMBER,
                TokenType.EOF,
            ],
        )
        self.assertEqual(tokens[1].literal, 12.5)

    def test_scans_control_flow_keywords_and_comparison_operators(self) -> None:
        tokens = Lexer("if count <= 3\nset count = count + 1\nend").tokenize()

        self.assertEqual(
            [token.type for token in tokens],
            [
                TokenType.IF,
                TokenType.IDENTIFIER,
                TokenType.LESS_EQUAL,
                TokenType.NUMBER,
                TokenType.NEWLINE,
                TokenType.SET,
                TokenType.IDENTIFIER,
                TokenType.EQUALS,
                TokenType.IDENTIFIER,
                TokenType.PLUS,
                TokenType.NUMBER,
                TokenType.NEWLINE,
                TokenType.END,
                TokenType.EOF,
            ],
        )

    def test_keywords_are_case_insensitive_and_fields_are_identifiers(self) -> None:
        tokens = Lexer("Circle base_2 = 10").tokenize()

        self.assertEqual(
            [token.type for token in tokens],
            [
                TokenType.CIRCLE,
                TokenType.IDENTIFIER,
                TokenType.EQUALS,
                TokenType.NUMBER,
                TokenType.EOF,
            ],
        )
        self.assertEqual(tokens[1].lexeme, "base_2")

    def test_empty_source_returns_eof(self) -> None:
        tokens = Lexer("").tokenize()

        self.assertEqual(len(tokens), 1)
        self.assertEqual(tokens[0].type, TokenType.EOF)
        self.assertEqual((tokens[0].line, tokens[0].column), (1, 1))

    def test_invalid_character_has_source_location(self) -> None:
        with self.assertRaises(LexicalError) as error:
            Lexer("circle radius = 7\n@").tokenize()

        self.assertEqual((error.exception.line, error.exception.column), (2, 1))
        self.assertIn("Unexpected character '@'", str(error.exception))


if __name__ == "__main__":
    unittest.main()
