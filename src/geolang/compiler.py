"""Compile GeoLang ASTs into executable Python source."""

from geolang.ast_nodes import (
    BinaryExpression,
    CalculateStatement,
    CallableDeclaration,
    CallExpression,
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
from geolang.lexer import TokenType
from geolang.semantic import SemanticAnalyzer


_PYTHON_OPERATORS = {
    TokenType.PLUS: "+",
    TokenType.MINUS: "-",
    TokenType.STAR: "*",
    TokenType.SLASH: "/",
}
_COMPARISON_OPERATORS = {
    TokenType.EQUAL_EQUAL: "==",
    TokenType.BANG_EQUAL: "!=",
    TokenType.LESS: "<",
    TokenType.LESS_EQUAL: "<=",
    TokenType.GREATER: ">",
    TokenType.GREATER_EQUAL: ">=",
}


class PythonCompiler:
    """Translate a validated GeoLang program into Python statements."""

    def __init__(self) -> None:
        self._loop_id = 0

    def compile(self, program: Program) -> str:
        """Return executable Python source generated directly from the AST."""
        SemanticAnalyzer().analyze(program)
        self._loop_id = 0
        lines = _PYTHON_RUNTIME.splitlines()

        for statement in program.statements:
            if isinstance(statement, GeometryDeclaration):
                lines.append(self._geometry_declaration(statement))

        for statement in program.statements:
            if isinstance(statement, CallableDeclaration):
                lines.extend(self._callable_declaration(statement))

        executable = tuple(
            statement
            for statement in program.statements
            if not isinstance(statement, (GeometryDeclaration, CallableDeclaration))
        )
        lines.extend(self._statements(executable, 0))
        lines.extend(_PYTHON_OUTPUT.splitlines())
        return "\n".join(lines) + "\n"

    def _geometry_declaration(self, declaration: GeometryDeclaration) -> str:
        if declaration.name is None:
            key = repr(("kind", declaration.kind.name.lower()))
        else:
            key = repr(("name", declaration.name))
        fields = ", ".join(
            f"{field.name!r}: {self._expression(field.value)}"
            for field in declaration.fields
        )
        return (
            f"_shapes[{key}] = "
            f"({declaration.kind.name.lower()!r}, {declaration.name!r}, "
            f"lambda: {{{fields}}})"
        )

    def _callable_declaration(
        self,
        declaration: CallableDeclaration,
    ) -> list[str]:
        name = self._routine_name(declaration.name)
        parameters = ", ".join(self._variable_name(item) for item in declaration.parameters)
        lines = [
            f"def {name}({parameters}):",
            "    global _call_depth",
            "    _call_depth += 1",
            "    try:",
            "        if _call_depth > 100:",
            "            raise RuntimeError('GeoLang routine call-depth limit exceeded')",
        ]
        assigned = self._assigned_names(declaration.body)
        for variable in sorted(assigned - set(declaration.parameters)):
            variable_name = self._variable_name(variable)
            lines.append(
                f"        {variable_name} = globals().get({variable_name!r})"
            )
        body = self._statements(declaration.body, 2)
        lines.extend(body or ["        pass"])
        if declaration.returns_value:
            lines.append(
                f"        raise RuntimeError("
                f"'GeoLang function {declaration.name!r} completed without returning')"
            )
        lines.extend(
            [
                "    finally:",
                "        _call_depth -= 1",
            ]
        )
        return lines

    def _statements(self, statements: tuple[Statement, ...], indent: int) -> list[str]:
        lines: list[str] = []
        prefix = "    " * indent
        for statement in statements:
            if isinstance(statement, (GeometryDeclaration, CallableDeclaration)):
                continue
            if isinstance(statement, VariableDeclaration):
                line = f"{self._variable_name(statement.name)} = {self._expression(statement.value)}"
                lines.append(prefix + line)
            elif isinstance(statement, VariableAssignment):
                lines.append(
                    prefix
                    + f"{self._variable_name(statement.name)} = "
                    + self._expression(statement.value)
                )
            elif isinstance(statement, CalculateStatement):
                key = (
                    ("name", statement.name)
                    if statement.name is not None
                    else ("kind", statement.kind.name.lower())
                )
                lines.append(
                    prefix
                    + f"_calculate({key!r}, {statement.line}, {statement.column})"
                )
            elif isinstance(statement, PerformStatement):
                arguments = ", ".join(
                    self._expression(argument) for argument in statement.arguments
                )
                lines.append(
                    prefix
                    + f"{self._routine_name(statement.name)}({arguments})"
                )
            elif isinstance(statement, ReturnStatement):
                lines.append(prefix + f"return {self._expression(statement.value)}")
            elif isinstance(statement, IfStatement):
                lines.append(
                    prefix
                    + f"if {self._condition(statement.condition)}:"
                )
                lines.extend(
                    self._statements(statement.then_branch, indent + 1)
                    or [prefix + "    pass"]
                )
                if statement.else_branch:
                    lines.append(prefix + "else:")
                    lines.extend(
                        self._statements(statement.else_branch, indent + 1)
                        or [prefix + "    pass"]
                    )
            elif isinstance(statement, WhileStatement):
                loop_id = self._loop_id
                self._loop_id += 1
                counter = f"_loop_iterations_{loop_id}"
                lines.extend(
                    [
                        prefix + f"{counter} = 0",
                        prefix + f"while {self._condition(statement.condition)}:",
                        prefix + f"    if {counter} >= 10_000:",
                        prefix
                        + "        raise RuntimeError('GeoLang loop iteration limit exceeded')",
                        prefix + f"    {counter} += 1",
                    ]
                )
                lines.extend(
                    self._statements(statement.body, indent + 1)
                    or [prefix + "    pass"]
                )
        return lines

    def _expression(self, expression: Expression) -> str:
        if isinstance(expression, NumberExpression):
            return repr(expression.value)
        if isinstance(expression, VariableExpression):
            return self._variable_name(expression.name)
        if isinstance(expression, CallExpression):
            arguments = ", ".join(
                self._expression(argument) for argument in expression.arguments
            )
            return f"{self._routine_name(expression.name)}({arguments})"
        if isinstance(expression, UnaryExpression):
            operator = "-" if expression.operator is TokenType.MINUS else "+"
            return f"({operator}{self._expression(expression.operand)})"
        if isinstance(expression, BinaryExpression):
            operator = _PYTHON_OPERATORS[expression.operator]
            return (
                f"({self._expression(expression.left)} {operator} "
                f"{self._expression(expression.right)})"
            )
        raise TypeError(f"Unsupported expression node: {type(expression).__name__}")

    def _condition(self, condition: Condition) -> str:
        operator = _COMPARISON_OPERATORS[condition.operator]
        return (
            f"({self._expression(condition.left)} {operator} "
            f"{self._expression(condition.right)})"
        )

    @staticmethod
    def _variable_name(name: str) -> str:
        return f"_v_{name}"

    @staticmethod
    def _routine_name(name: str) -> str:
        return f"_fn_{name}"

    @classmethod
    def _assigned_names(cls, statements: tuple[Statement, ...]) -> set[str]:
        names: set[str] = set()
        for statement in statements:
            if isinstance(statement, (VariableDeclaration, VariableAssignment)):
                names.add(statement.name)
            elif isinstance(statement, IfStatement):
                names.update(cls._assigned_names(statement.then_branch))
                names.update(cls._assigned_names(statement.else_branch))
            elif isinstance(statement, WhileStatement):
                names.update(cls._assigned_names(statement.body))
        return names


_PYTHON_RUNTIME = '''\
import math as _math

_shapes = {}
_results = []
_call_depth = 0


def _calculate(key, line, column):
    if key not in _shapes:
        raise RuntimeError(f"GeoLang shape {key[1]!r} is not defined at {line}:{column}")
    kind, name, dimensions_factory = _shapes[key]
    dimensions = dimensions_factory()
    for field, value in dimensions.items():
        try:
            finite = _math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise RuntimeError(f"GeoLang dimension {field!r} is outside the numeric range")
        if value < 0 or (value == 0 and kind != "circle"):
            raise RuntimeError(f"GeoLang dimension {field!r} must be positive")

    if kind == "circle":
        radius = dimensions["radius"]
        measurements = {"area": _math.pi * radius ** 2,
                        "circumference": 2 * _math.pi * radius}
    elif kind == "rectangle":
        length, width = dimensions["length"], dimensions["width"]
        measurements = {"area": length * width,
                        "perimeter": 2 * (length + width)}
    elif kind == "square":
        side = dimensions["side"]
        measurements = {"area": side ** 2, "perimeter": 4 * side}
    else:
        if "side_a" in dimensions:
            side_a, side_b, side_c = (dimensions["side_a"], dimensions["side_b"],
                                      dimensions["side_c"])
            if (side_a + side_b <= side_c or side_a + side_c <= side_b
                    or side_b + side_c <= side_a):
                raise RuntimeError("GeoLang triangle inequality is not satisfied")
            semiperimeter = (side_a + side_b + side_c) / 2
            area = _math.sqrt(semiperimeter * (semiperimeter - side_a)
                              * (semiperimeter - side_b) * (semiperimeter - side_c))
            measurements = {"area": area, "perimeter": side_a + side_b + side_c}
        else:
            measurements = {"area": dimensions["base"] * dimensions["height"] / 2}

    for value in measurements.values():
        try:
            finite = _math.isfinite(value)
        except OverflowError:
            finite = False
        if not finite:
            raise RuntimeError("GeoLang geometry result is outside the numeric range")
    _results.append((kind, name, dimensions, measurements))


def _format_number(value):
    return f"{value:.2f}"
'''


_PYTHON_OUTPUT = '''\
print("GeoLang compiled program")
for _kind, _name, _dimensions, _measurements in _results:
    _label = _kind.title() + (f" ({_name})" if _name is not None else "")
    print(f"\\n{_label}:")
    for _field, _value in _dimensions.items():
        print(f"{_field.replace('_', ' ').title()} = {_format_number(_value)}")
    for _field, _value in _measurements.items():
        print(f"{_field.title()} = {_format_number(_value)}")
print("\\nExecution completed successfully.")
'''
