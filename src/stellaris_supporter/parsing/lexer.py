"""Lossless byte-oriented lexer for Paradox-style script fixtures.

Byte spans are zero-based half-open offsets into the original input. Line and column
coordinates are one-based; end coordinates are exclusive. CRLF counts as one newline.
A leading UTF-8 BOM is emitted as its own zero-column-width token so the following
source byte still begins at line 1, column 1.
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

_UTF8_BOM = b"\xef\xbb\xbf"
_WHITESPACE = b" \t\r\n\v\f"
_SPECIAL = b'{}=<>"#'
_NUMBER_RE = re.compile(r"[+-]?(?:\d+(?:\.\d*)?|\.\d+)\Z")


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


def _utf8_length(first: int) -> int:
    if first < 0x80:
        return 1
    if first < 0xE0:
        return 2
    if first < 0xF0:
        return 3
    return 4


def _position_map(source: bytes) -> dict[int, tuple[int, int]]:
    positions: dict[int, tuple[int, int]] = {0: (1, 1)}
    line = 1
    column = 1
    offset = 0

    if source.startswith(_UTF8_BOM):
        positions[3] = (1, 1)
        offset = 3

    while offset < len(source):
        positions[offset] = (line, column)
        if source.startswith(b"\r\n", offset):
            offset += 2
            line += 1
            column = 1
            positions[offset] = (line, column)
            continue

        byte = source[offset]
        if byte in (0x0A, 0x0D):
            offset += 1
            line += 1
            column = 1
            positions[offset] = (line, column)
            continue

        offset += _utf8_length(byte)
        column += 1
        positions[offset] = (line, column)

    positions[len(source)] = (line, column)
    return positions


def _raw_position(source: bytes, offset: int) -> tuple[int, int]:
    prefix = source[:offset]
    if prefix.startswith(_UTF8_BOM):
        prefix = prefix[len(_UTF8_BOM) :]
    text = prefix.decode("utf-8", errors="strict")
    line = 1
    column = 1
    index = 0
    while index < len(text):
        if text.startswith("\r\n", index):
            line += 1
            column = 1
            index += 2
        elif text[index] in "\r\n":
            line += 1
            column = 1
            index += 1
        else:
            column += 1
            index += 1
    return line, column


def _span(
    positions: dict[int, tuple[int, int]],
    byte_start: int,
    byte_end: int,
) -> SourceSpan:
    line_start, column_start = positions[byte_start]
    line_end, column_end = positions[byte_end]
    return SourceSpan(
        byte_start=byte_start,
        byte_end=byte_end,
        line_start=line_start,
        column_start=column_start,
        line_end=line_end,
        column_end=column_end,
    )


def _decode_error_result(source: bytes, exc: UnicodeDecodeError) -> LexResult:
    line, column = _raw_position(source, exc.start)
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


def _token(
    kind: TokenKind,
    source: bytes,
    positions: dict[int, tuple[int, int]],
    start: int,
    end: int,
) -> Token:
    return Token(
        kind=kind,
        text=source[start:end].decode("utf-8", errors="strict"),
        span=_span(positions, start, end),
    )


def _scalar_kind(text: str) -> TokenKind:
    if text.startswith("@"):
        return "variable"
    if _NUMBER_RE.fullmatch(text):
        return "number"
    return "identifier"


def lex_bytes(source: bytes) -> LexResult:
    """Tokenize validated UTF-8 bytes while preserving exact original byte spans."""

    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")

    try:
        source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        return _decode_error_result(source, exc)

    positions = _position_map(source)
    tokens: list[Token] = []
    diagnostics: list[LexerDiagnostic] = []
    offset = 0
    size = len(source)

    if source.startswith(_UTF8_BOM):
        tokens.append(_token("bom", source, positions, 0, len(_UTF8_BOM)))
        offset = len(_UTF8_BOM)

    while offset < size:
        byte = source[offset]

        if byte in _WHITESPACE:
            end = offset + 1
            while end < size and source[end] in _WHITESPACE:
                end += 1
            tokens.append(_token("whitespace", source, positions, offset, end))
            offset = end
            continue

        if byte == ord("#"):
            end = offset + 1
            while end < size and source[end] not in (0x0A, 0x0D):
                end += 1
            tokens.append(_token("comment", source, positions, offset, end))
            offset = end
            continue

        if byte == ord('"'):
            end = offset + 1
            terminated = False
            while end < size:
                if source[end] == ord("\\"):
                    if end + 1 < size:
                        end += 2
                    else:
                        end += 1
                    continue
                if source[end] == ord('"'):
                    end += 1
                    terminated = True
                    break
                end += 1

            tokens.append(_token("string", source, positions, offset, end))
            if not terminated:
                diagnostics.append(
                    LexerDiagnostic(
                        code="LEX_UNTERMINATED_STRING",
                        severity="error",
                        message="Quoted string reaches end of file without a closing quote.",
                        span=_span(positions, offset, end),
                    )
                )
            offset = end
            continue

        if source.startswith(b">=", offset):
            tokens.append(_token("gte", source, positions, offset, offset + 2))
            offset += 2
            continue
        if source.startswith(b"<=", offset):
            tokens.append(_token("lte", source, positions, offset, offset + 2))
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
            tokens.append(_token(single[byte], source, positions, offset, offset + 1))
            offset += 1
            continue

        end = offset + 1
        while (
            end < size
            and source[end] not in _WHITESPACE
            and source[end] not in _SPECIAL
        ):
            end += 1
        text = source[offset:end].decode("utf-8", errors="strict")
        tokens.append(_token(_scalar_kind(text), source, positions, offset, end))
        offset = end

    return LexResult(tokens=tuple(tokens), diagnostics=tuple(diagnostics))
