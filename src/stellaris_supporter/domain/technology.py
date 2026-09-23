"""Loss-preserving technology adapter for ordered script AST."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from stellaris_supporter.parsing import (
    AstNode,
    BlockNode,
    DocumentNode,
    PairNode,
    ScalarNode,
    SourceSpan,
    UnknownNode,
)

SourceKind = Literal["synthetic", "base", "mod", "official", "wiki", "community"]
DiagnosticSeverity = Literal["info", "warning", "error"]


@dataclass(frozen=True)
class SourceContext:
    snapshot_id: str
    source_kind: SourceKind
    source_id: str
    relative_path: str
    file_sha256: str


@dataclass(frozen=True)
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


@dataclass(frozen=True)
class RawNodeRef:
    kind: str
    raw: str
    source_ref: SourceRef
    key: str | None = None
    operator: str | None = None
    children: tuple[RawNodeRef, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "kind": self.kind,
            "raw": self.raw,
            "source_ref": self.source_ref.to_dict(),
            "key": self.key,
            "operator": self.operator,
            "children": [item.to_dict() for item in self.children],
        }


@dataclass(frozen=True)
class TechnologyField:
    name: str
    occurrence: int
    operator: str
    raw_value: str | None
    value: RawNodeRef | None
    source_ref: SourceRef

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "occurrence": self.occurrence,
            "operator": self.operator,
            "raw_value": self.raw_value,
            "value": None if self.value is None else self.value.to_dict(),
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True)
class TechnologyPrerequisite:
    target_game_id: str
    raw_value: str
    source_ref: SourceRef

    def to_dict(self) -> dict[str, object]:
        return {
            "target_game_id": self.target_game_id,
            "raw_value": self.raw_value,
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True)
class TechnologyDiagnostic:
    code: str
    severity: DiagnosticSeverity
    message: str
    source_ref: SourceRef

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True)
class TechnologyCandidate:
    game_id: str
    kind: Literal["technology"]
    items: tuple[RawNodeRef, ...]
    fields: tuple[TechnologyField, ...]
    prerequisites: tuple[TechnologyPrerequisite, ...]
    source_ref: SourceRef
    diagnostics: tuple[TechnologyDiagnostic, ...]
    resolution: Literal["raw_definition"] = "raw_definition"

    def to_dict(self) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "kind": self.kind,
            "items": [item.to_dict() for item in self.items],
            "fields": [field.to_dict() for field in self.fields],
            "prerequisites": [item.to_dict() for item in self.prerequisites],
            "source_ref": self.source_ref.to_dict(),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "resolution": self.resolution,
        }


@dataclass(frozen=True)
class TechnologyAdaptResult:
    candidates: tuple[TechnologyCandidate, ...]
    diagnostics: tuple[TechnologyDiagnostic, ...]

    @property
    def ok(self) -> bool:
        return not any(item.severity == "error" for item in self.diagnostics)

    def to_dict(self) -> dict[str, object]:
        return {
            "candidates": [item.to_dict() for item in self.candidates],
            "diagnostics": [item.to_dict() for item in self.diagnostics],
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


def _raw_text(source: bytes, span: SourceSpan) -> str:
    return source[span.byte_start : span.byte_end].decode("utf-8", errors="strict")


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
        raw=_raw_text(source, node.span),
        source_ref=_source_ref(context, node.span),
        key=key,
        operator=operator,
        children=children,
    )


def _scalar_game_id(node: ScalarNode) -> str:
    if (
        node.token_kind == "string"
        and len(node.text) >= 2
        and node.text.startswith('"')
        and node.text.endswith('"')
    ):
        return node.text[1:-1]
    return node.text


def _candidate_from_pair(
    pair: PairNode,
    source: bytes,
    context: SourceContext,
) -> TechnologyCandidate:
    assert isinstance(pair.value, BlockNode)

    fields: list[TechnologyField] = []
    prerequisites: list[TechnologyPrerequisite] = []
    diagnostics: list[TechnologyDiagnostic] = []
    occurrences: dict[str, int] = {}

    for item in pair.value.items:
        if isinstance(item, PairNode):
            occurrence = occurrences.get(item.key_text, 0) + 1
            occurrences[item.key_text] = occurrence
            raw_value = (
                None
                if item.value is None
                else _raw_text(source, item.value.span)
            )
            field = TechnologyField(
                name=item.key_text,
                occurrence=occurrence,
                operator=item.operator_text,
                raw_value=raw_value,
                value=(
                    None
                    if item.value is None
                    else _raw_node(item.value, source, context)
                ),
                source_ref=_source_ref(context, item.span),
            )
            fields.append(field)

            if item.key_text == "prerequisites":
                if isinstance(item.value, BlockNode):
                    for prerequisite in item.value.items:
                        if isinstance(prerequisite, ScalarNode):
                            prerequisites.append(
                                TechnologyPrerequisite(
                                    target_game_id=_scalar_game_id(prerequisite),
                                    raw_value=_raw_text(source, prerequisite.span),
                                    source_ref=_source_ref(
                                        context,
                                        prerequisite.span,
                                    ),
                                )
                            )
                        else:
                            diagnostics.append(
                                TechnologyDiagnostic(
                                    code="ADAPTER_UNSUPPORTED_PREREQUISITE",
                                    severity="warning",
                                    message=(
                                        "Non-scalar prerequisite was preserved "
                                        "without inferred semantics."
                                    ),
                                    source_ref=_source_ref(
                                        context,
                                        prerequisite.span,
                                    ),
                                )
                            )
                else:
                    diagnostics.append(
                        TechnologyDiagnostic(
                            code="ADAPTER_UNSUPPORTED_PREREQUISITES",
                            severity="warning",
                            message=(
                                "Prerequisites value is not a block and was "
                                "preserved without inferred semantics."
                            ),
                            source_ref=_source_ref(context, item.span),
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

    return TechnologyCandidate(
        game_id=pair.key_text,
        kind="technology",
        items=tuple(_raw_node(item, source, context) for item in pair.value.items),
        fields=tuple(fields),
        prerequisites=tuple(prerequisites),
        source_ref=_source_ref(context, pair.span),
        diagnostics=tuple(diagnostics),
    )


def adapt_technologies(
    document: DocumentNode,
    source: bytes,
    context: SourceContext,
) -> TechnologyAdaptResult:
    """Adapt top-level identifier assignments with block values to technologies."""

    candidates: list[TechnologyCandidate] = []
    diagnostics: list[TechnologyDiagnostic] = []

    for item in document.items:
        if (
            isinstance(item, PairNode)
            and item.key_kind == "identifier"
            and item.operator_kind == "assign"
            and isinstance(item.value, BlockNode)
        ):
            candidate = _candidate_from_pair(item, source, context)
            candidates.append(candidate)
            diagnostics.extend(candidate.diagnostics)
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

    return TechnologyAdaptResult(
        candidates=tuple(candidates),
        diagnostics=tuple(diagnostics),
    )
