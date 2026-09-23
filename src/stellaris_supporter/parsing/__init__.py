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

from stellaris_supporter.parsing.parser import (
    DEFAULT_PARSER_MAX_DEPTH,
    DEFAULT_PARSER_MAX_DIAGNOSTICS,
    DEFAULT_PARSER_MAX_NODES,
    AstNode,
    BlockNode,
    DocumentNode,
    PairNode,
    ParseDiagnostic,
    ParseResult,
    ScalarNode,
    UnknownNode,
    parse_bytes,
)

__all__ += [
    "DEFAULT_PARSER_MAX_DEPTH",
    "DEFAULT_PARSER_MAX_DIAGNOSTICS",
    "DEFAULT_PARSER_MAX_NODES",
    "AstNode",
    "BlockNode",
    "DocumentNode",
    "PairNode",
    "ParseDiagnostic",
    "ParseResult",
    "ScalarNode",
    "UnknownNode",
    "parse_bytes",
]
