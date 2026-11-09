"""Recursive-descent parser for GeoLang source tokens."""

from collections.abc import Sequence
from typing import NoReturn

from geolang.ast_nodes import (
    BinaryExpression,
    CallExpression,
    CallableDeclaration,
    CalculateStatement,
    Condition,
    Expression,
    FieldAssignment,
    GeometryDeclaration,
    IfStatement,
    NumberExpression,
    Program,
    PerformStatement,
    ReturnStatement,
    Statement,
    UnaryExpression,
    VariableDeclaration,
    VariableAssignment,
    VariableExpression,
    WhileStatement,
)
from geolang.errors import SyntaxError
from geolang.lexer import Lexer, Token, TokenType


_GEOMETRY_TYPES = {
    TokenType.CIRCLE,
    TokenType.TRIANGLE,
    TokenType.RECTANGLE,
    TokenType.SQUARE,
}


class Parser:
    """Parse a sequence of lexer tokens into a GeoLang abstract syntax tree."""

    def __init__(self, tokens: Sequence[Token]) -> None:
        if not tokens or tokens[-1].type is not TokenType.EOF:
            raise ValueError("Parser requires a token sequence ending with EOF.")
        self.tokens = tokens
        self.current = 0

    @classmethod
    def from_source(cls, source: str) -> Parser:
        """Lex source text and create a parser for its tokens."""
        return cls(Lexer(source).tokenize())

    def parse(self) -> Program:
        """Parse one complete program."""
        first_token = self._peek()
        self._skip_newlines()

        language: str | None = None
        if self._match(TokenType.LANGUAGE):
            language = self._consume(
                TokenType.IDENTIFIER,
                "Expected a language name after 'language'.",
            ).lexeme
            self._consume_line_end()

        statements: list[Statement] = []
        self._skip_newlines()
        while not self._check(TokenType.EOF):
            statements.append(self._statement())
            self._consume_line_end()
            self._skip_newlines()

        return Program(language, tuple(statements), first_token.line, first_token.column)

    def _statement(self) -> Statement:
        if self._peek().type in _GEOMETRY_TYPES:
            return self._geometry_declaration()
        if self._match(TokenType.LET):
            keyword = self._previous()
            name = self._consume(
                TokenType.IDENTIFIER,
                "Expected a variable name after 'let'.",
            )
            self._consume(
                TokenType.EQUALS,
                f"Expected '=' after variable '{name.lexeme}'.",
            )
            return VariableDeclaration(
                name.lexeme,
                self._expression(),
                keyword.line,
                keyword.column,
            )
        if self._match(TokenType.SET):
            keyword = self._previous()
            name = self._consume(
                TokenType.IDENTIFIER,
                "Expected a variable name after 'set'.",
            )
            self._consume(
                TokenType.EQUALS,
                f"Expected '=' after variable '{name.lexeme}'.",
            )
            return VariableAssignment(
                name.lexeme,
                self._expression(),
                keyword.line,
                keyword.column,
            )
        if self._match(TokenType.IF):
            return self._if_statement(self._previous())
        if self._match(TokenType.WHILE):
            return self._while_statement(self._previous())
        if self._match(TokenType.FUNCTION):
            return self._callable_declaration(self._previous(), returns_value=True)
        if self._match(TokenType.INSTRUCTION):
            return self._callable_declaration(self._previous(), returns_value=False)
        if self._match(TokenType.RETURN):
            keyword = self._previous()
            return ReturnStatement(
                self._expression(),
                keyword.line,
                keyword.column,
            )
        if self._match(TokenType.PERFORM):
            keyword = self._previous()
            name = self._consume(
                TokenType.IDENTIFIER,
                "Expected an instruction name after 'perform'.",
            )
            arguments = self._arguments()
            return PerformStatement(
                name.lexeme,
                arguments,
                keyword.line,
                keyword.column,
            )
        if self._match(TokenType.CALCULATE):
            calculate_token = self._previous()
            if self._peek().type in _GEOMETRY_TYPES:
                kind = self._advance().type
                return CalculateStatement(
                    kind, calculate_token.line, calculate_token.column
                )
            name = self._consume(
                TokenType.IDENTIFIER,
                "Expected a geometry type or shape name after 'calculate'.",
            )
            return CalculateStatement(
                None,
                calculate_token.line,
                calculate_token.column,
                name.lexeme,
            )
        token = self._peek()
        self._raise_error(
            token,
            "Expected a geometry declaration or 'calculate' instruction.",
        )

    def _callable_declaration(
        self,
        keyword: Token,
        returns_value: bool,
    ) -> CallableDeclaration:
        name = self._consume(TokenType.IDENTIFIER, "Expected a routine name.")
        parameters = self._parameters()
        self._consume_line_end()
        self._skip_newlines()
        body = self._block({TokenType.END})
        self._consume(TokenType.END, "Expected 'end' to close the routine.")
        return CallableDeclaration(
            name.lexeme,
            parameters,
            body,
            returns_value,
            keyword.line,
            keyword.column,
        )

    def _parameters(self) -> tuple[str, ...]:
        self._consume(TokenType.LEFT_PAREN, "Expected '(' before routine parameters.")
        parameters: list[str] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                parameter = self._consume(
                    TokenType.IDENTIFIER,
                    "Expected a parameter name.",
                )
                if parameter.lexeme in parameters:
                    self._raise_error(
                        parameter,
                        f"Parameter '{parameter.lexeme}' is repeated.",
                    )
                parameters.append(parameter.lexeme)
                if not self._match(TokenType.COMMA):
                    break
        self._consume(TokenType.RIGHT_PAREN, "Expected ')' after routine parameters.")
        return tuple(parameters)

    def _arguments(self) -> tuple[Expression, ...]:
        self._consume(TokenType.LEFT_PAREN, "Expected '(' before arguments.")
        arguments: list[Expression] = []
        if not self._check(TokenType.RIGHT_PAREN):
            while True:
                arguments.append(self._expression())
                if not self._match(TokenType.COMMA):
                    break
        self._consume(TokenType.RIGHT_PAREN, "Expected ')' after arguments.")
        return tuple(arguments)

    def _if_statement(self, keyword: Token) -> IfStatement:
        condition = self._condition()
        self._consume_line_end()
        self._skip_newlines()
        then_branch = self._block({TokenType.ELSE, TokenType.END})
        else_branch: tuple[Statement, ...] = ()
        if self._match(TokenType.ELSE):
            self._consume_line_end()
            self._skip_newlines()
            else_branch = self._block({TokenType.END})
        self._consume(TokenType.END, "Expected 'end' to close the if statement.")
        return IfStatement(
            condition, then_branch, else_branch, keyword.line, keyword.column
        )

    def _while_statement(self, keyword: Token) -> WhileStatement:
        condition = self._condition()
        self._consume_line_end()
        self._skip_newlines()
        body = self._block({TokenType.END})
        self._consume(TokenType.END, "Expected 'end' to close the while loop.")
        return WhileStatement(condition, body, keyword.line, keyword.column)

    def _condition(self) -> Condition:
        left = self._expression()
        if not self._match(
            TokenType.EQUAL_EQUAL,
            TokenType.BANG_EQUAL,
            TokenType.LESS,
            TokenType.LESS_EQUAL,
            TokenType.GREATER,
            TokenType.GREATER_EQUAL,
        ):
            self._raise_error(self._peek(), "Expected a comparison operator in condition.")
        operator = self._previous()
        right = self._expression()
        return Condition(left, operator.type, right, operator.line, operator.column)

    def _block(self, terminators: set[TokenType]) -> tuple[Statement, ...]:
        statements: list[Statement] = []
        while self._peek().type not in terminators | {TokenType.EOF}:
            statements.append(self._statement())
            self._consume_line_end()
            self._skip_newlines()
        return tuple(statements)

    def _geometry_declaration(self) -> GeometryDeclaration:
        geometry_token = self._advance()
        shape_name: str | None = None
        if (
            self._check(TokenType.IDENTIFIER)
            and self._peek_next().type is TokenType.IDENTIFIER
        ):
            shape_name = self._advance().lexeme
        fields: list[FieldAssignment] = []

        while not self._at_line_end():
            name = self._consume(
                TokenType.IDENTIFIER,
                "Expected a dimension name in the geometry declaration.",
            )
            self._consume(
                TokenType.EQUALS,
                f"Expected '=' after dimension '{name.lexeme}'.",
            )
            value = self._expression()
            fields.append(
                FieldAssignment(name.lexeme, value, name.line, name.column)
            )

        if not fields:
            self._raise_error(
                self._peek(),
                f"Expected at least one dimension after '{geometry_token.lexeme}'.",
            )

        return GeometryDeclaration(
            geometry_token.type,
            tuple(fields),
            geometry_token.line,
            geometry_token.column,
            shape_name,
        )

    def _expression(self) -> Expression:
        return self._addition()

    def _addition(self) -> Expression:
        expression = self._multiplication()
        while self._match(TokenType.PLUS, TokenType.MINUS):
            operator = self._previous()
            right = self._multiplication()
            expression = BinaryExpression(
                expression, operator.type, right, operator.line, operator.column
            )
        return expression

    def _multiplication(self) -> Expression:
        expression = self._unary()
        while self._match(TokenType.STAR, TokenType.SLASH):
            operator = self._previous()
            right = self._unary()
            expression = BinaryExpression(
                expression, operator.type, right, operator.line, operator.column
            )
        return expression

    def _unary(self) -> Expression:
        if self._match(TokenType.MINUS, TokenType.PLUS):
            operator = self._previous()
            return UnaryExpression(
                operator.type,
                self._unary(),
                operator.line,
                operator.column,
            )
        return self._primary()

    def _primary(self) -> Expression:
        if self._match(TokenType.NUMBER):
            token = self._previous()
            value = token.literal
            if value is None:
                self._raise_error(token, "Number token is missing its numeric value.")
            return NumberExpression(value, token.line, token.column)

        if self._match(TokenType.IDENTIFIER):
            token = self._previous()
            if self._check(TokenType.LEFT_PAREN):
                return CallExpression(
                    token.lexeme,
                    self._arguments(),
                    token.line,
                    token.column,
                )
            return VariableExpression(token.lexeme, token.line, token.column)

        if self._match(TokenType.LEFT_PAREN):
            expression = self._expression()
            self._consume(TokenType.RIGHT_PAREN, "Expected ')' after the expression.")
            return expression

        self._raise_error(self._peek(), "Expected a numeric value or '(' to start an expression.")

    def _consume_line_end(self) -> None:
        if self._match(TokenType.NEWLINE):
            return
        if not self._check(TokenType.EOF):
            self._raise_error(self._peek(), "Expected the end of the line.")

    def _consume(self, token_type: TokenType, message: str) -> Token:
        if self._check(token_type):
            return self._advance()
        self._raise_error(self._peek(), message)

    def _match(self, *token_types: TokenType) -> bool:
        if self._peek().type in token_types:
            self._advance()
            return True
        return False

    def _check(self, token_type: TokenType) -> bool:
        return self._peek().type is token_type

    def _advance(self) -> Token:
        token = self._peek()
        if token.type is not TokenType.EOF:
            self.current += 1
        return token

    def _peek(self) -> Token:
        return self.tokens[self.current]

    def _peek_next(self) -> Token:
        return self.tokens[min(self.current + 1, len(self.tokens) - 1)]

    def _previous(self) -> Token:
        return self.tokens[self.current - 1]

    def _at_line_end(self) -> bool:
        return self._peek().type in {TokenType.NEWLINE, TokenType.EOF}

    def _skip_newlines(self) -> None:
        while self._match(TokenType.NEWLINE):
            pass

    @staticmethod
    def _raise_error(token: Token, message: str) -> NoReturn:
        raise SyntaxError(message, token.line, token.column)
