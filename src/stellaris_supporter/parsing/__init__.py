"""Static parsing primitives."""

from stellaris_supporter.parsing.lexer import (
    LexerDiagnostic,
    LexResult,
    SourceSpan,
    Token,
    lex_bytes,
)

__all__ = [
    "LexResult",
    "LexerDiagnostic",
    "SourceSpan",
    "Token",
    "lex_bytes",
]
