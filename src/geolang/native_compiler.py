"""Compile GeoLang programs into Windows x64 executables through MSVC."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
from functools import lru_cache
from pathlib import Path

from geolang.ast_nodes import (
    BinaryExpression,
    BooleanExpression,
    CalculateStatement,
    CallableDeclaration,
    CallExpression,
    Expression,
    GeometryDeclaration,
    IfStatement,
    ImportStatement,
    NumberExpression,
    PerformStatement,
    PrintStatement,
    Program,
    ReturnStatement,
    Statement,
    StringExpression,
    UnaryExpression,
    VariableAssignment,
    VariableDeclaration,
    VariableExpression,
    WhileStatement,
)
from geolang.errors import CompilerError
from geolang.lexer import TokenType
from geolang.semantic import SemanticAnalyzer


_COMPARISON_OPERATORS = {
    TokenType.EQUAL_EQUAL: "==",
    TokenType.BANG_EQUAL: "!=",
    TokenType.LESS: "<",
    TokenType.LESS_EQUAL: "<=",
    TokenType.GREATER: ">",
    TokenType.GREATER_EQUAL: ">=",
}


class NativeCompiler:
    """Generate and compile a native Windows x64 executable with MSVC."""

    def __init__(self) -> None:
        self._loop_id = 0
        self._routines: dict[str, int] = {}
        self._shapes: dict[tuple[str, str], int] = {}

    def generate(self, program: Program) -> str:
        """Generate self-contained C++17 source from a validated program."""
        SemanticAnalyzer().analyze(program)
        declarations = [
            item
            for item in program.statements
            if isinstance(item, GeometryDeclaration)
        ]
        routines = [
            item
            for item in program.statements
            if isinstance(item, CallableDeclaration)
        ]
        self._routines = {item.name: index for index, item in enumerate(routines)}
        self._shapes = {}
        for index, declaration in enumerate(declarations):
            key = (
                ("name", declaration.name)
                if declaration.name is not None
                else ("kind", declaration.kind.name.lower())
            )
            self._shapes[key] = index
        self._loop_id = 0

        lines = [_CPP_RUNTIME]
        for index, _routine in enumerate(routines):
            lines.append(
                f"static Value _routine_{index}(Env&, const std::vector<Value>&);"
            )
        lines.extend(
            self._shape_function(index, item)
            for index, item in enumerate(declarations)
        )
        lines.extend(
            self._routine_function(index, routine)
            for index, routine in enumerate(routines)
        )

        executable = tuple(
            item
            for item in program.statements
            if not isinstance(item, (GeometryDeclaration, CallableDeclaration))
        )
        lines.append("int main() {")
        lines.append("    try {")
        lines.append("        Env _env;")
        lines.extend(self._statements(executable, "_env", 2))
        lines.append("        _print_results();")
        lines.append("        std::cout << \"\\nExecution completed successfully.\\n\";")
        lines.append("        return 0;")
        lines.append("    } catch (const std::exception& error) {")
        lines.append("        std::cerr << \"GeoLang Runtime Error: \" << error.what() << '\\n';")
        lines.append("        return 1;")
        lines.append("    }")
        lines.append("}")
        return "\n\n".join(lines) + "\n"

    def compile(self, program: Program, output_path: str | Path) -> Path:
        """Generate source and compile it to the requested native executable."""
        source = self.generate(program)
        output = Path(output_path).resolve()
        if output.suffix.lower() != ".exe":
            raise CompilerError("The native output path must end in '.exe'.", 1, 1)
        if not output.parent.is_dir():
            raise CompilerError(
                f"Output directory does not exist: '{output.parent}'.",
                1,
                1,
            )
        developer_command = self._find_msvc_environment()
        compiler_environment = self._load_msvc_environment(developer_command)
        compiler = self._find_compiler(developer_command, compiler_environment)
        if compiler is None:
            raise CompilerError(
                "MSVC was found, but cl.exe is unavailable in its x64 environment. "
                "Install the Visual Studio C++ x64 build tools.",
                1,
                1,
            )
        with tempfile.TemporaryDirectory(prefix="geolang-native-") as directory:
            source_path = Path(directory) / "program.cpp"
            object_path = Path(directory) / "program.obj"
            source_path.write_text(source, encoding="ascii", newline="\n")
            try:
                result = subprocess.run(
                    [
                        compiler,
                        "/nologo",
                        "/std:c++17",
                        "/EHsc",
                        "/O2",
                        f"/Fe:{output}",
                        f"/Fo:{object_path}",
                        str(source_path),
                    ],
                    env=compiler_environment,
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as error:
                raise CompilerError(
                    "MSVC timed out while compiling the native program.",
                    1,
                    1,
                ) from error
            except OSError as error:
                raise CompilerError(
                    f"Could not run MSVC: {error}",
                    1,
                    1,
                ) from error
            if result.returncode != 0:
                details = (result.stdout + result.stderr).strip()
                raise CompilerError(
                    "MSVC failed to compile the native program."
                    + (f"\n{details}" if details else ""),
                    1,
                    1,
                )
        if not output.is_file():
            raise CompilerError(
                f"MSVC reported success but did not create '{output}'.",
                1,
                1,
            )
        return output

    @staticmethod
    def _find_compiler(
        developer_command: Path,
        environment: dict[str, str],
    ) -> str | None:
        path_key = next(
            (key for key in environment if key.casefold() == "path"),
            "PATH",
        )
        compiler = shutil.which("cl.exe", path=environment.get(path_key))
        if compiler is None:
            compiler = NativeCompiler._find_installed_cl(developer_command)
            if compiler is not None:
                compiler_directory = str(Path(compiler).parent)
                environment[path_key] = os.pathsep.join(
                    [
                        compiler_directory,
                        environment.get(path_key, ""),
                    ]
                )
        return compiler

    @staticmethod
    def _find_msvc_environment() -> Path:
        program_files = os.environ.get(
            "ProgramFiles(x86)",
            r"C:\Program Files (x86)",
        )
        vswhere = (
            Path(program_files)
            / "Microsoft Visual Studio"
            / "Installer"
            / "vswhere.exe"
        )
        if not vswhere.is_file():
            raise CompilerError(
                "Native Windows compilation requires Visual Studio Build Tools "
                "with the C++ x64 tools installed.",
                1,
                1,
            )
        result = subprocess.run(
            [
                str(vswhere),
                "-latest",
                "-products",
                "*",
                "-requires",
                "Microsoft.VisualStudio.Component.VC.Tools.x86.x64",
                "-property",
                "installationPath",
            ],
            capture_output=True,
            text=True,
            errors="replace",
            check=False,
            timeout=10,
        )
        installation = result.stdout.strip()
        if result.returncode != 0 or not installation:
            raise CompilerError(
                "Native Windows compilation requires Visual Studio Build Tools "
                "with the C++ x64 tools installed.",
                1,
                1,
            )
        developer_command = (
            Path(installation) / "Common7" / "Tools" / "VsDevCmd.bat"
        )
        if not developer_command.is_file():
            raise CompilerError(
                f"Visual Studio developer environment was not found at '{developer_command}'.",
                1,
                1,
            )
        return developer_command

    @staticmethod
    @lru_cache(maxsize=2)
    def _load_msvc_environment(developer_command: Path) -> dict[str, str]:
        with tempfile.TemporaryDirectory(prefix="geolang-msvc-env-") as directory:
            batch_path = Path(directory) / "environment.bat"
            batch_path.write_text(
                "\r\n".join(
                    [
                        "@echo off",
                        f'call "{developer_command}" -no_logo -arch=x64',
                        "if errorlevel 1 exit /b %errorlevel%",
                        "set",
                        "",
                    ]
                ),
                encoding="ascii",
            )
            try:
                result = subprocess.run(
                    [
                        os.environ.get("COMSPEC", "cmd.exe"),
                        "/d",
                        "/c",
                        str(batch_path),
                    ],
                    capture_output=True,
                    text=True,
                    errors="replace",
                    check=False,
                    timeout=120,
                )
            except subprocess.TimeoutExpired as error:
                raise CompilerError(
                    "Timed out while initializing the MSVC x64 build environment.",
                    1,
                    1,
                ) from error
            except OSError as error:
                raise CompilerError(
                    f"Could not initialize the MSVC x64 build environment: {error}",
                    1,
                    1,
                ) from error
        if result.returncode != 0:
            details = (result.stdout + result.stderr).strip()
            raise CompilerError(
                "Could not initialize the MSVC x64 build environment."
                + (f"\n{details}" if details else ""),
                1,
                1,
            )
        environment = os.environ.copy()
        environment_keys = {
            key.casefold(): key
            for key in environment
        }
        for line in result.stdout.splitlines():
            if "=" in line and not line.startswith("="):
                name, value = line.split("=", 1)
                existing_name = environment_keys.get(name.casefold())
                if existing_name is None:
                    environment[name] = value
                    environment_keys[name.casefold()] = name
                else:
                    environment[existing_name] = value
        return environment

    @staticmethod
    def _find_installed_cl(developer_command: Path) -> str | None:
        installation = developer_command.parents[2]
        compiler_versions = (
            installation / "VC" / "Tools" / "MSVC"
        )
        if not compiler_versions.is_dir():
            return None
        for version in sorted(compiler_versions.iterdir(), reverse=True):
            compiler = (
                version
                / "bin"
                / "Hostx64"
                / "x64"
                / "cl.exe"
            )
            if compiler.is_file():
                return str(compiler)
        return None

    def _shape_function(
        self,
        index: int,
        declaration: GeometryDeclaration,
    ) -> str:
        lines = [f"static void _calculate_shape_{index}(Env& _env) {{"]
        lines.append("    std::vector<std::pair<std::string, double>> _dimensions;")
        circle_literal = "true" if declaration.kind is TokenType.CIRCLE else "false"
        for field in declaration.fields:
            lines.append(
                f"    const double _{field.name} = _number("
                f"{self._expression(field.value, '_env')}, "
                f"{field.line}, {field.column});"
            )
            lines.append(
                f"    _check_dimension(_{field.name}, {self._string(field.name)}, "
                f"{circle_literal}, "
                f"{field.line}, {field.column});"
            )
            lines.append(
                f"    _dimensions.emplace_back({self._string(field.name)}, "
                f"_{field.name});"
            )

        kind = declaration.kind
        if kind is TokenType.CIRCLE:
            formulas = [
                ("area", "3.14159265358979323846 * _radius * _radius"),
                ("circumference", "2.0 * 3.14159265358979323846 * _radius"),
            ]
        elif kind is TokenType.RECTANGLE:
            formulas = [
                ("area", "_length * _width"),
                ("perimeter", "2.0 * (_length + _width)"),
            ]
        elif kind is TokenType.SQUARE:
            formulas = [
                ("area", "_side * _side"),
                ("perimeter", "4.0 * _side"),
            ]
        elif any(field.name == "side_a" for field in declaration.fields):
            lines.extend(
                [
                    "    if (_side_a + _side_b <= _side_c || "
                    "_side_a + _side_c <= _side_b || "
                    "_side_b + _side_c <= _side_a) "
                    '_fail("Triangle side lengths must satisfy the triangle inequality.");',
                    "    const double _semi = (_side_a + _side_b + _side_c) / 2.0;",
                ]
            )
            formulas = [
                (
                    "area",
                    "std::sqrt(_semi * (_semi - _side_a) "
                    "* (_semi - _side_b) * (_semi - _side_c))",
                ),
                ("perimeter", "_side_a + _side_b + _side_c"),
            ]
        else:
            formulas = [
                ("area", "_base * _height / 2.0"),
            ]

        lines.append("    std::vector<std::pair<std::string, double>> _measurements;")
        for name, formula in formulas:
            lines.append(
                f"    const double _measurement_{name} = {formula};"
            )
            lines.append(f"    _check_result(_measurement_{name});")
            lines.append(
                f"    _measurements.emplace_back({self._string(name)}, "
                f"_measurement_{name});"
            )
        shape_name = declaration.name or ""
        lines.append(
            f"    _results.push_back(Result{{{self._string(kind.name.lower())}, "
            f"{self._string(shape_name)}, std::move(_dimensions), "
            "std::move(_measurements)});"
        )
        lines.append("}")
        return "\n".join(lines)

    def _routine_function(
        self,
        index: int,
        declaration: CallableDeclaration,
    ) -> str:
        lines = [
            f"static Value _routine_{index}(Env& _caller, "
            "const std::vector<Value>& _arguments) {",
            "    _CallGuard _call_guard;",
            "    Env _env = _caller;",
        ]
        for parameter_index, parameter in enumerate(declaration.parameters):
            lines.append(
                f"    _set(_env, {self._string(parameter)}, "
                f"_arguments.at({parameter_index}));"
            )
        lines.extend(
            self._statements(declaration.body, "_env", 1, in_function=True)
        )
        if declaration.returns_value:
            lines.append(
                f"    _fail({self._string('Function ' + repr(declaration.name) + ' completed without returning a value.')});"
            )
        else:
            lines.append("    return Value{0.0};")
        lines.append("}")
        return "\n".join(lines)

    def _statements(
        self,
        statements: tuple[Statement, ...],
        environment: str,
        indent: int,
        *,
        in_function: bool = False,
    ) -> list[str]:
        output: list[str] = []
        prefix = "    " * indent
        for statement in statements:
            if isinstance(statement, (ImportStatement, GeometryDeclaration, CallableDeclaration)):
                continue
            if isinstance(statement, VariableDeclaration):
                output.append(
                    prefix
                    + f"_set({environment}, {self._string(statement.name)}, "
                    + f"{self._expression(statement.value, environment)});"
                )
            elif isinstance(statement, VariableAssignment):
                output.append(
                    prefix
                    + f"_set({environment}, {self._string(statement.name)}, "
                    + f"{self._expression(statement.value, environment)});"
                )
            elif isinstance(statement, PrintStatement):
                output.append(
                    prefix
                    + f"_print_value({self._expression(statement.value, environment)});"
                )
            elif isinstance(statement, CalculateStatement):
                key = (
                    ("name", statement.name)
                    if statement.name is not None
                    else ("kind", statement.kind.name.lower())
                )
                output.append(
                    prefix
                    + f"_calculate_shape_{self._shapes[key]}({environment});"
                )
            elif isinstance(statement, PerformStatement):
                output.append(
                    prefix
                    + self._call(statement.name, statement.arguments, environment)
                    + ";"
                )
            elif isinstance(statement, ReturnStatement):
                if not in_function:
                    raise CompilerError(
                        "'return' is only valid inside a function.",
                        statement.line,
                        statement.column,
                    )
                output.append(
                    prefix
                    + f"return {self._expression(statement.value, environment)};"
                )
            elif isinstance(statement, IfStatement):
                output.append(
                    prefix
                    + f"if (_condition({self._expression(statement.condition.left, environment)}, "
                    + f"{self._expression(statement.condition.right, environment)}, "
                    + f"{self._string(_COMPARISON_OPERATORS[statement.condition.operator])}, "
                    + f"{statement.line}, {statement.column})) {{"
                )
                output.extend(
                    self._statements(
                        statement.then_branch,
                        environment,
                        indent + 1,
                        in_function=in_function,
                    )
                )
                if statement.else_branch:
                    output.append(prefix + "} else {")
                    output.extend(
                        self._statements(
                            statement.else_branch,
                            environment,
                            indent + 1,
                            in_function=in_function,
                        )
                    )
                output.append(prefix + "}")
            elif isinstance(statement, WhileStatement):
                loop_id = self._loop_id
                self._loop_id += 1
                output.append(prefix + "{")
                output.append(prefix + f"    std::size_t _iterations_{loop_id} = 0;")
                output.append(
                    prefix
                    + f"    while (_condition("
                    + f"{self._expression(statement.condition.left, environment)}, "
                    + f"{self._expression(statement.condition.right, environment)}, "
                    + f"{self._string(_COMPARISON_OPERATORS[statement.condition.operator])}, "
                    + f"{statement.line}, {statement.column})) {{"
                )
                output.append(
                    prefix
                    + f"        if (_iterations_{loop_id}++ >= 10000) "
                    + '_fail("Loop exceeded the 10000 iteration limit.");'
                )
                output.extend(
                    self._statements(
                        statement.body,
                        environment,
                        indent + 2,
                        in_function=in_function,
                    )
                )
                output.append(prefix + "    }")
                output.append(prefix + "}")
        return output

    def _expression(self, expression: Expression, environment: str) -> str:
        if isinstance(expression, NumberExpression):
            return f"_literal_number({self._string(repr(expression.value))})"
        if isinstance(expression, StringExpression):
            return f"Value{{{self._string(expression.value)}}}"
        if isinstance(expression, BooleanExpression):
            return f"Value{{{'true' if expression.value else 'false'}}}"
        if isinstance(expression, VariableExpression):
            return f"_get({environment}, {self._string(expression.name)})"
        if isinstance(expression, CallExpression):
            if expression.name == "input_number":
                argument = self._expression(expression.arguments[0], environment)
                return (
                    f"_input_number({argument}, "
                    f"{expression.line}, {expression.column})"
                )
            return self._call(expression.name, expression.arguments, environment)
        if isinstance(expression, UnaryExpression):
            operator = "-" if expression.operator is TokenType.MINUS else "+"
            return (
                f"_unary({self._string(operator)}, "
                f"{self._expression(expression.operand, environment)}, "
                f"{expression.line}, {expression.column})"
            )
        if isinstance(expression, BinaryExpression):
            operator = {
                TokenType.PLUS: "+",
                TokenType.MINUS: "-",
                TokenType.STAR: "*",
                TokenType.SLASH: "/",
            }[expression.operator]
            return (
                f"_binary({self._string(operator)}, "
                f"{self._expression(expression.left, environment)}, "
                f"{self._expression(expression.right, environment)}, "
                f"{expression.line}, {expression.column})"
            )
        raise TypeError(f"Unsupported expression node: {type(expression).__name__}")

    def _call(
        self,
        name: str,
        arguments: tuple[Expression, ...],
        environment: str,
    ) -> str:
        call_args = ", ".join(
            self._expression(argument, environment) for argument in arguments
        )
        return (
            f"_routine_{self._routines[name]}({environment}, "
            f"std::vector<Value>{{{call_args}}})"
        )

    @staticmethod
    def _string(value: str) -> str:
        encoded = value.encode("utf-8")
        escaped = "".join(f"\\x{byte:02x}" for byte in encoded)
        return f"std::string(\"{escaped}\", {len(encoded)})"


_CPP_RUNTIME = r'''#include <charconv>
#include <cerrno>
#include <cmath>
#include <cstddef>
#include <cstdint>
#include <cstdlib>
#include <iomanip>
#include <iostream>
#include <limits>
#include <stdexcept>
#include <string>
#include <system_error>
#include <unordered_map>
#include <utility>
#include <variant>
#include <vector>

using Value = std::variant<double, std::string, bool, std::int64_t>;
using Env = std::unordered_map<std::string, Value>;

struct Result {
    std::string kind;
    std::string name;
    std::vector<std::pair<std::string, double>> dimensions;
    std::vector<std::pair<std::string, double>> measurements;
};

static std::vector<Result> _results;
static std::size_t _call_depth = 0;

[[noreturn]] static void _fail(const std::string& message) {
    throw std::runtime_error(message);
}

struct _CallGuard {
    _CallGuard() {
        if (_call_depth >= 100) _fail("Routine call exceeded the 100 call-depth limit.");
        ++_call_depth;
    }
    ~_CallGuard() { --_call_depth; }
};

static double _finite(double value, int line, int column) {
    if (!std::isfinite(value))
        _fail("Numeric result is outside the supported range at " +
              std::to_string(line) + ":" + std::to_string(column));
    return value;
}

static Value _literal_number(const std::string& text) {
    if (text.find_first_of(".eE") == std::string::npos) {
        errno = 0;
        char* integer_end = nullptr;
        const long long integer = std::strtoll(text.c_str(), &integer_end, 10);
        if (integer_end != text.c_str() && *integer_end == '\0' && errno != ERANGE)
            return static_cast<std::int64_t>(integer);
        if (errno == ERANGE) _fail("Integer literal is outside the native 64-bit range.");
    }
    char* end = nullptr;
    const double value = std::strtod(text.c_str(), &end);
    if (end == text.c_str() || *end != '\0' || !std::isfinite(value))
        _fail("Numeric literal is outside the supported range.");
    return value;
}

static double _number(const Value& value, int line, int column) {
    const auto* number = std::get_if<double>(&value);
    if (number) return *number;
    if (const auto* integer = std::get_if<std::int64_t>(&value))
        return static_cast<double>(*integer);
    _fail("Expected a numeric value at " + std::to_string(line) + ":" +
          std::to_string(column));
}

static Value _get(const Env& env, const std::string& name) {
    const auto found = env.find(name);
    if (found == env.end()) _fail("Variable '" + name + "' is not defined.");
    return found->second;
}

static void _set(Env& env, const std::string& name, Value value) {
    env[name] = std::move(value);
}

static Value _unary(const std::string& op, const Value& value, int line, int column) {
    if (const auto* integer = std::get_if<std::int64_t>(&value)) {
        if (op == "+") return *integer;
        if (*integer == std::numeric_limits<std::int64_t>::min())
            _fail("Integer result is outside the native 64-bit range at " +
                  std::to_string(line) + ":" + std::to_string(column));
        return -*integer;
    }
    const double number = _number(value, line, column);
    return _finite(op == "-" ? -number : number, line, column);
}

static std::int64_t _integer_binary(const std::string& op, std::int64_t a,
                                    std::int64_t b, int line, int column) {
    const auto minimum = std::numeric_limits<std::int64_t>::min();
    const auto maximum = std::numeric_limits<std::int64_t>::max();
    bool overflow = false;
    if (op == "+")
        overflow = (b > 0 && a > maximum - b) || (b < 0 && a < minimum - b);
    else if (op == "-")
        overflow = (b < 0 && a > maximum + b) || (b > 0 && a < minimum + b);
    else if (a != 0 && b != 0) {
        if ((a == -1 && b == minimum) || (b == -1 && a == minimum))
            overflow = true;
        else if (a > 0)
            overflow = b > 0 ? a > maximum / b : b < minimum / a;
        else
            overflow = b > 0 ? a < minimum / b : a < maximum / b;
    }
    if (overflow)
        _fail("Integer result is outside the native 64-bit range at " +
              std::to_string(line) + ":" + std::to_string(column));
    if (op == "+") return a + b;
    if (op == "-") return a - b;
    return a * b;
}

static Value _binary(const std::string& op, const Value& left, const Value& right,
                     int line, int column) {
    const auto* left_integer = std::get_if<std::int64_t>(&left);
    const auto* right_integer = std::get_if<std::int64_t>(&right);
    if (op != "/" && left_integer && right_integer)
        return _integer_binary(op, *left_integer, *right_integer, line, column);
    const double a = _number(left, line, column);
    const double b = _number(right, line, column);
    if (op == "/" && b == 0.0) _fail("Division by zero at " +
                                      std::to_string(line) + ":" + std::to_string(column));
    if (op == "+") return _finite(a + b, line, column);
    if (op == "-") return _finite(a - b, line, column);
    if (op == "*") return _finite(a * b, line, column);
    return _finite(a / b, line, column);
}

static bool _condition(const Value& left, const Value& right, const std::string& op,
                       int line, int column) {
    const auto* left_integer = std::get_if<std::int64_t>(&left);
    const auto* right_integer = std::get_if<std::int64_t>(&right);
    if (left_integer && right_integer) {
        if (op == "==") return *left_integer == *right_integer;
        if (op == "!=") return *left_integer != *right_integer;
        if (op == "<") return *left_integer < *right_integer;
        if (op == "<=") return *left_integer <= *right_integer;
        if (op == ">") return *left_integer > *right_integer;
        return *left_integer >= *right_integer;
    }
    const auto* left_number = std::get_if<double>(&left);
    const auto* right_number = std::get_if<double>(&right);
    const auto* left_boolean = std::get_if<bool>(&left);
    const auto* right_boolean = std::get_if<bool>(&right);
    const auto* left_int = std::get_if<std::int64_t>(&left);
    const auto* right_int = std::get_if<std::int64_t>(&right);
    if ((left_number || left_boolean || left_int) &&
        (right_number || right_boolean || right_int)) {
        const double a = left_number ? *left_number :
                         left_int ? static_cast<double>(*left_int) :
                         (*left_boolean ? 1.0 : 0.0);
        const double b = right_number ? *right_number :
                         right_int ? static_cast<double>(*right_int) :
                         (*right_boolean ? 1.0 : 0.0);
        if (op == "==") return a == b;
        if (op == "!=") return a != b;
        if (op == "<") return a < b;
        if (op == "<=") return a <= b;
        if (op == ">") return a > b;
        return a >= b;
    }
    const auto* left_string = std::get_if<std::string>(&left);
    const auto* right_string = std::get_if<std::string>(&right);
    if (left_string && right_string) {
        if (op == "==") return *left_string == *right_string;
        if (op == "!=") return *left_string != *right_string;
        if (op == "<") return *left_string < *right_string;
        if (op == "<=") return *left_string <= *right_string;
        if (op == ">") return *left_string > *right_string;
        return *left_string >= *right_string;
    }
    if (op == "==") return false;
    if (op == "!=") return true;
    _fail("Comparison requires compatible values at " + std::to_string(line) +
          ":" + std::to_string(column));
}

static std::string _number_text(double value) {
    char buffer[64];
    const auto converted = std::to_chars(buffer, buffer + sizeof(buffer), value);
    if (converted.ec != std::errc{})
        _fail("Could not format numeric output.");
    std::string result(buffer, converted.ptr);
    if (result.find_first_of(".eE") == std::string::npos) result += ".0";
    return result;
}

static void _print_value(const Value& value) {
    if (const auto* string = std::get_if<std::string>(&value)) std::cout << *string << '\n';
    else if (const auto* boolean = std::get_if<bool>(&value))
        std::cout << (*boolean ? "true" : "false") << '\n';
    else if (const auto* integer = std::get_if<std::int64_t>(&value))
        std::cout << *integer << '\n';
    else std::cout << _number_text(std::get<double>(value)) << '\n';
}

static Value _input_number(const Value& prompt, int line, int column) {
    const auto* text = std::get_if<std::string>(&prompt);
    if (!text)
        _fail("input_number prompt must be text at " + std::to_string(line) +
              ":" + std::to_string(column));
    std::cout << *text << std::flush;
    std::string input;
    if (!std::getline(std::cin, input))
        _fail("No numeric input was provided at " + std::to_string(line) +
              ":" + std::to_string(column));
    const std::size_t first = input.find_first_not_of(" \t\r\n");
    const std::size_t last = input.find_last_not_of(" \t\r\n");
    if (first == std::string::npos)
        _fail("Input must be a number at " + std::to_string(line) +
              ":" + std::to_string(column));
    return _literal_number(input.substr(first, last - first + 1));
}

static void _check_dimension(double value, const std::string& name, bool circle,
                             int line, int column) {
    if (!std::isfinite(value))
        _fail("Dimension '" + name + "' is outside the numeric range at " +
              std::to_string(line) + ":" + std::to_string(column));
    if (value < 0.0 || (value == 0.0 && !circle))
        _fail("Dimension '" + name + "' must be positive at " +
              std::to_string(line) + ":" + std::to_string(column));
}

static void _check_result(double value) {
    if (!std::isfinite(value))
        _fail("Geometry result is outside the supported numeric range.");
}

static std::string _title(const std::string& value) {
    std::string result = value;
    bool capitalize = true;
    for (char& character : result) {
        if (character == '_') {
            character = ' ';
            capitalize = true;
        } else if (capitalize) {
            if (character >= 'a' && character <= 'z') character -= ('a' - 'A');
            capitalize = false;
        }
    }
    return result;
}

static void _print_results() {
    std::cout << "GeoLang native program\n";
    for (const Result& result : _results) {
        std::cout << '\n' << _title(result.kind);
        if (!result.name.empty()) std::cout << " (" << result.name << ')';
        std::cout << ":\n";
        for (const auto& item : result.dimensions)
            std::cout << _title(item.first) << " = " << std::fixed
                      << std::setprecision(2) << item.second << '\n';
        for (const auto& item : result.measurements)
            std::cout << _title(item.first) << " = " << std::fixed
                      << std::setprecision(2) << item.second << '\n';
    }
}
'''
