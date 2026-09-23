"""Static parsing primitives."""

from stellaris_supporter.parsing.lexer import (
    DEFAULT_LEXER_MAX_BYTES,
    DEFAULT_LEXER_MAX_TOKENS,
    LexerDiagnostic,
    LexResult,
    SourceSpan,
    Token,
    lex_bytes,
)

__all__ = [
    "DEFAULT_LEXER_MAX_BYTES",
    "DEFAULT_LEXER_MAX_TOKENS",
    "LexResult",
    "LexerDiagnostic",
    "SourceSpan",
    "Token",
    "lex_bytes",
]
