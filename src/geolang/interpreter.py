"""Execute semantically valid GeoLang programs."""

import math
from dataclasses import dataclass

from geolang.ast_nodes import (
    CalculateStatement,
    CallableDeclaration,
    GeometryDeclaration,
    IfStatement,
    PerformStatement,
    Program,
    ReturnStatement,
    Statement,
    VariableAssignment,
    VariableDeclaration,
    WhileStatement,
)
from geolang.errors import RuntimeGeoLangError, SemanticError
from geolang.expressions import (
    ExpressionEvaluationError,
    evaluate_condition,
    evaluate_expression,
)
from geolang.lexer import TokenType
from geolang.semantic import SemanticAnalyzer

MAX_LOOP_ITERATIONS = 10_000
MAX_CALL_DEPTH = 100


class _ReturnSignal(Exception):
    def __init__(self, value: int | float) -> None:
        self.value = value


@dataclass(frozen=True, slots=True)
class GeometryResult:
    kind: TokenType
    dimensions: tuple[tuple[str, int | float], ...]
    measurements: tuple[tuple[str, int | float], ...]
    name: str | None = None


class Interpreter:
    """Run geometry calculations requested by a GeoLang program."""

    def execute(self, program: Program) -> tuple[GeometryResult, ...]:
        """Validate and execute a program, returning results in calculate order."""
        SemanticAnalyzer().analyze(program)
        self._callables = {
            statement.name: statement
            for statement in program.statements
            if isinstance(statement, CallableDeclaration)
        }
        self._call_depth = 0
        variables: dict[str, int | float] = {}
        named_shapes: dict[str, GeometryDeclaration] = {}
        anonymous_shapes: dict[TokenType, GeometryDeclaration] = {}
        for statement in program.statements:
            if isinstance(statement, GeometryDeclaration):
                if statement.name is None:
                    anonymous_shapes[statement.kind] = statement
                else:
                    named_shapes[statement.name] = statement
        self._named_shapes = named_shapes
        self._anonymous_shapes = anonymous_shapes
        self._results: list[GeometryResult] = []

        self._execute_statements(
            program.statements,
            variables,
            named_shapes,
            anonymous_shapes,
            self._results,
        )
        return tuple(self._results)

    def _execute_statements(
        self,
        statements: tuple[Statement, ...],
        variables: dict[str, int | float],
        named_shapes: dict[str, GeometryDeclaration],
        anonymous_shapes: dict[TokenType, GeometryDeclaration],
        results: list[GeometryResult],
    ) -> None:
        for statement in statements:
            if isinstance(statement, VariableDeclaration):
                variables[statement.name] = self._evaluate(
                    statement.value, variables
                )
            elif isinstance(statement, VariableAssignment):
                variables[statement.name] = self._evaluate(
                    statement.value, variables
                )
            elif isinstance(statement, GeometryDeclaration):
                continue
            elif isinstance(statement, CallableDeclaration):
                continue
            elif isinstance(statement, ReturnStatement):
                raise _ReturnSignal(self._evaluate(statement.value, variables))
            elif isinstance(statement, PerformStatement):
                arguments = tuple(
                    self._evaluate(argument, variables)
                    for argument in statement.arguments
                )
                self._invoke(
                    statement.name,
                    arguments,
                    variables,
                    statement.line,
                    statement.column,
                    expect_value=False,
                )
            elif isinstance(statement, IfStatement):
                branch = (
                    statement.then_branch
                    if self._evaluate_condition(statement.condition, variables)
                    else statement.else_branch
                )
                self._execute_statements(
                    branch,
                    variables,
                    named_shapes,
                    anonymous_shapes,
                    results,
                )
            elif isinstance(statement, WhileStatement):
                iterations = 0
                while self._evaluate_condition(statement.condition, variables):
                    if iterations >= MAX_LOOP_ITERATIONS:
                        raise RuntimeGeoLangError(
                            f"Loop exceeded the {MAX_LOOP_ITERATIONS} iteration limit.",
                            statement.line,
                            statement.column,
                        )
                    iterations += 1
                    self._execute_statements(
                        statement.body,
                        variables,
                        named_shapes,
                        anonymous_shapes,
                        results,
                    )
            elif isinstance(statement, CalculateStatement):
                if statement.name is not None:
                    declaration = named_shapes.get(statement.name)
                elif statement.kind is not None:
                    declaration = anonymous_shapes.get(statement.kind)
                else:
                    declaration = None
                if declaration is None:
                    label = (
                        f"Shape '{statement.name}'"
                        if statement.name is not None
                        else "Requested shape"
                    )
                    raise RuntimeGeoLangError(
                        f"{label} has not been declared.",
                        statement.line,
                        statement.column,
                    )
                results.append(self._calculate(declaration, statement, variables))

    def _evaluate(self, expression, variables: dict[str, int | float]) -> int | float:
        try:
            return evaluate_expression(
                expression,
                variables,
                lambda call, arguments: self._invoke(
                    call.name,
                    arguments,
                    variables,
                    call.line,
                    call.column,
                    expect_value=True,
                ),
            )
        except ExpressionEvaluationError as error:
            raise RuntimeGeoLangError(
                error.message,
                error.line,
                error.column,
            ) from error

    def _evaluate_condition(self, condition, variables: dict[str, int | float]) -> bool:
        try:
            return evaluate_condition(
                condition,
                variables,
                lambda call, arguments: self._invoke(
                    call.name,
                    arguments,
                    variables,
                    call.line,
                    call.column,
                    expect_value=True,
                ),
            )
        except ExpressionEvaluationError as error:
            raise RuntimeGeoLangError(
                error.message,
                error.line,
                error.column,
            ) from error

    def _invoke(
        self,
        name: str,
        arguments: tuple[int | float, ...],
        variables: dict[str, int | float],
        line: int,
        column: int,
        *,
        expect_value: bool,
    ) -> int | float:
        routine = self._callables.get(name)
        if routine is None:
            raise RuntimeGeoLangError(
                f"Routine '{name}' is not defined.",
                line,
                column,
            )
        if routine.returns_value != expect_value:
            use = "function" if expect_value else "instruction"
            raise RuntimeGeoLangError(
                f"'{name}' cannot be used as a {use}.",
                line,
                column,
            )
        if len(arguments) != len(routine.parameters):
            raise RuntimeGeoLangError(
                f"Routine '{name}' expects {len(routine.parameters)} argument(s), "
                f"but received {len(arguments)}.",
                line,
                column,
            )
        if self._call_depth >= MAX_CALL_DEPTH:
            raise RuntimeGeoLangError(
                f"Routine call exceeded the {MAX_CALL_DEPTH} call-depth limit.",
                line,
                column,
            )

        local_variables = variables.copy()
        local_variables.update(zip(routine.parameters, arguments, strict=True))
        self._call_depth += 1
        try:
            try:
                self._execute_statements(
                    routine.body,
                    local_variables,
                    self._named_shapes,
                    self._anonymous_shapes,
                    self._results,
                )
            except _ReturnSignal as returned:
                if not routine.returns_value:
                    raise RuntimeGeoLangError(
                        f"Instruction '{name}' cannot return a value.",
                        line,
                        column,
                    ) from None
                return returned.value
        finally:
            self._call_depth -= 1

        if routine.returns_value:
            raise RuntimeGeoLangError(
                f"Function '{name}' completed without returning a value.",
                routine.line,
                routine.column,
            )
        return 0

    def _calculate(
        self,
        declaration: GeometryDeclaration,
        statement: CalculateStatement,
        variables: dict[str, int | float],
    ) -> GeometryResult:
        dimensions: dict[str, int | float] = {}
        for field in declaration.fields:
            try:
                dimensions[field.name] = self._evaluate(field.value, variables)
            except RuntimeGeoLangError:
                raise

        try:
            SemanticAnalyzer.validate_values(
                declaration.kind,
                dimensions,
                declaration.line,
                declaration.column,
            )
        except SemanticError as error:
            raise RuntimeGeoLangError(
                error.message,
                error.line,
                error.column,
            ) from error

        try:
            if declaration.kind is TokenType.CIRCLE:
                radius = dimensions["radius"]
                measurements = (
                    ("area", math.pi * radius**2),
                    ("circumference", 2 * math.pi * radius),
                )
            elif declaration.kind is TokenType.TRIANGLE:
                if {"side_a", "side_b", "side_c"} <= dimensions.keys():
                    side_a = dimensions["side_a"]
                    side_b = dimensions["side_b"]
                    side_c = dimensions["side_c"]
                    semiperimeter = (side_a + side_b + side_c) / 2
                    measurements = (
                        (
                            "area",
                            math.sqrt(
                                semiperimeter
                                * (semiperimeter - side_a)
                                * (semiperimeter - side_b)
                                * (semiperimeter - side_c)
                            ),
                        ),
                        ("perimeter", side_a + side_b + side_c),
                    )
                else:
                    measurements = (
                        ("area", dimensions["base"] * dimensions["height"] / 2),
                    )
            elif declaration.kind is TokenType.RECTANGLE:
                length = dimensions["length"]
                width = dimensions["width"]
                measurements = (
                    ("area", length * width),
                    ("perimeter", 2 * (length + width)),
                )
            elif declaration.kind is TokenType.SQUARE:
                side = dimensions["side"]
                measurements = (
                    ("area", side**2),
                    ("perimeter", 4 * side),
                )
            else:
                raise RuntimeGeoLangError(
                    f"Unsupported shape '{declaration.kind.name.lower()}'.",
                    statement.line,
                    statement.column,
                )
        except OverflowError as error:
            raise RuntimeGeoLangError(
                "Geometry result is outside the supported numeric range.",
                statement.line,
                statement.column,
            ) from error

        for name, value in measurements:
            try:
                is_finite = math.isfinite(value)
            except OverflowError:
                is_finite = False
            if not is_finite:
                raise RuntimeGeoLangError(
                    f"Calculated {name} is outside the supported numeric range.",
                    statement.line,
                    statement.column,
                )

        return GeometryResult(
            declaration.kind,
            tuple(dimensions.items()),
            measurements,
            declaration.name,
        )


def format_number(value: int | float) -> str:
    """Format geometry measurements to two decimal places."""
    return f"{value:.2f}"
