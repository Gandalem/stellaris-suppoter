"""Loss-preserving technology adapter for ordered script AST."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal

from stellaris_supporter.parsing import (
    AstNode,
    BlockNode,
    PairNode,
    ParseDiagnostic,
    ParseResult,
    ScalarNode,
    SourceSpan,
    UnknownNode,
)

SourceKind = Literal["synthetic", "base", "mod", "official", "wiki", "community"]
DiagnosticSeverity = Literal["info", "warning", "error"]
DiagnosticOrigin = Literal["adapter", "lexer", "parser"]
CandidateResolution = Literal["raw_definition", "partial"]

DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES = 1024 * 1024


class AdapterSerializationLimitError(ValueError):
    """Raised when optional raw serialization exceeds its explicit byte budget."""


@dataclass(frozen=True, slots=True)
class SourceContext:
    snapshot_id: str
    source_kind: SourceKind
    source_id: str
    relative_path: str
    file_sha256: str


@dataclass(frozen=True, slots=True)
class SourceRef:
    snapshot_id: str
    source_kind: SourceKind
    source_id: str
    relative_path: str
    file_sha256: str
    byte_start: int
    byte_end: int
    line_start: int
    line_end: int

    def raw_bytes(self, source: bytes) -> bytes:
        return source[self.byte_start : self.byte_end]

    def raw_text(self, source: bytes) -> str:
        return self.raw_bytes(source).decode("utf-8", errors="strict")

    def to_dict(self) -> dict[str, object]:
        return {
            "snapshot_id": self.snapshot_id,
            "source_kind": self.source_kind,
            "source_id": self.source_id,
            "relative_path": self.relative_path,
            "file_sha256": self.file_sha256,
            "byte_start": self.byte_start,
            "byte_end": self.byte_end,
            "line_start": self.line_start,
            "line_end": self.line_end,
        }


@dataclass(slots=True)
class _RawOutputBudget:
    remaining: int

    def materialize(self, source: bytes, source_ref: SourceRef) -> str:
        size = source_ref.byte_end - source_ref.byte_start
        if size > self.remaining:
            raise AdapterSerializationLimitError(
                "Raw serialization byte budget was exceeded."
            )
        self.remaining -= size
        return source_ref.raw_text(source)


@dataclass(frozen=True, slots=True)
class RawNodeRef:
    kind: str
    source_ref: SourceRef
    key: str | None = None
    operator: str | None = None
    children: tuple[RawNodeRef, ...] = ()
    _source: bytes = field(repr=False, compare=False, default=b"")

    @property
    def raw(self) -> str:
        """Materialize this node's source slice on demand without caching it."""

        return self.source_ref.raw_text(self._source)

    def raw_bytes(self) -> bytes:
        return self.source_ref.raw_bytes(self._source)

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        _budget: _RawOutputBudget | None = None,
    ) -> dict[str, object]:
        result: dict[str, object] = {
            "kind": self.kind,
            "source_ref": self.source_ref.to_dict(),
            "key": self.key,
            "operator": self.operator,
            "children": [
                item.to_dict(include_raw=include_raw, _budget=_budget)
                for item in self.children
            ],
        }
        if include_raw:
            if _budget is None:
                raise ValueError("raw serialization requires a shared byte budget")
            result["raw"] = _budget.materialize(self._source, self.source_ref)
        return result


@dataclass(frozen=True, slots=True)
class TechnologyField:
    name: str
    occurrence: int
    operator: str
    value: RawNodeRef | None
    source_ref: SourceRef

    @property
    def raw_value(self) -> str | None:
        """Materialize the field value lazily; the adapter does not retain this copy."""

        return None if self.value is None else self.value.raw

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "occurrence": self.occurrence,
            "operator": self.operator,
            "value_source_ref": (
                None if self.value is None else self.value.source_ref.to_dict()
            ),
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class TechnologyPrerequisite:
    target_game_id: str
    source_ref: SourceRef
    _source: bytes = field(repr=False, compare=False, default=b"")

    @property
    def raw_value(self) -> str:
        return self.source_ref.raw_text(self._source)

    def to_dict(self, *, include_raw: bool = False) -> dict[str, object]:
        result: dict[str, object] = {
            "target_game_id": self.target_game_id,
            "source_ref": self.source_ref.to_dict(),
        }
        if include_raw:
            result["raw_value"] = self.raw_value
        return result


@dataclass(frozen=True, slots=True)
class TechnologyDiagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    source_ref: SourceRef
    origin: DiagnosticOrigin = "adapter"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source_ref": self.source_ref.to_dict(),
            "origin": self.origin,
        }


