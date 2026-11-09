"""Evaluate arithmetic expressions shared by analysis and execution."""

import math
from collections.abc import Mapping
from collections.abc import Callable

from geolang.ast_nodes import (
    BinaryExpression,
    CallExpression,
    Condition,
    Expression,
    NumberExpression,
    UnaryExpression,
    VariableExpression,
)
from geolang.lexer import TokenType


class ExpressionEvaluationError(Exception):
    """An arithmetic failure with the source position of its expression."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.column = column


def evaluate_expression(
    expression: Expression,
    variables: Mapping[str, int | float] | None = None,
    function_call: Callable[
        [CallExpression, tuple[int | float, ...]], int | float
    ] | None = None,
) -> int | float:
    """Evaluate an AST expression, rejecting division by zero and non-finite values."""
    if isinstance(expression, NumberExpression):
        value = expression.value
    elif isinstance(expression, VariableExpression):
        if variables is None or expression.name not in variables:
            raise ExpressionEvaluationError(
                f"Variable '{expression.name}' is not defined.",
                expression.line,
                expression.column,
            )
        value = variables[expression.name]
    elif isinstance(expression, CallExpression):
        if function_call is None:
            raise ExpressionEvaluationError(
                f"Function '{expression.name}' cannot be called here.",
                expression.line,
                expression.column,
            )
        arguments = tuple(
            evaluate_expression(argument, variables, function_call)
            for argument in expression.arguments
        )
        value = function_call(expression, arguments)
    elif isinstance(expression, UnaryExpression):
        operand = evaluate_expression(expression.operand, variables, function_call)
        value = -operand if expression.operator is TokenType.MINUS else operand
    elif isinstance(expression, BinaryExpression):
        left = evaluate_expression(expression.left, variables, function_call)
        right = evaluate_expression(expression.right, variables, function_call)
        try:
            if expression.operator is TokenType.PLUS:
                value = left + right
            elif expression.operator is TokenType.MINUS:
                value = left - right
            elif expression.operator is TokenType.STAR:
                value = left * right
            else:
                value = left / right
        except ZeroDivisionError as error:
            raise ExpressionEvaluationError(
                "Division by zero in dimension expression.",
                expression.line,
                expression.column,
            ) from error
        except OverflowError as error:
            raise ExpressionEvaluationError(
                "Dimension expression is outside the supported numeric range.",
                expression.line,
                expression.column,
            ) from error
    else:
        raise TypeError(f"Unsupported expression node: {type(expression).__name__}")

    if isinstance(value, float) and not math.isfinite(value):
        raise ExpressionEvaluationError(
            "Dimension expression must produce a finite number.",
            expression.line,
            expression.column,
        )
    return value


def evaluate_condition(
    condition: Condition,
    variables: Mapping[str, int | float] | None = None,
    function_call: Callable[
        [CallExpression, tuple[int | float, ...]], int | float
    ] | None = None,
) -> bool:
    """Evaluate a numeric comparison condition."""
    left = evaluate_expression(condition.left, variables, function_call)
    right = evaluate_expression(condition.right, variables, function_call)
    if condition.operator is TokenType.EQUAL_EQUAL:
        return left == right
    if condition.operator is TokenType.BANG_EQUAL:
        return left != right
    if condition.operator is TokenType.LESS:
        return left < right
    if condition.operator is TokenType.LESS_EQUAL:
        return left <= right
    if condition.operator is TokenType.GREATER:
        return left > right
    if condition.operator is TokenType.GREATER_EQUAL:
        return left >= right
    raise TypeError(f"Unsupported comparison operator: {condition.operator.name}")
