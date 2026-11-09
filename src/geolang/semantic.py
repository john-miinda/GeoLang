"""Semantic checks for GeoLang abstract syntax trees."""

from geolang.ast_nodes import (
    BinaryExpression,
    CallExpression,
    CalculateStatement,
    CallableDeclaration,
    Condition,
    Expression,
    GeometryDeclaration,
    IfStatement,
    NumberExpression,
    PerformStatement,
    Program,
    ReturnStatement,
    Statement,
    UnaryExpression,
    VariableAssignment,
    VariableDeclaration,
    VariableExpression,
    WhileStatement,
)
from geolang.errors import SemanticError
from geolang.expressions import (
    ExpressionEvaluationError,
    evaluate_condition,
    evaluate_expression,
)
from geolang.lexer import TokenType


_REQUIRED_FIELDS: dict[TokenType, frozenset[str]] = {
    TokenType.CIRCLE: frozenset({"radius"}),
    TokenType.RECTANGLE: frozenset({"length", "width"}),
    TokenType.SQUARE: frozenset({"side"}),
}
_TRIANGLE_DIMENSIONS = frozenset({"base", "height", "side_a", "side_b", "side_c"})
_TRIANGLE_BASE_HEIGHT = frozenset({"base", "height"})
_TRIANGLE_SIDES = frozenset({"side_a", "side_b", "side_c"})


