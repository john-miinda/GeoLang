"""Abstract syntax tree nodes produced by the GeoLang parser."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TypeAlias

from geolang.lexer import TokenType


@dataclass(frozen=True, slots=True)
class NumberExpression:
    value: int | float
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class VariableExpression:
    name: str
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class CallExpression:
    name: str
    arguments: tuple[Expression, ...]
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class UnaryExpression:
    operator: TokenType
    operand: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class BinaryExpression:
    left: Expression
    operator: TokenType
    right: Expression
    line: int
    column: int


Expression: TypeAlias = (
    NumberExpression
    | VariableExpression
    | CallExpression
    | UnaryExpression
    | BinaryExpression
)


@dataclass(frozen=True, slots=True)
class FieldAssignment:
    name: str
    value: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class GeometryDeclaration:
    kind: TokenType
    fields: tuple[FieldAssignment, ...]
    line: int
    column: int
    name: str | None = None


@dataclass(frozen=True, slots=True)
class VariableDeclaration:
    name: str
    value: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class VariableAssignment:
    name: str
    value: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class Condition:
    left: Expression
    operator: TokenType
    right: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class IfStatement:
    condition: Condition
    then_branch: tuple[Statement, ...]
    else_branch: tuple[Statement, ...]
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class WhileStatement:
    condition: Condition
    body: tuple[Statement, ...]
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class CallableDeclaration:
    name: str
    parameters: tuple[str, ...]
    body: tuple[Statement, ...]
    returns_value: bool
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class ReturnStatement:
    value: Expression
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class PerformStatement:
    name: str
    arguments: tuple[Expression, ...]
    line: int
    column: int


@dataclass(frozen=True, slots=True)
class CalculateStatement:
    kind: TokenType | None
    line: int
    column: int
    name: str | None = None


Statement: TypeAlias = (
    GeometryDeclaration
    | VariableDeclaration
    | VariableAssignment
    | CalculateStatement
    | IfStatement
    | WhileStatement
    | CallableDeclaration
    | ReturnStatement
    | PerformStatement
)


@dataclass(frozen=True, slots=True)
class Program:
    language: str | None
    statements: tuple[Statement, ...]
    line: int
    column: int
