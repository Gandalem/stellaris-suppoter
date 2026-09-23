"""Lossless, bounded byte-oriented lexer for Paradox-style script fixtures.

Byte spans are zero-based half-open offsets into the original input. Line and column
coordinates are one-based; end coordinates are exclusive. CRLF counts as one newline.
A leading UTF-8 BOM is emitted as its own zero-column-width token so the following
source byte still begins at line 1, column 1.

The lexer enforces input-byte and token-count budgets before unbounded Python object
growth. Position tracking is streaming and does not build a per-character position map.
"""

from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Literal

TokenKind = Literal[
    "bom",
    "whitespace",
    "comment",
    "lbrace",
    "rbrace",
    "assign",
    "gt",
    "lt",
    "gte",
    "lte",
    "string",
    "number",
    "identifier",
    "variable",
]
Severity = Literal["warning", "error"]

DEFAULT_LEXER_MAX_BYTES = 16 * 1024 * 1024
DEFAULT_LEXER_MAX_TOKENS = 100_000

_UTF8_BOM = b"\xef\xbb\xbf"
_WHITESPACE = b" \t\r\n\v\f"
_SPECIAL = b'{}=<>"#'
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")
_WHITESPACE_RE = re.compile(rb"[ \t\r\n\v\f]+")
_SCALAR_END_RE = re.compile(rb'[ \t\r\n\v\f{}=<>"#]')


@dataclass(frozen=True)
class SourceSpan:
    byte_start: int
    byte_end: int
    line_start: int
    column_start: int
    line_end: int
    column_end: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


@dataclass(frozen=True)
class Token:
    kind: TokenKind
    text: str
    span: SourceSpan

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "text": self.text,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class LexerDiagnostic:
    code: str
    severity: Severity
    message: str
    span: SourceSpan

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class LexResult:
    tokens: tuple[Token, ...]
    diagnostics: tuple[LexerDiagnostic, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)