@dataclass(frozen=True, slots=True)
class TechnologyCandidate:
    game_id: str
    kind: Literal["technology"]
    items: tuple[RawNodeRef, ...]
    fields: tuple[TechnologyField, ...]
    prerequisites: tuple[TechnologyPrerequisite, ...]
    source_ref: SourceRef
    diagnostics: tuple[TechnologyDiagnostic, ...]
    resolution: CandidateResolution = "raw_definition"

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        _budget: _RawOutputBudget | None = None,
    ) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "kind": self.kind,
            "items": [
                item.to_dict(include_raw=include_raw, _budget=_budget)
                for item in self.items
            ],
            "fields": [field.to_dict() for field in self.fields],
            "prerequisites": [
                item.to_dict(include_raw=False) for item in self.prerequisites
            ],
            "source_ref": self.source_ref.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "resolution": self.resolution,
        }


@dataclass(frozen=True, slots=True)
class TechnologyAdaptResult:
    candidates: tuple[TechnologyCandidate, ...]
    diagnostics: tuple[TechnologyDiagnostic, ...]
    complete: bool

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        max_raw_bytes: int = DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES,
    ) -> dict[str, object]:
        if isinstance(max_raw_bytes, bool) or not isinstance(max_raw_bytes, int):
            raise TypeError("max_raw_bytes must be an integer")
        if max_raw_bytes <= 0:
            raise ValueError("max_raw_bytes must be positive")

        budget = _RawOutputBudget(max_raw_bytes) if include_raw else None
        return {
            "candidates": [
                item.to_dict(include_raw=include_raw, _budget=budget)
                for item in self.candidates
            ],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "complete": self.complete,
        }


def _source_ref(context: SourceContext, span: SourceSpan) -> SourceRef:
    return SourceRef(
        snapshot_id=context.snapshot_id,
        source_kind=context.source_kind,
        source_id=context.source_id,
        relative_path=context.relative_path,
        file_sha256=context.file_sha256,
        byte_start=span.byte_start,
        byte_end=span.byte_end,
        line_start=span.line_start,
        line_end=span.line_end,
    )


def _raw_node(
    node: AstNode,
    source: bytes,
    context: SourceContext,
) -> RawNodeRef:
    children: tuple[RawNodeRef, ...] = ()
    key: str | None = None
    operator: str | None = None

    if isinstance(node, PairNode):
        key = node.key_text
        operator = node.operator_text
        children = (
            ()
            if node.value is None
            else (_raw_node(node.value, source, context),)
        )
    elif isinstance(node, BlockNode):
        children = tuple(_raw_node(item, source, context) for item in node.items)

    return RawNodeRef(
        kind=node.kind,
        source_ref=_source_ref(context, node.span),
        key=key,
        operator=operator,
        children=children,
        _source=source,
    )


def _parse_diagnostic(
    diagnostic: ParseDiagnostic,
    context: SourceContext,
) -> TechnologyDiagnostic:
    return TechnologyDiagnostic(
        code=diagnostic.code,
        severity=diagnostic.severity,
        message=diagnostic.message,
        source_ref=_source_ref(context, diagnostic.span),
        origin=diagnostic.origin,
    )


def _overlaps(source_ref: SourceRef, span: SourceSpan) -> bool:
    if span.byte_start == span.byte_end:
        return source_ref.byte_start <= span.byte_start <= source_ref.byte_end
    return (
        source_ref.byte_start < span.byte_end
        and span.byte_start < source_ref.byte_end
    )


def _has_unclosed_block(node: AstNode) -> bool:
    if isinstance(node, BlockNode):
        return (not node.closed) or any(
            _has_unclosed_block(item) for item in node.items
        )
    if isinstance(node, PairNode) and node.value is not None:
        return _has_unclosed_block(node.value)
    return False


def _literal_prerequisite_id(node: ScalarNode) -> str | None:
    if node.token_kind == "identifier":
        return node.text if node.text else None
    if (
        node.token_kind == "string"
        and len(node.text) >= 2
        and node.text.startswith('"')
        and node.text.endswith('"')
    ):
        value = node.text[1:-1]
        return value if value else None
    return None


