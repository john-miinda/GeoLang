"""Convert GeoLang source text into a sequence of tokens."""

from dataclasses import dataclass
from enum import Enum, auto

from geolang.errors import LexicalError


class TokenType(Enum):
    LANGUAGE = auto()
    CIRCLE = auto()
    TRIANGLE = auto()
    RECTANGLE = auto()
    SQUARE = auto()
    CALCULATE = auto()
    LET = auto()
    SET = auto()
    IF = auto()
    ELSE = auto()
    WHILE = auto()
    END = auto()
    FUNCTION = auto()
    INSTRUCTION = auto()
    RETURN = auto()
    PERFORM = auto()
    IDENTIFIER = auto()
    NUMBER = auto()
    EQUALS = auto()
    PLUS = auto()
    MINUS = auto()
    STAR = auto()
    SLASH = auto()
    LEFT_PAREN = auto()
    RIGHT_PAREN = auto()
    COMMA = auto()
    EQUAL_EQUAL = auto()
    BANG_EQUAL = auto()
    LESS = auto()
    LESS_EQUAL = auto()
    GREATER = auto()
    GREATER_EQUAL = auto()
    NEWLINE = auto()
    EOF = auto()


@dataclass(frozen=True)
class Token:
    type: TokenType
    lexeme: str
    line: int
    column: int
    literal: int | float | None = None


_KEYWORDS = {
    "language": TokenType.LANGUAGE,
    "circle": TokenType.CIRCLE,
    "triangle": TokenType.TRIANGLE,
    "rectangle": TokenType.RECTANGLE,
    "square": TokenType.SQUARE,
    "calculate": TokenType.CALCULATE,
    "let": TokenType.LET,
    "set": TokenType.SET,
    "if": TokenType.IF,
    "else": TokenType.ELSE,
    "while": TokenType.WHILE,
    "end": TokenType.END,
    "function": TokenType.FUNCTION,
    "instruction": TokenType.INSTRUCTION,
    "return": TokenType.RETURN,
    "perform": TokenType.PERFORM,
}


class Lexer:
    """Scan source text and return tokens with 1-based source positions."""

    def __init__(self, source: str) -> None:
        self.source = source.replace("\r\n", "\n").replace("\r", "\n")
        self.start = 0
        self.current = 0
        self.line = 1
        self.column = 1
        self.start_line = 1
        self.start_column = 1
        self.tokens: list[Token] = []

    def tokenize(self) -> list[Token]:
        """Return all tokens, including a final EOF token."""
        while not self._is_at_end():
            self.start = self.current
            self.start_line = self.line
            self.start_column = self.column
            character = self._advance()

            if character in " \t\f":
                continue
            if character == "\n":
                self._add_token(TokenType.NEWLINE)
            elif character.isascii() and (character.isalpha() or character == "_"):
                self._identifier()
            elif character.isascii() and character.isdigit():
                self._number()
            else:
                token_type = {
                    "=": TokenType.EQUALS,
                    "+": TokenType.PLUS,
                    "-": TokenType.MINUS,
                    "*": TokenType.STAR,
                    "/": TokenType.SLASH,
                    "(": TokenType.LEFT_PAREN,
                    ")": TokenType.RIGHT_PAREN,
                    ",": TokenType.COMMA,
                }.get(character)
                if character in {"=", "!", "<", ">"}:
                    token_type = self._comparison_operator(character)
                if token_type is None:
                    raise LexicalError(
                        f"Unexpected character {character!r}.",
                        self.start_line,
                        self.start_column,
                    )
                self._add_token(token_type)

        self.tokens.append(Token(TokenType.EOF, "", self.line, self.column))
        return self.tokens

    def _comparison_operator(self, character: str) -> TokenType:
        if self._peek() == "=":
            self._advance()
            return {
                "=": TokenType.EQUAL_EQUAL,
                "!": TokenType.BANG_EQUAL,
                "<": TokenType.LESS_EQUAL,
                ">": TokenType.GREATER_EQUAL,
            }[character]
        if character == "=":
            return TokenType.EQUALS
        if character == "<":
            return TokenType.LESS
        if character == ">":
            return TokenType.GREATER
        raise LexicalError(
            "Expected '=' after '!'.",
            self.start_line,
            self.start_column,
        )

    def _identifier(self) -> None:
        while not self._is_at_end():
            character = self._peek()
            if not (character.isascii() and (character.isalnum() or character == "_")):
                break
            self._advance()

        lexeme = self.source[self.start:self.current]
        token_type = _KEYWORDS.get(lexeme.lower(), TokenType.IDENTIFIER)
        self._add_token(token_type)

    def _number(self) -> None:
        while not self._is_at_end() and self._peek().isascii() and self._peek().isdigit():
            self._advance()

        is_decimal = False
        if (
            not self._is_at_end()
            and self._peek() == "."
            and self._peek_next().isascii()
            and self._peek_next().isdigit()
        ):
            is_decimal = True
            self._advance()
            while not self._is_at_end() and self._peek().isascii() and self._peek().isdigit():
                self._advance()

        lexeme = self.source[self.start:self.current]
        literal: int | float = float(lexeme) if is_decimal else int(lexeme)
        self._add_token(TokenType.NUMBER, literal)

    def _add_token(self, token_type: TokenType, literal: int | float | None = None) -> None:
        lexeme = self.source[self.start:self.current]
        self.tokens.append(
            Token(token_type, lexeme, self.start_line, self.start_column, literal)
        )

    def _advance(self) -> str:
        character = self.source[self.current]
        self.current += 1
        if character == "\n":
            self.line += 1
            self.column = 1
        else:
            self.column += 1
        return character

    def _peek(self) -> str:
        return "\0" if self._is_at_end() else self.source[self.current]

    def _peek_next(self) -> str:
        next_index = self.current + 1
        return "\0" if next_index >= len(self.source) else self.source[next_index]

    def _is_at_end(self) -> bool:
        return self.current >= len(self.source)
