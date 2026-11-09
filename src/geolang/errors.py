"""Errors reported while processing GeoLang source code."""


class GeoLangError(Exception):
    """Base class for errors that include a GeoLang source location."""

    def __init__(self, phase: str, message: str, line: int, column: int) -> None:
        super().__init__(message)
        self.phase = phase
        self.message = message
        self.line = line
        self.column = column

    def __str__(self) -> str:
        return (
            f"GeoLang {self.phase} Error:\n"
            f"Line {self.line}, Column {self.column}\n\n"
            f"{self.message}"
        )


class LexicalError(GeoLangError):
    """Raised when the lexer encounters a character it cannot recognize."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__("Lexical", message, line, column)


class SyntaxError(GeoLangError):
    """Raised when tokens do not follow the GeoLang grammar."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__("Syntax", message, line, column)


class SemanticError(GeoLangError):
    """Raised when a syntactically valid program is not meaningful."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__("Semantic", message, line, column)


class RuntimeGeoLangError(GeoLangError):
    """Raised when a valid program cannot be executed."""

    def __init__(self, message: str, line: int, column: int) -> None:
        super().__init__("Runtime", message, line, column)