def _candidate_from_pair(
    pair: PairNode,
    source: bytes,
    context: SourceContext,
    parse_diagnostics: tuple[ParseDiagnostic, ...],
) -> TechnologyCandidate:
    assert isinstance(pair.value, BlockNode)

    candidate_ref = _source_ref(context, pair.span)
    candidate_parse_diagnostics = tuple(
        _parse_diagnostic(item, context)
        for item in parse_diagnostics
        if _overlaps(candidate_ref, item.span)
    )

    raw_items = tuple(
        _raw_node(item, source, context) for item in pair.value.items
    )
    fields: list[TechnologyField] = []
    prerequisites: list[TechnologyPrerequisite] = []
    diagnostics: list[TechnologyDiagnostic] = list(candidate_parse_diagnostics)
    occurrences: dict[str, int] = {}

    for item, raw_item in zip(pair.value.items, raw_items, strict=True):
        if isinstance(item, PairNode):
            occurrence = occurrences.get(item.key_text, 0) + 1
            occurrences[item.key_text] = occurrence
            value_ref = raw_item.children[0] if item.value is not None else None
            fields.append(
                TechnologyField(
                    name=item.key_text,
                    occurrence=occurrence,
                    operator=item.operator_text,
                    value=value_ref,
                    source_ref=_source_ref(context, item.span),
                )
            )

            if item.key_text != "prerequisites":
                continue

            if item.operator_kind != "assign":
                diagnostics.append(
                    TechnologyDiagnostic(
                        code="ADAPTER_UNSUPPORTED_PREREQUISITES_OPERATOR",
                        severity="warning",
                        message=(
                            "Prerequisites are extracted only from assignment "
                            "blocks; the raw field was preserved."
                        ),
                        source_ref=_source_ref(context, item.span),
                    )
                )
                continue

            if not isinstance(item.value, BlockNode):
                diagnostics.append(
                    TechnologyDiagnostic(
                        code="ADAPTER_UNSUPPORTED_PREREQUISITES",
                        severity="warning",
                        message=(
                            "Prerequisites assignment is not a block and was "
                            "preserved without inferred references."
                        ),
                        source_ref=_source_ref(context, item.span),
                    )
                )
                continue

            for prerequisite in item.value.items:
                if isinstance(prerequisite, ScalarNode):
                    target_game_id = _literal_prerequisite_id(prerequisite)
                    if target_game_id is not None:
                        prerequisites.append(
                            TechnologyPrerequisite(
                                target_game_id=target_game_id,
                                source_ref=_source_ref(
                                    context,
                                    prerequisite.span,
                                ),
                                _source=source,
                            )
                        )
                        continue

                diagnostics.append(
                    TechnologyDiagnostic(
                        code="ADAPTER_UNRESOLVED_PREREQUISITE",
                        severity="warning",
                        message=(
                            "Prerequisite is not a supported non-empty literal "
                            "ID and was preserved without inferred reference."
                        ),
                        source_ref=_source_ref(context, prerequisite.span),
                    )
                )

        elif isinstance(item, UnknownNode):
            diagnostics.append(
                TechnologyDiagnostic(
                    code="ADAPTER_UNKNOWN_ITEM",
                    severity="warning",
                    message=(
                        "Unknown technology item was preserved without "
                        "inferred semantics."
                    ),
                    source_ref=_source_ref(context, item.span),
                )
            )

    resolution: CandidateResolution = "raw_definition"
    if (
        any(item.severity == "error" for item in diagnostics)
        or _has_unclosed_block(pair.value)
        or any(
            item.code.startswith("ADAPTER_UNSUPPORTED_")
            or item.code == "ADAPTER_UNRESOLVED_PREREQUISITE"
            for item in diagnostics
        )
    ):
        resolution = "partial"

    return TechnologyCandidate(
        game_id=pair.key_text,
        kind="technology",
        items=raw_items,
        fields=tuple(fields),
        prerequisites=tuple(prerequisites),
        source_ref=candidate_ref,
        diagnostics=tuple(diagnostics),
        resolution=resolution,
    )


def adapt_technologies(
    parsed: ParseResult,
    source: bytes,
    context: SourceContext,
) -> TechnologyAdaptResult:
    """Adapt parsed technology definitions without discarding parse state."""

    candidates: list[TechnologyCandidate] = []
    parse_diagnostics = tuple(parsed.diagnostics)
    diagnostics: list[TechnologyDiagnostic] = [
        _parse_diagnostic(item, context) for item in parse_diagnostics
    ]

    for item in parsed.document.items:
        if (
            isinstance(item, PairNode)
            and item.key_kind == "identifier"
            and item.operator_kind == "assign"
            and isinstance(item.value, BlockNode)
        ):
            candidate = _candidate_from_pair(
                item,
                source,
                context,
                parse_diagnostics,
            )
            candidates.append(candidate)
            diagnostics.extend(
                item
                for item in candidate.diagnostics
                if item.origin == "adapter"
            )
        elif isinstance(item, UnknownNode):
            diagnostics.append(
                TechnologyDiagnostic(
                    code="ADAPTER_TOP_LEVEL_UNKNOWN",
                    severity="warning",
                    message=(
                        "Unknown top-level syntax was preserved and not "
                        "adapted as a technology."
                    ),
                    source_ref=_source_ref(context, item.span),
                )
            )

    complete = parsed.ok and all(
        item.resolution == "raw_definition" for item in candidates
    )
    return TechnologyAdaptResult(
        candidates=tuple(candidates),
        diagnostics=tuple(diagnostics),
        complete=complete,
    )