def _validate_limit(value: int, *, name: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    return value


def _advance_text_position(
    text: str,
    line: int,
    column: int,
) -> tuple[int, int]:
    """Advance coordinates using C-backed string scans, with CRLF as one newline."""

    cr_count = text.count("\r")
    lf_count = text.count("\n")
    newline_count = cr_count + lf_count - text.count("\r\n")
    if newline_count == 0:
        return line, column + len(text)

    last_break = max(text.rfind("\r"), text.rfind("\n"))
    return line + newline_count, len(text) - last_break


def _span_from_text(
    text: str,
    start: int,
    end: int,
    line: int,
    column: int,
) -> tuple[SourceSpan, int, int]:
    line_end, column_end = _advance_text_position(text, line, column)
    return (
        SourceSpan(
            byte_start=start,
            byte_end=end,
            line_start=line,
            column_start=column,
            line_end=line_end,
            column_end=column_end,
        ),
        line_end,
        column_end,
    )


def _position_at(source: bytes, offset: int) -> tuple[int, int]:
    start = len(_UTF8_BOM) if source.startswith(_UTF8_BOM) else 0
    if offset <= start:
        return 1, 1
    prefix = source[start:offset].decode("utf-8", errors="strict")
    return _advance_text_position(prefix, 1, 1)


def _validate_utf8(source: bytes) -> None:
    """Strict validation bounded by max_bytes at the public entrypoint."""

    source.decode("utf-8", errors="strict")


def _decode_error_result(source: bytes, exc: UnicodeDecodeError) -> LexResult:
    line, column = _position_at(source, exc.start)
    width = max(1, exc.end - exc.start)
    diagnostic = LexerDiagnostic(
        code="ENCODING_ERROR",
        severity="error",
        message="Source bytes are not valid UTF-8.",
        span=SourceSpan(
            byte_start=exc.start,
            byte_end=exc.end,
            line_start=line,
            column_start=column,
            line_end=line,
            column_end=column + width,
        ),
    )
    return LexResult(tokens=(), diagnostics=(diagnostic,))


def _limit_diagnostic(
    *,
    message: str,
    offset: int,
    line: int,
    column: int,
) -> LexerDiagnostic:
    return LexerDiagnostic(
        code="LIMIT_EXCEEDED",
        severity="error",
        message=message,
        span=SourceSpan(
            byte_start=offset,
            byte_end=offset,
            line_start=line,
            column_start=column,
            line_end=line,
            column_end=column,
        ),
    )


def _make_token(
    kind: TokenKind,
    source: bytes,
    start: int,
    end: int,
    line: int,
    column: int,
) -> tuple[Token, int, int]:
    text = source[start:end].decode("utf-8", errors="strict")
    span, line_end, column_end = _span_from_text(
        text,
        start,
        end,
        line,
        column,
    )
    return (
        Token(
            kind=kind,
            text=text,
            span=span,
        ),
        line_end,
        column_end,
    )


def _scalar_kind(text: str) -> TokenKind:
    if text.startswith("@"):
        return "variable"
    if _NUMBER_RE.fullmatch(text):
        return "number"
    return "identifier"


def lex_bytes(
    source: bytes,
    *,
    max_bytes: int = DEFAULT_LEXER_MAX_BYTES,
    max_tokens: int = DEFAULT_LEXER_MAX_TOKENS,
) -> LexResult:
    """Tokenize UTF-8 bytes with bounded allocations and exact original byte spans."""

    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    max_bytes = _validate_limit(max_bytes, name="max_bytes")
    max_tokens = _validate_limit(max_tokens, name="max_tokens")

    if len(source) > max_bytes:
        return LexResult(
            tokens=(),
            diagnostics=(
                _limit_diagnostic(
                    message="Lexer input-byte limit was exceeded before tokenization.",
                    offset=0,
                    line=1,
                    column=1,
                ),
            ),
        )

    try:
        _validate_utf8(source)
    except UnicodeDecodeError as exc:
        return _decode_error_result(source, exc)

    tokens: list[Token] = []
    diagnostics: list[LexerDiagnostic] = []
    offset = 0
    line = 1
    column = 1
    size = len(source)

    def emit(kind: TokenKind, start: int, end: int) -> LexResult | None:
        nonlocal line, column
        if len(tokens) >= max_tokens:
            return LexResult(
                tokens=tuple(tokens),
                diagnostics=(
                    _limit_diagnostic(
                        message="Lexer token-count limit was exceeded.",
                        offset=start,
                        line=line,
                        column=column,
                    ),
                ),
            )
        token, line, column = _make_token(
            kind,
            source,
            start,
            end,
            line,
            column,
        )
        tokens.append(token)
        return None

    if source.startswith(_UTF8_BOM):
        if max_tokens < 1:
            return LexResult(
                tokens=(),
                diagnostics=(
                    _limit_diagnostic(
                        message="Lexer token-count limit was exceeded.",
                        offset=0,
                        line=1,
                        column=1,
                    ),
                ),
            )
        tokens.append(
            Token(
                kind="bom",
                text=_UTF8_BOM.decode("utf-8"),
                span=SourceSpan(
                    byte_start=0,
                    byte_end=len(_UTF8_BOM),
                    line_start=1,
                    column_start=1,
                    line_end=1,
                    column_end=1,
                ),
            )
        )
        offset = len(_UTF8_BOM)

    while offset < size:
        if len(tokens) >= max_tokens:
            return LexResult(
                tokens=tuple(tokens),
                diagnostics=(
                    _limit_diagnostic(
                        message="Lexer token-count limit was exceeded.",
                        offset=offset,
                        line=line,
                        column=column,
                    ),
                ),
            )

        byte = source[offset]

        if byte in _WHITESPACE:
            match = _WHITESPACE_RE.match(source, offset)
            assert match is not None
            end = match.end()
            limited = emit("whitespace", offset, end)
            if limited is not None:
                return limited
            offset = end
            continue

        if byte == ord("#"):
            lf = source.find(b"\n", offset + 1)
            cr = source.find(b"\r", offset + 1)
            candidates = [value for value in (lf, cr) if value != -1]
            end = min(candidates) if candidates else size
            limited = emit("comment", offset, end)
            if limited is not None:
                return limited
            offset = end
            continue

        if byte == ord('"'):
            end = offset + 1
            terminated = False
            while end < size:
                quote = source.find(b'"', end)
                escape = source.find(b"\\", end)
                if quote == -1 and escape == -1:
                    end = size
                    break
                if escape != -1 and (quote == -1 or escape < quote):
                    end = min(size, escape + 2)
                    continue
                end = quote + 1
                terminated = True
                break

            start_line = line
            start_column = column
            limited = emit("string", offset, end)
            if limited is not None:
                return limited
            if not terminated:
                diagnostics.append(
                    LexerDiagnostic(
                        code="LEX_UNTERMINATED_STRING",
                        severity="error",
                        message="Quoted string reaches end of file without a closing quote.",
                        span=SourceSpan(
                            byte_start=offset,
                            byte_end=end,
                            line_start=start_line,
                            column_start=start_column,
                            line_end=line,
                            column_end=column,
                        ),
                    )
                )
            offset = end
            continue

        if source.startswith(b">=", offset):
            limited = emit("gte", offset, offset + 2)
            if limited is not None:
                return limited
            offset += 2
            continue
        if source.startswith(b"<=", offset):
            limited = emit("lte", offset, offset + 2)
            if limited is not None:
                return limited
            offset += 2
            continue

        single: dict[int, TokenKind] = {
            ord("{"): "lbrace",
            ord("}"): "rbrace",
            ord("="): "assign",
            ord(">"): "gt",
            ord("<"): "lt",
        }
        if byte in single:
            limited = emit(single[byte], offset, offset + 1)
            if limited is not None:
                return limited
            offset += 1
            continue

        boundary = _SCALAR_END_RE.search(source, offset + 1)
        end = boundary.start() if boundary is not None else size
        text = source[offset:end].decode("utf-8", errors="strict")
        limited = emit(_scalar_kind(text), offset, end)
        if limited is not None:
            return limited
        offset = end

    return LexResult(tokens=tuple(tokens), diagnostics=tuple(diagnostics))
