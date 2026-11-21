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
from geolang.compiler import PythonCompiler
from geolang.native_compiler import NativeCompiler
from geolang.repl import run_repl


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
        nargs="?",
        help="GeoLang source file to run",
    )
    output_group = argument_parser.add_mutually_exclusive_group()
    output_group.add_argument(
        "--tokens",
        action="store_true",
        help="print lexer tokens instead of the parsed program summary",
    )
    output_group.add_argument(
        "--compile",
        action="store_true",
        help="print executable Python source generated from the program",
    )
    output_group.add_argument(
        "--native",
        type=Path,
        metavar="OUTPUT.exe",
        help="compile a Windows x64 executable at OUTPUT.exe",
    )
    argument_parser.add_argument(
        "--repl",
        action="store_true",
        help="start the interactive GeoLang prompt",
    )
    arguments = argument_parser.parse_args(argv)

    if arguments.repl:
        if arguments.source_file is not None:
            argument_parser.error("source_file cannot be used with --repl")
        if arguments.tokens or arguments.compile or arguments.native:
            argument_parser.error(
                "--repl cannot be combined with --tokens, --compile, or --native"
            )
        return run_repl()
    if arguments.source_file is None:
        argument_parser.error("source_file is required unless --repl is used")

    try:
        source = arguments.source_file.read_text(encoding="utf-8")
        if arguments.tokens:
            tokens = Lexer(source).tokenize()
        else:
            program = Parser.load_file(arguments.source_file)
            if arguments.compile:
                generated = PythonCompiler().compile(program)
            elif arguments.native:
                output = NativeCompiler().compile(program, arguments.native)
            else:
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
    if arguments.compile:
        print(generated, end="")
        return 0
    if arguments.native:
        print(f"Native executable written to {output}")
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