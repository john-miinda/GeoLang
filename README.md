# GeoLang
<<<<<<< HEAD

GeoLang is an experimental, geometry-oriented programming language. It is being
built incrementally to make each language-processing stage understandable and
testable.

# GeoLang

GeoLang is a geometry-oriented programming language implemented in Python.
Its interpreter includes a hand-written lexer, recursive-descent parser,
abstract syntax tree, semantic analyzer, and runtime for geometric calculations.
The first release also supports arithmetic, numeric variables, named shapes,
conditionals, and bounded while loops.

```geolang
language GeoLang

let radius = 7
circle wheel radius = radius

calculate wheel
```

## Requirements

- Python 3.14 or newer
- Windows PowerShell, Command Prompt, or another Python-capable terminal

GeoLang has no runtime third-party dependencies.

## Install and run

From the project directory in PowerShell, create and activate a virtual
environment, then install GeoLang in editable mode:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e .
geolang examples\first.geolang
```

If the Python launcher is unavailable, create the environment with
`python -m venv .venv` using a Python 3.14+ interpreter. If PowerShell blocks
activation, invoke the environment directly:

```powershell
.\.venv\Scripts\python.exe -m pip install -e .
.\.venv\Scripts\geolang.exe examples\first.geolang
```

`python -m geolang examples\first.geolang` also runs the language without
calling the installed console command. Use `geolang --help` for options, or
`geolang --tokens examples\first.geolang` to inspect lexer tokens.

The interpreter computes circle area and circumference, rectangle and square
area and perimeter, and triangle area from `base` and `height`. To calculate a
triangle's area and perimeter from its side lengths, provide `side_a`, `side_b`,
and `side_c`; the analyzer checks the triangle inequality. Base and height do
not determine a triangle's perimeter, so that form reports area only.

## Language grammar

```text
program       := ["language" IDENTIFIER NEWLINE] statement*
statement     := variable-declaration | assignment | geometry-declaration
                 | calculate-statement | if-statement | while-statement
variable-declaration
              := "let" IDENTIFIER "=" expression
assignment    := "set" IDENTIFIER "=" expression
geometry-declaration
              := SHAPE [IDENTIFIER] (IDENTIFIER "=" expression)+
calculate-statement
              := "calculate" (SHAPE | IDENTIFIER)
if-statement  := "if" condition NEWLINE statement*
                 ["else" NEWLINE statement*] "end"
while-statement
              := "while" condition NEWLINE statement* "end"
condition     := expression COMPARISON expression
expression    := term (("+" | "-") term)*
term          := unary (("*" | "/") unary)*
unary         := ("+" | "-") unary | NUMBER | IDENTIFIER | "(" expression ")"
COMPARISON    := "==" | "!=" | "<" | "<=" | ">" | ">="
SHAPE         := "circle" | "triangle" | "rectangle" | "square"
```

Statements are separated by newlines. Parentheses and standard arithmetic
precedence are represented in the AST. Semantic analysis validates dimension
expressions before the interpreter evaluates the geometry formulas.
Variables must be declared before use; `set` updates a declared variable.
Variable and shape declarations belong at the top level, outside control-flow
blocks. Shape names must be unique. For backwards compatibility, unnamed shapes
can still use `calculate circle`, `calculate triangle`, and similar type-based
instructions; only one unnamed shape of each type is allowed.

`if` conditions execute one branch. `while` conditions are checked before each
iteration. Loops stop with a runtime error after 10,000 iterations to avoid
unintended infinite execution.

```geolang
let count = 0
while count < 3
    set count = count + 1
end

if count == 3
    calculate wheel
else
    calculate backup_wheel
end
```

Comparison operators are numeric (`==`, `!=`, `<`, `<=`, `>`, `>=`). Variables
must be declared with `let` before they can be updated with `set`. Shape and
variable declarations are currently restricted to the top-level program; the
blocks can contain assignments, calculations, and nested control flow.

## Initial semantic rules

| Shape | Required dimensions |
|---|---|
| `circle` | `radius` (zero or greater) |
| `triangle` | `base`, `height`; or `side_a`, `side_b`, `side_c` |
| `rectangle` | `length`, `width` (both greater than zero) |
| `square` | `side` (greater than zero) |

Dimension expressions must evaluate to finite numbers, and division by zero is
reported as a semantic error. Named shapes may share a type, and
`calculate name` refers to a particular named shape. Calculations may appear
before shape declarations. Only one unnamed shape of each type is allowed.

All triangle dimensions must be greater than zero. Side-based triangles must
satisfy the triangle inequality.

## Test

```powershell
python -m unittest discover -s tests -v
```

The test suite includes command-line integration tests for successful programs
and lexical, syntax, semantic, and runtime failures.

## Architecture

- `src/geolang/lexer.py` turns source text into typed tokens and tracks
  1-based line and column positions.
- `src/geolang/parser.py` uses recursive descent to validate grammar and build
  the program tree.
- `src/geolang/ast_nodes.py` defines immutable nodes for programs, geometry
  declarations, variables, calculation instructions, and expressions.
- `src/geolang/semantic.py` validates dimensions and shape references before
  execution.
- `src/geolang/expressions.py` evaluates arithmetic expressions consistently
  during semantic analysis and execution.
- `src/geolang/interpreter.py` computes geometry results for `calculate`
  instructions.
- `src/geolang/errors.py` defines source-located errors; the lexer raises a
  lexical error for unsupported characters, the parser reports syntax errors,
  semantic analysis reports invalid declarations or calculations, and runtime
  errors report calculations outside the supported numeric range or loops
  exceeding their iteration limit.
- `src/geolang/main.py` is the command-line entry point.
- `tests/` contains standard-library `unittest` tests.
- `examples/` contains runnable GeoLang source examples.

## Project status

GeoLang 0.1.0 is a runnable, geometry-focused interpreted language. It includes
lexing, parsing and AST construction, semantic checks, arithmetic, variables,
named shapes, conditionals, loops, source-file execution, and source-located
errors. The project is installable and has no runtime third-party dependencies.

The test suite includes unit tests and CLI integration tests for successful
execution and lexical, syntax, semantic, and runtime failures. GeoLang does not
compile to machine code or another language. User-defined functions, a REPL,
and user-defined instructions remain future features.
=======
A custom geometry-oriented programming language built with Python
>>>>>>> 094c888c6f6c77e24b7a32ccfe0380eaceeab062
