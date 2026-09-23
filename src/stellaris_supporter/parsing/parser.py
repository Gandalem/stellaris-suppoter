"""Ordered, bounded AST parser built on the lossless lexer."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal, TypeAlias

from stellaris_supporter.parsing.lexer import (
    DEFAULT_LEXER_MAX_BYTES,
    DEFAULT_LEXER_MAX_TOKENS,
    LexerDiagnostic,
    SourceSpan,
    Token,
    TokenKind,
    lex_bytes,
)

DEFAULT_PARSER_MAX_DEPTH = 128
DEFAULT_PARSER_MAX_NODES = 100_000
DEFAULT_PARSER_MAX_DIAGNOSTICS = 1_000
MAX_PARSER_RECURSION_DEPTH = DEFAULT_PARSER_MAX_DEPTH

_TRIVIA = {"bom", "whitespace", "comment"}
_BINARY_OPERATORS = {"assign", "gt", "lt", "gte", "lte"}
_SCALAR_KINDS = {"identifier", "variable", "number", "string"}
_OPERATORISH_RE = re.compile(r"^[\^!~%&|+*/?]+$")
_OPERATORISH_SUFFIX_RE = re.compile(r"[\^!~%&|+*/?]+$")

DiagnosticOrigin = Literal["lexer", "parser"]
Severity = Literal["warning", "error"]


@dataclass(frozen=True)
class ParseDiagnostic:
    code: str
    severity: Severity
    message: str
    span: SourceSpan
    origin: DiagnosticOrigin = "parser"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "span": self.span.to_dict(),
            "origin": self.origin,
        }


@dataclass(frozen=True)
class ScalarNode:
    kind: Literal["scalar"]
    token_kind: TokenKind
    text: str
    span: SourceSpan

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "token_kind": self.token_kind,
            "text": self.text,
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class PairNode:
    kind: Literal["pair"]
    key_kind: TokenKind
    key_text: str
    key_span: SourceSpan
    operator_kind: TokenKind
    operator_text: str
    operator_span: SourceSpan
    value: AstNode | None
    span: SourceSpan

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "key_kind": self.key_kind,
            "key_text": self.key_text,
            "key_span": self.key_span.to_dict(),
            "operator_kind": self.operator_kind,
            "operator_text": self.operator_text,
            "operator_span": self.operator_span.to_dict(),
            "value": None if self.value is None else self.value.to_dict(),
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class BlockNode:
    kind: Literal["block"]
    items: tuple[AstNode, ...]
    span: SourceSpan
    closed: bool

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "items": [item.to_dict() for item in self.items],
            "span": self.span.to_dict(),
            "closed": self.closed,
        }


@dataclass(frozen=True)
class UnknownNode:
    kind: Literal["unknown"]
    tokens: tuple[Token, ...]
    span: SourceSpan

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "tokens": [token.to_dict() for token in self.tokens],
            "span": self.span.to_dict(),
        }


AstNode: TypeAlias = ScalarNode | PairNode | BlockNode | UnknownNode


@dataclass(frozen=True)
class DocumentNode:
    kind: Literal["document"]
    items: tuple[AstNode, ...]
    span: SourceSpan

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.span.byte_start : self.span.byte_end]

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "items": [item.to_dict() for item in self.items],
            "span": self.span.to_dict(),
        }


@dataclass(frozen=True)
class ParseResult:
    document: DocumentNode
    tokens: tuple[Token, ...]
    diagnostics: tuple[ParseDiagnostic, ...]
    node_count: int

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(self) -> dict[str, object]:
        return {
            "document": self.document.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "node_count": self.node_count,
        }


def _validate_limit(value: int, *, name: str, maximum: int | None = None) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"{name} must be an integer")
    if value <= 0:
        raise ValueError(f"{name} must be positive")
    if maximum is not None and value > maximum:
        raise ValueError(f"{name} must be <= {maximum}")
    return value


def _merge_spans(first: SourceSpan, last: SourceSpan) -> SourceSpan:
    return SourceSpan(
        byte_start=first.byte_start,
        byte_end=last.byte_end,
        line_start=first.line_start,
        column_start=first.column_start,
        line_end=last.line_end,
        column_end=last.column_end,
    )


def _empty_span() -> SourceSpan:
    return SourceSpan(
        byte_start=0,
        byte_end=0,
        line_start=1,
        column_start=1,
        line_end=1,
        column_end=1,
    )


def _from_lexer_diagnostic(item: LexerDiagnostic) -> ParseDiagnostic:
    return ParseDiagnostic(
        code=item.code,
        severity=item.severity,
        message=item.message,
        span=item.span,
        origin="lexer",
    )


class _Parser:
    def __init__(
        self,
        tokens: tuple[Token, ...],
        *,
        max_depth: int,
        max_nodes: int,
        max_diagnostics: int,
        initial_diagnostics: tuple[ParseDiagnostic, ...],
    ) -> None:
        self.tokens = tokens
        self.max_depth = max_depth
        self.max_nodes = max_nodes
        self.max_diagnostics = max_diagnostics
        self.diagnostics = list(initial_diagnostics[:max_diagnostics])
        self.node_count = 0
        self.stopped = False

    def parse(self) -> ParseResult:
        items, index, _, _ = self._parse_sequence(0, depth=0, stop_on_rbrace=False)
        if not self.stopped:
            index = self._skip_trivia(index)
            while index < len(self.tokens):
                token = self.tokens[index]
                if not self._reserve_node(token.span):
                    break
                node = UnknownNode(kind="unknown", tokens=(token,), span=token.span)
                items.append(node)
                self._diagnose(
                    "PARSE_UNEXPECTED_TOKEN",
                    "Unexpected token at document scope.",
                    token.span,
                )
                index += 1
                index = self._skip_trivia(index)

        span = (
            _merge_spans(self.tokens[0].span, self.tokens[-1].span)
            if self.tokens
            else _empty_span()
        )
        document = DocumentNode(kind="document", items=tuple(items), span=span)
        return ParseResult(
            document=document,
            tokens=self.tokens,
            diagnostics=tuple(self.diagnostics),
            node_count=self.node_count,
        )

    def _diagnose(self, code: str, message: str, span: SourceSpan) -> None:
        if self.stopped and code != "PARSE_DIAGNOSTIC_LIMIT":
            return
        if len(self.diagnostics) < self.max_diagnostics:
            self.diagnostics.append(
                ParseDiagnostic(
                    code=code,
                    severity="error",
                    message=message,
                    span=span,
                    origin="parser",
                )
            )
            return
        if self.diagnostics:
            self.diagnostics[-1] = ParseDiagnostic(
                code="PARSE_DIAGNOSTIC_LIMIT",
                severity="error",
                message="Parser diagnostic limit was exceeded.",
                span=span,
                origin="parser",
            )
        self.stopped = True

    def _reserve_node(self, span: SourceSpan) -> bool:
        if self.node_count >= self.max_nodes:
            self._diagnose(
                "PARSE_NODE_LIMIT",
                "Parser node-count limit was exceeded.",
                span,
            )
            self.stopped = True
            return False
        self.node_count += 1
        return True

    def _skip_trivia(self, index: int) -> int:
        while index < len(self.tokens) and self.tokens[index].kind in _TRIVIA:
            index += 1
        return index

    def _next_significant(self, index: int) -> int:
        return self._skip_trivia(index)

    def _parse_sequence(
        self,
        index: int,
        *,
        depth: int,
        stop_on_rbrace: bool,
    ) -> tuple[list[AstNode], int, Token | None, bool]:
        items: list[AstNode] = []
        while not self.stopped:
            index = self._skip_trivia(index)
            if index >= len(self.tokens):
                return items, index, None, False

            token = self.tokens[index]
            if token.kind == "rbrace":
                if stop_on_rbrace:
                    return items, index + 1, token, True
                if not self._reserve_node(token.span):
                    return items, index, None, False
                items.append(UnknownNode(kind="unknown", tokens=(token,), span=token.span))
                self._diagnose(
                    "PARSE_UNMATCHED_RBRACE",
                    "Closing brace has no matching opening brace.",
                    token.span,
                )
                index += 1
                continue

            node, index = self._parse_item(index, depth=depth)
            if node is not None:
                items.append(node)
        return items, index, None, False

    def _parse_item(self, index: int, *, depth: int) -> tuple[AstNode | None, int]:
        token = self.tokens[index]

        if token.kind == "lbrace":
            return self._parse_block(index, depth=depth + 1)

        if token.kind not in _SCALAR_KINDS:
            if not self._reserve_node(token.span):
                return None, index
            self._diagnose(
                "PARSE_UNEXPECTED_TOKEN",
                f"Unexpected token kind {token.kind!r}.",
                token.span,
            )
            return UnknownNode(kind="unknown", tokens=(token,), span=token.span), index + 1

        unknown = self._unknown_operator_expression(index)
        if unknown is not None:
            return unknown

        operator_index = self._next_significant(index + 1)
        if (
            operator_index < len(self.tokens)
            and self.tokens[operator_index].kind in _BINARY_OPERATORS
        ):
            unknown_pair = self._unsupported_pair_expression(index, operator_index)
            if unknown_pair is not None:
                return unknown_pair
            if self.stopped:
                return None, index
            return self._parse_pair(index, operator_index, depth=depth)

        if not self._reserve_node(token.span):
            return None, index
        return (
            ScalarNode(
                kind="scalar",
                token_kind=token.kind,
                text=token.text,
                span=token.span,
            ),
            index + 1,
        )

    def _unknown_operator_expression(
        self,
        index: int,
    ) -> tuple[UnknownNode, int] | None:
        middle_index = self._next_significant(index + 1)
        if middle_index >= len(self.tokens):
            return None
        middle = self.tokens[middle_index]
        if middle.kind != "identifier" or not _OPERATORISH_RE.fullmatch(middle.text):
            return None

        operator_index = self._next_significant(middle_index + 1)
        if (
            operator_index >= len(self.tokens)
            or self.tokens[operator_index].kind not in _BINARY_OPERATORS
        ):
            return None

        end_index = self._consume_raw_value(operator_index + 1)
        last_index = self._last_significant_index(index, end_index)
        last = self.tokens[last_index]
        span = _merge_spans(self.tokens[index].span, last.span)
        if not self._reserve_node(span):
            return None
        significant = tuple(
            token
            for token in self.tokens[index:end_index]
            if token.kind not in _TRIVIA
        )
        self._diagnose(
            "PARSE_UNKNOWN_SYNTAX",
            "Unsupported operator or expression form was preserved without semantics.",
            span,
        )
        return UnknownNode(kind="unknown", tokens=significant, span=span), end_index

    def _same_line(self, left_index: int, right_index: int) -> bool:
        return (
            self.tokens[left_index].span.line_end
            == self.tokens[right_index].span.line_start
        )

    def _unsupported_pair_expression(
        self,
        key_index: int,
        operator_index: int,
    ) -> tuple[UnknownNode, int] | None:
        key = self.tokens[key_index]
        value_index = self._next_significant(operator_index + 1)
        end_index: int | None = None

        if (
            key.kind == "identifier"
            and _OPERATORISH_SUFFIX_RE.search(key.text) is not None
        ):
            end_index = self._consume_raw_value(operator_index + 1)
        elif (
            value_index < len(self.tokens)
            and self.tokens[value_index].kind in _SCALAR_KINDS
        ):
            trailing_index = self._next_significant(value_index + 1)
            if (
                trailing_index < len(self.tokens)
                and self._same_line(value_index, trailing_index)
                and self.tokens[trailing_index].kind == "lbrace"
            ):
                end_index = self._skip_balanced_block(trailing_index)
            elif (
                trailing_index < len(self.tokens)
                and self._same_line(value_index, trailing_index)
                and self.tokens[trailing_index].kind == "identifier"
                and _OPERATORISH_RE.fullmatch(
                    self.tokens[trailing_index].text
                )
                is not None
            ):
                trailing_operator = self._next_significant(trailing_index + 1)
                if (
                    trailing_operator < len(self.tokens)
                    and self.tokens[trailing_operator].kind in _BINARY_OPERATORS
                ):
                    end_index = self._consume_raw_value(trailing_operator + 1)

        if end_index is None:
            return None

        last_index = self._last_significant_index(key_index, end_index)
        span = _merge_spans(key.span, self.tokens[last_index].span)
        if not self._reserve_node(span):
            return None
        significant = tuple(
            token
            for token in self.tokens[key_index:end_index]
            if token.kind not in _TRIVIA
        )
        self._diagnose(
            "PARSE_UNKNOWN_SYNTAX",
            "Unsupported operator or typed expression was preserved without semantics.",
            span,
        )
        return UnknownNode(kind="unknown", tokens=significant, span=span), end_index

    def _consume_raw_value(self, index: int) -> int:
        index = self._next_significant(index)
        if index >= len(self.tokens):
            return index
        if self.tokens[index].kind == "rbrace":
            return index
        if self.tokens[index].kind == "lbrace":
            return self._skip_balanced_block(index)
        return index + 1

    def _last_significant_index(self, start: int, end: int) -> int:
        candidate = min(end, len(self.tokens)) - 1
        while candidate > start and self.tokens[candidate].kind in _TRIVIA:
            candidate -= 1
        return candidate

    def _parse_pair(
        self,
        key_index: int,
        operator_index: int,
        *,
        depth: int,
    ) -> tuple[PairNode | None, int]:
        key = self.tokens[key_index]
        operator = self.tokens[operator_index]
        value_index = self._next_significant(operator_index + 1)

        if not self._reserve_node(key.span):
            return None, key_index

        if value_index >= len(self.tokens) or self.tokens[value_index].kind == "rbrace":
            span = _merge_spans(key.span, operator.span)
            self._diagnose(
                "PARSE_MISSING_VALUE",
                "Binary operator has no value.",
                span,
            )
            return (
                PairNode(
                    kind="pair",
                    key_kind=key.kind,
                    key_text=key.text,
                    key_span=key.span,
                    operator_kind=operator.kind,
                    operator_text=operator.text,
                    operator_span=operator.span,
                    value=None,
                    span=span,
                ),
                value_index,
            )

        value, next_index = self._parse_value(value_index, depth=depth)
        end_span = value.span if value is not None else operator.span
        return (
            PairNode(
                kind="pair",
                key_kind=key.kind,
                key_text=key.text,
                key_span=key.span,
                operator_kind=operator.kind,
                operator_text=operator.text,
                operator_span=operator.span,
                value=value,
                span=_merge_spans(key.span, end_span),
            ),
            next_index,
        )

    def _parse_value(
        self,
        index: int,
        *,
        depth: int,
    ) -> tuple[AstNode | None, int]:
        token = self.tokens[index]
        if token.kind == "lbrace":
            return self._parse_block(index, depth=depth + 1)
        if token.kind in _SCALAR_KINDS:
            if not self._reserve_node(token.span):
                return None, index
            return (
                ScalarNode(
                    kind="scalar",
                    token_kind=token.kind,
                    text=token.text,
                    span=token.span,
                ),
                index + 1,
            )
        if not self._reserve_node(token.span):
            return None, index
        self._diagnose(
            "PARSE_UNEXPECTED_VALUE",
            "Unexpected token where a scalar or block value was required.",
            token.span,
        )
        return UnknownNode(kind="unknown", tokens=(token,), span=token.span), index + 1

    def _parse_block(
        self,
        index: int,
        *,
        depth: int,
    ) -> tuple[AstNode | None, int]:
        opening = self.tokens[index]
        if depth > self.max_depth:
            end_index = self._skip_balanced_block(index)
            last_index = self._last_significant_index(index, end_index)
            span = _merge_spans(opening.span, self.tokens[last_index].span)
            if not self._reserve_node(span):
                return None, index
            significant = tuple(
                token
                for token in self.tokens[index:end_index]
                if token.kind not in _TRIVIA
            )
            self._diagnose(
                "PARSE_DEPTH_LIMIT",
                "Parser nesting-depth limit was exceeded.",
                span,
            )
            return UnknownNode(kind="unknown", tokens=significant, span=span), end_index

        if not self._reserve_node(opening.span):
            return None, index

        items, next_index, closing, closed = self._parse_sequence(
            index + 1,
            depth=depth,
            stop_on_rbrace=True,
        )
        last_span = closing.span if closing is not None else (
            self.tokens[self._last_significant_index(index, next_index)].span
            if next_index > index
            else opening.span
        )
        span = _merge_spans(opening.span, last_span)
        if not closed:
            self._diagnose(
                "PARSE_UNCLOSED_BLOCK",
                "Opening brace reaches end of input without a closing brace.",
                span,
            )
        return (
            BlockNode(
                kind="block",
                items=tuple(items),
                span=span,
                closed=closed,
            ),
            next_index,
        )

    def _skip_balanced_block(self, index: int) -> int:
        balance = 0
        cursor = index
        while cursor < len(self.tokens):
            token = self.tokens[cursor]
            if token.kind == "lbrace":
                balance += 1
            elif token.kind == "rbrace":
                balance -= 1
                if balance == 0:
                    return cursor + 1
            cursor += 1
        return len(self.tokens)


def parse_bytes(
    source: bytes,
    *,
    max_bytes: int = DEFAULT_LEXER_MAX_BYTES,
    max_tokens: int = DEFAULT_LEXER_MAX_TOKENS,
    max_depth: int = DEFAULT_PARSER_MAX_DEPTH,
    max_nodes: int = DEFAULT_PARSER_MAX_NODES,
    max_diagnostics: int = DEFAULT_PARSER_MAX_DIAGNOSTICS,
) -> ParseResult:
    """Lex and parse UTF-8 bytes into an ordered, bounded AST."""

    max_depth = _validate_limit(
        max_depth,
        name="max_depth",
        maximum=MAX_PARSER_RECURSION_DEPTH,
    )
    max_nodes = _validate_limit(max_nodes, name="max_nodes")
    max_diagnostics = _validate_limit(max_diagnostics, name="max_diagnostics")

    lexed = lex_bytes(source, max_bytes=max_bytes, max_tokens=max_tokens)
    diagnostics = tuple(_from_lexer_diagnostic(item) for item in lexed.diagnostics)
    parser = _Parser(
        lexed.tokens,
        max_depth=max_depth,
        max_nodes=max_nodes,
        max_diagnostics=max_diagnostics,
        initial_diagnostics=diagnostics,
    )
    return parser.parse()
