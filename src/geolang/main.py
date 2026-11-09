"""Command-line entry point for the GeoLang interpreter."""

import argparse
import sys
from collections.abc import Sequence
from pathlib import Path

from geolang import __version__
from geolang.errors import GeoLangError
from geolang.lexer import Lexer
from geolang.parser import Parser
from geolang.interpreter import Interpreter, format_number


def main(argv: Sequence[str] | None = None) -> int:
    argument_parser = argparse.ArgumentParser(
        prog="geolang",
        description="Run a GeoLang source file.",
    )
    argument_parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )
    argument_parser.add_argument(
        "source_file",
        type=Path,
        help="GeoLang source file to run",
    )
    argument_parser.add_argument(
        "--tokens",
        action="store_true",
        help="print lexer tokens instead of the parsed program summary",
    )
    arguments = argument_parser.parse_args(argv)

    try:
        source = arguments.source_file.read_text(encoding="utf-8")
        if arguments.tokens:
            tokens = Lexer(source).tokenize()
        else:
            program = Parser.from_source(source).parse()
            results = Interpreter().execute(program)
    except (OSError, UnicodeError) as error:
        print(f"GeoLang Input Error: {error}", file=sys.stderr)
        return 1
    except GeoLangError as error:
        print(error, file=sys.stderr)
        print("\nProgram processing terminated.", file=sys.stderr)
        return 1

    if arguments.tokens:
        for token in tokens:
            print(f"{token.type.name:<12} {token.lexeme!r} ({token.line}:{token.column})")
        return 0

    print(f"GeoLang Interpreter v{__version__}")
    for result in results:
        shape_label = result.kind.name.title()
        if result.name is not None:
            shape_label += f" ({result.name})"
        print(f"\n{shape_label}:")
        for name, value in result.dimensions:
            label = name.replace("_", " ").title()
            print(f"{label} = {format_number(value)}")
        for name, value in result.measurements:
            print(f"{name.title()} = {format_number(value)}")
    print("\nExecution completed successfully.")
    return 0