class SemanticAnalyzer:
    """Validate shape dimensions, declarations, and calculation references."""

    def __init__(self) -> None:
        self._mutable_variables: set[str] = set()
        self._callables: dict[str, CallableDeclaration] = {}

    def analyze(self, program: Program) -> None:
        """Raise a located semantic error if the program is inconsistent."""
        self._mutable_variables = set(
            self._find_mutable_variables(program.statements)
        )
        self._callables = {}
        for statement in program.statements:
            if isinstance(statement, CallableDeclaration):
                if statement.name in self._callables:
                    self._raise(
                        statement.line,
                        statement.column,
                        f"Routine '{statement.name}' is declared more than once.",
                    )
                self._callables[statement.name] = statement

        named_shapes: dict[str, GeometryDeclaration] = {}
        anonymous_shapes: dict[TokenType, GeometryDeclaration] = {}
        for statement in program.statements:
            if isinstance(statement, GeometryDeclaration):
                if statement.name is None:
                    if statement.kind in anonymous_shapes:
                        self._raise(
                            statement.line,
                            statement.column,
                            f"Only one anonymous {statement.kind.name.lower()} "
                            "declaration is allowed.",
                        )
                    anonymous_shapes[statement.kind] = statement
                else:
                    if statement.name in named_shapes:
                        self._raise(
                            statement.line,
                            statement.column,
                            f"Shape '{statement.name}' is declared more than once.",
                        )
                    named_shapes[statement.name] = statement
        top_level_variables = self._analyze_block(
            program.statements,
            {},
            named_shapes,
            anonymous_shapes,
            inside_control=False,
        )
        for routine in self._callables.values():
            variables = top_level_variables.copy()
            variables.update({name: 1 for name in routine.parameters})
            self._analyze_block(
                routine.body,
                variables,
                named_shapes,
                anonymous_shapes,
                inside_control=False,
                routine=routine,
            )
            if routine.returns_value and not self._contains_return(routine.body):
                self._raise(
                    routine.line,
                    routine.column,
                    f"Function '{routine.name}' must contain a return statement.",
                )

    def _analyze_block(
        self,
        statements: tuple[Statement, ...],
        variables: dict[str, int | float],
        named_shapes: dict[str, GeometryDeclaration],
        anonymous_shapes: dict[TokenType, GeometryDeclaration],
        inside_control: bool,
        routine: CallableDeclaration | None = None,
    ) -> dict[str, int | float]:
        for statement in statements:
            if isinstance(statement, VariableDeclaration):
                if inside_control:
                    self._raise(
                        statement.line,
                        statement.column,
                        "Variables must be declared outside conditional and loop blocks.",
                    )
                if statement.name in variables:
                    self._raise(
                        statement.line,
                        statement.column,
                        f"Variable '{statement.name}' is declared more than once.",
                    )
                if self._uses_mutable_variable(statement.value):
                    self._mutable_variables.add(statement.name)
                variables[statement.name] = self._evaluate(
                    statement.value, variables
                )
            elif isinstance(statement, VariableAssignment):
                if statement.name not in variables:
                    self._raise(
                        statement.line,
                        statement.column,
                        f"Variable '{statement.name}' is not defined.",
                    )
                variables[statement.name] = self._evaluate(
                    statement.value, variables
                )
            elif isinstance(statement, GeometryDeclaration):
                if inside_control or routine is not None:
                    self._raise(
                        statement.line,
                        statement.column,
                        "Shape declarations must be outside conditional and loop blocks.",
                    )
                self._validate_declaration(statement, variables)
            elif isinstance(statement, CalculateStatement):
                if statement.name is not None:
                    exists = statement.name in named_shapes
                    message = f"Shape '{statement.name}' has not been declared."
                else:
                    exists = statement.kind in anonymous_shapes
                    shape_name = (
                        statement.kind.name.lower()
                        if statement.kind is not None
                        else "unknown"
                    )
                    message = f"No {shape_name} has been declared."
                if not exists:
                    self._raise(statement.line, statement.column, message)
            elif isinstance(statement, IfStatement):
                self._evaluate_condition(statement.condition, variables)
                initial = variables.copy()
                then_values = self._analyze_block(
                    statement.then_branch,
                    initial.copy(),
                    named_shapes,
                    anonymous_shapes,
                    inside_control=True,
                    routine=routine,
                )
                else_values = self._analyze_block(
                    statement.else_branch,
                    initial.copy(),
                    named_shapes,
                    anonymous_shapes,
                    inside_control=True,
                    routine=routine,
                )
                variables = self._merge_variables(initial, then_values, else_values)
            elif isinstance(statement, WhileStatement):
                self._evaluate_condition(statement.condition, variables)
                initial = variables.copy()
                body_values = self._analyze_block(
                    statement.body,
                    initial.copy(),
                    named_shapes,
                    anonymous_shapes,
                    inside_control=True,
                    routine=routine,
                )
                variables = self._merge_variables(initial, body_values, initial)
            elif isinstance(statement, CallableDeclaration):
                continue
            elif isinstance(statement, ReturnStatement):
                if routine is None or not routine.returns_value:
                    self._raise(
                        statement.line,
                        statement.column,
                        "'return' is only valid inside a function.",
                    )
                self._evaluate(statement.value, variables)
            elif isinstance(statement, PerformStatement):
                self._validate_call(
                    statement.name,
                    statement.arguments,
                    wants_value=False,
                    line=statement.line,
                    column=statement.column,
                )
                for argument in statement.arguments:
                    self._evaluate(argument, variables)
        return variables

    @staticmethod
    def _merge_variables(
        initial: dict[str, int | float],
        first: dict[str, int | float],
        second: dict[str, int | float],
    ) -> dict[str, int | float]:
        merged = initial.copy()
        for name in initial:
            if first.get(name) == second.get(name):
                merged[name] = first[name]
        return merged

    def _evaluate(
        self,
        expression: Expression,
        variables: dict[str, int | float],
    ) -> int | float:
        try:
            return evaluate_expression(
                expression,
                variables,
                self._static_function_call,
            )
        except ExpressionEvaluationError as error:
            self._raise(error.line, error.column, error.message)

    def _evaluate_condition(
        self,
        condition: Condition,
        variables: dict[str, int | float],
    ) -> bool:
        try:
            return evaluate_condition(
                condition,
                variables,
                self._static_function_call,
            )
        except ExpressionEvaluationError as error:
            self._raise(error.line, error.column, error.message)

    def _validate_declaration(
        self,
        declaration: GeometryDeclaration,
        variables: dict[str, int | float],
    ) -> None:
        required_fields = _REQUIRED_FIELDS.get(declaration.kind, frozenset())
        allowed_fields = (
            _TRIANGLE_DIMENSIONS
            if declaration.kind is TokenType.TRIANGLE
            else required_fields
        )
        supplied_fields: set[str] = set()
        values: dict[str, int | float] = {}

        for field in declaration.fields:
            if field.name in supplied_fields:
                self._raise(
                    field.line,
                    field.column,
                    f"Dimension '{field.name}' is assigned more than once.",
                )
            if field.name not in allowed_fields:
                expected = ", ".join(sorted(allowed_fields))
                self._raise(
                    field.line,
                    field.column,
                    f"'{field.name}' is not a dimension of "
                    f"{declaration.kind.name.lower()}; expected: {expected}.",
                )
            supplied_fields.add(field.name)
            value = self._evaluate(field.value, variables)
            values[field.name] = value
            if not self._uses_mutable_variable(field.value):
                if value < 0:
                    self._raise(
                        field.line,
                        field.column,
                        f"Dimension '{field.name}' cannot be negative.",
                    )
                if value == 0 and declaration.kind is not TokenType.CIRCLE:
                    self._raise(
                        field.line,
                        field.column,
                        f"Dimension '{field.name}' must be greater than zero.",
                    )

        if declaration.kind is TokenType.TRIANGLE:
            self._validate_triangle_dimensions(declaration, supplied_fields)
            if not any(self._uses_mutable_variable(field.value) for field in declaration.fields):
                self.validate_values(
                    declaration.kind,
                    values,
                    declaration.line,
                    declaration.column,
                )
            return

        missing_fields = required_fields - supplied_fields
        if missing_fields:
            missing = ", ".join(sorted(missing_fields))
            self._raise(
                declaration.line,
                declaration.column,
                f"Missing required {declaration.kind.name.lower()} "
                f"dimension(s): {missing}.",
            )
        if not any(self._uses_mutable_variable(field.value) for field in declaration.fields):
            self.validate_values(
                declaration.kind,
                values,
                declaration.line,
                declaration.column,
            )

    @staticmethod
    def validate_values(
        kind: TokenType,
        values: dict[str, int | float],
        line: int,
        column: int,
    ) -> None:
        """Validate evaluated dimensions, including values changed at runtime."""
        for name, value in values.items():
            if value < 0:
                raise SemanticError(
                    f"Dimension '{name}' cannot be negative.",
                    line,
                    column,
                )
            if value == 0 and kind is not TokenType.CIRCLE:
                raise SemanticError(
                    f"Dimension '{name}' must be greater than zero.",
                    line,
                    column,
                )
        if kind is TokenType.TRIANGLE and _TRIANGLE_SIDES <= values.keys():
            side_a = values["side_a"]
            side_b = values["side_b"]
            side_c = values["side_c"]
            if (
                side_a + side_b <= side_c
                or side_a + side_c <= side_b
                or side_b + side_c <= side_a
            ):
                raise SemanticError(
                    "Triangle side lengths must satisfy the triangle inequality.",
                    line,
                    column,
                )

    def _validate_triangle_dimensions(
        self,
        declaration: GeometryDeclaration,
        supplied_fields: set[str],
    ) -> None:
        if supplied_fields == _TRIANGLE_BASE_HEIGHT:
            return
        if supplied_fields == _TRIANGLE_SIDES:
            return

        self._raise(
            declaration.line,
            declaration.column,
            "A triangle requires either 'base' and 'height', or all of "
            "'side_a', 'side_b', and 'side_c'. Do not mix the two forms.",
        )

    def _uses_mutable_variable(self, expression: Expression) -> bool:
        return self._contains_call(expression) or bool(
            self._expression_variables(expression) & self._mutable_variables
        )

    @staticmethod
    def _expression_variables(expression: Expression) -> set[str]:
        if isinstance(expression, VariableExpression):
            return {expression.name}
        if isinstance(expression, UnaryExpression):
            return SemanticAnalyzer._expression_variables(expression.operand)
        if isinstance(expression, BinaryExpression):
            return (
                SemanticAnalyzer._expression_variables(expression.left)
                | SemanticAnalyzer._expression_variables(expression.right)
            )
        if isinstance(expression, NumberExpression):
            return set()
        if isinstance(expression, CallExpression):
            variables: set[str] = set()
            for argument in expression.arguments:
                variables.update(SemanticAnalyzer._expression_variables(argument))
            return variables
        raise TypeError(f"Unsupported expression node: {type(expression).__name__}")

    @staticmethod
    def _contains_call(expression: Expression) -> bool:
        if isinstance(expression, CallExpression):
            return True
        if isinstance(expression, UnaryExpression):
            return SemanticAnalyzer._contains_call(expression.operand)
        if isinstance(expression, BinaryExpression):
            return (
                SemanticAnalyzer._contains_call(expression.left)
                or SemanticAnalyzer._contains_call(expression.right)
            )
        return False

    @classmethod
    def _contains_return(cls, statements: tuple[Statement, ...]) -> bool:
        for statement in statements:
            if isinstance(statement, ReturnStatement):
                return True
            if isinstance(statement, IfStatement) and (
                cls._contains_return(statement.then_branch)
                or cls._contains_return(statement.else_branch)
            ):
                return True
            if isinstance(statement, WhileStatement) and cls._contains_return(
                statement.body
            ):
                return True
        return False

    def _static_function_call(
        self,
        expression: CallExpression,
        _arguments: tuple[int | float, ...],
    ) -> int | float:
        self._validate_call(
            expression.name,
            expression.arguments,
            wants_value=True,
            line=expression.line,
            column=expression.column,
        )
        return 1

    def _validate_call(
        self,
        name: str,
        arguments: tuple[Expression, ...],
        *,
        wants_value: bool,
        line: int,
        column: int,
    ) -> None:
        routine = self._callables.get(name)
        if routine is None:
            self._raise(line, column, f"Routine '{name}' is not defined.")
        if routine.returns_value != wants_value:
            expected = "function call" if wants_value else "instruction"
            self._raise(
                line,
                column,
                f"'{name}' must be used as a {expected}.",
            )
        if len(arguments) != len(routine.parameters):
            self._raise(
                line,
                column,
                f"Routine '{name}' expects {len(routine.parameters)} argument(s), "
                f"but received {len(arguments)}.",
            )

    @classmethod
    def _find_mutable_variables(cls, statements: tuple) -> set[str]:
        mutable: set[str] = set()
        for statement in statements:
            if isinstance(statement, VariableAssignment):
                mutable.add(statement.name)
            elif isinstance(statement, IfStatement):
                mutable.update(cls._find_mutable_variables(statement.then_branch))
                mutable.update(cls._find_mutable_variables(statement.else_branch))
            elif isinstance(statement, WhileStatement):
                mutable.update(cls._find_mutable_variables(statement.body))
        return mutable

    @staticmethod
    def _raise(line: int, column: int, message: str) -> None:
        raise SemanticError(message, line, column)
