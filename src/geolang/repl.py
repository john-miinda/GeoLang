"""Interactive GeoLang prompt with persistent source history."""

import sys
from collections.abc import Callable, TextIO

from geolang import __version__
from geolang.errors import GeoLangError
from geolang.interpreter import Interpreter, format_number
from geolang.lexer import Lexer, TokenType
from geolang.parser import Parser


_BLOCK_STARTS = {
    TokenType.FUNCTION,
    TokenType.INSTRUCTION,
    TokenType.IF,
    TokenType.WHILE,
}


def run_repl(
    input_fn: Callable[[str], str] | None = None,
    stdout: TextIO | None = None,
    stderr: TextIO | None = None,
) -> int:
    """Run the interactive prompt until the user enters ``exit`` or EOF."""
    read_line = input if input_fn is None else input_fn
    output = sys.stdout if stdout is None else stdout
    errors = sys.stderr if stderr is None else stderr
    history: list[str] = []
    pending: list[str] = []
    prior_result_count = 0

    print(f"GeoLang REPL v{__version__} (type 'exit' to quit)", file=output)
    while True:
        try:
            line = read_line("... " if pending else ">>> ")
        except EOFError:
            if pending:
                _report_source_error("\n".join(pending), errors)
            print(file=output)
            return 0
        except KeyboardInterrupt:
            pending.clear()
            print("\nInput cancelled.", file=output)
            continue

        if not pending and line.strip().lower() in {"exit", "quit"}:
            return 0
        if not line.strip() and not pending:
            continue

        pending.append(line)
        candidate = "\n".join(pending)
        try:
            block_depth = _block_depth(candidate)
        except GeoLangError as error:
            _print_error(error, errors)
            pending.clear()
            continue
        if block_depth > 0:
            continue

        candidate_history = [*history, candidate]
        source = "\n".join(candidate_history)
        try:
            program = Parser.from_source(source).parse()
            results = Interpreter().execute(program)
        except GeoLangError as error:
            _print_error(error, errors)
            pending.clear()
            continue

        for result in results[prior_result_count:]:
            label = result.kind.name.title()
            if result.name is not None:
                label += f" ({result.name})"
            print(f"\n{label}:", file=output)
            for name, value in result.dimensions:
                print(
                    f"{name.replace('_', ' ').title()} = {format_number(value)}",
                    file=output,
                )
            for name, value in result.measurements:
                print(f"{name.title()} = {format_number(value)}", file=output)
        history = candidate_history
        prior_result_count = len(results)
        pending.clear()


def _block_depth(source: str) -> int:
    tokens = Lexer(source).tokenize()
    depth = 0
    for token in tokens:
        if token.type in _BLOCK_STARTS:
            depth += 1
        elif token.type is TokenType.END:
            depth -= 1
    return depth


def _report_source_error(source: str, stream: TextIO) -> None:
    try:
        Parser.from_source(source).parse()
    except GeoLangError as error:
        _print_error(error, stream)


def _print_error(error: GeoLangError, stream: TextIO) -> None:
    print(error, file=stream)
    print("Program processing terminated.", file=stream)
