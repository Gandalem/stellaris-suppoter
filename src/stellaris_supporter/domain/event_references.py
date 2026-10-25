"""Ordered literal event calls; scopes and conditions remain source evidence."""
from __future__ import annotations

from dataclasses import dataclass

from stellaris_supporter.domain.generic import DomainCandidate, _literal
from stellaris_supporter.domain.technology import SourceContext, SourceRef, _source_ref
from stellaris_supporter.parsing import BlockNode, PairNode, ParseResult
from stellaris_supporter.storage.identity import SnapshotError, storage_json

EXTRACTOR_VERSION = "literal-event-refs-1"
MAX_DEFINITION_REFERENCES = 1024
MAX_REFERENCE_RAW_BYTES = 1024 * 1024
_EVENT_TYPES = frozenset({"country_event", "planet_event"})
_CONTAINERS = frozenset({"if", "else_if", "else", "hidden_effect"})


@dataclass(frozen=True, slots=True)
class StaticReference:
    target_game_id: str
    source_ref: SourceRef
    conditions_raw: str | None = None

    def to_dict(self) -> dict:
        return {"target_game_id": self.target_game_id,
                "source_ref": self.source_ref.to_dict(),
                "conditions_raw": self.conditions_raw}


@dataclass(frozen=True, slots=True)
class EventReferenceRecord:
    candidate: DomainCandidate
    prerequisites: tuple[StaticReference, ...]
    coverage_complete: bool
    coverage_reasons: tuple[str, ...]

    @property
    def game_id(self):
        return self.candidate.game_id

    @property
    def kind(self):
        return self.candidate.kind

    @property
    def source_ref(self):
        return self.candidate.source_ref

    @property
    def items(self):
        return self.candidate.items

    @property
    def resolution(self):
        return self.candidate.resolution if self.coverage_complete else "partial"

    def to_dict(self, *, include_raw=False) -> dict:
        return {**self.candidate.to_dict(include_raw=include_raw),
                "reference_extractor": EXTRACTOR_VERSION,
                "references": [r.to_dict() for r in self.prerequisites],
                "reference_coverage": {"complete": self.coverage_complete,
                                       "reasons": list(self.coverage_reasons)}}


def extract_event_references(candidate: DomainCandidate, parsed: ParseResult,
                             source: bytes, context: SourceContext, *, _root=None) -> EventReferenceRecord:
    """Use a whole-file canonical AST; never interpret strings or trigger blocks."""
    roots = [node for node in ((_root,) if _root is not None else parsed.document.items) if isinstance(node, PairNode)
             and node.key_text in _EVENT_TYPES and node.key_kind == "identifier"
             and node.operator_kind == "assign"
             and _source_ref(context, node.span) == candidate.source_ref]
    if len(roots) != 1 or not isinstance(roots[0].value, BlockNode):
        raise SnapshotError("SOURCE_CHANGED", "Event definition is not a top-level source node.")
    if candidate.source_ref.byte_end - candidate.source_ref.byte_start > MAX_REFERENCE_RAW_BYTES:
        raise SnapshotError("LIMIT_EXCEEDED", "Event definition byte budget exceeded.")
    references: list[StaticReference] = []
    raw_bytes = 0
    reasons: list[str] = []

    def incomplete(reason):
        if reason not in reasons:
            reasons.append(reason)

    def walk(block: BlockNode, guards: tuple[PairNode, ...]):
        nonlocal raw_bytes
        for node in block.items:
            if not isinstance(node, PairNode) or node.key_kind != "identifier":
                incomplete("unsupported_effect_structure")
                continue
            if node.operator_kind != "assign":
                incomplete("unsupported_effect_operator")
                continue
            if node.key_text == "limit":
                continue
            if node.key_text in _EVENT_TYPES:
                if not isinstance(node.value, BlockNode):
                    incomplete("nonliteral_event_call")
                    continue
                ids = [n for n in node.value.items
                       if isinstance(n, PairNode) and n.key_text == "id"]
                target = (_literal(ids[0].value) if len(ids) == 1
                          and ids[0].operator_kind == "assign"
                          and ids[0].key_kind == "identifier" else None)
                if target is None or not target or len(target) > 512:
                    incomplete("nonliteral_event_id")
                    continue
                if len(references) >= MAX_DEFINITION_REFERENCES:
                    raise SnapshotError("LIMIT_EXCEEDED", "Event reference count exceeded.")
                # Preserve wrappers/limits as raw evidence without asserting scope.
                raw_charge = sum(g.span.byte_end - g.span.byte_start for g in guards)
                if raw_bytes + raw_charge > MAX_REFERENCE_RAW_BYTES:
                    raise SnapshotError("LIMIT_EXCEEDED", "Event guard byte budget exceeded.")
                evidence = [{"name": g.key_text,
                             "source_ref": _source_ref(context, g.span).to_dict(),
                             "raw": g.raw_bytes(source).decode("utf-8")} for g in guards]
                encoded = (storage_json(evidence, max_bytes=MAX_REFERENCE_RAW_BYTES - raw_bytes)
                           if evidence else None)
                conditions = None if encoded is None else encoded.decode("utf-8")
                raw_bytes += 0 if encoded is None else len(encoded)
                references.append(StaticReference(target, _source_ref(context, ids[0].value.span), conditions))
            elif node.key_text in _CONTAINERS:
                if isinstance(node.value, BlockNode):
                    walk(node.value, (*guards, node))
                else:
                    incomplete("unsupported_effect_structure")
            elif isinstance(node.value, BlockNode):
                # Unknown scopes can contain calls; coverage must remain partial.
                incomplete("unsupported_effect_scope")

    for node in roots[0].value.items:
        if not isinstance(node, PairNode):
            incomplete("unsupported_definition_structure")
        elif node.key_text in {"immediate", "option"}:
            if (node.key_kind == "identifier" and node.operator_kind == "assign"
                    and isinstance(node.value, BlockNode)):
                walk(node.value, (node,) if node.key_text == "option" else ())
            else:
                incomplete("unsupported_effect_structure")
        elif node.key_text in _EVENT_TYPES or node.key_text in _CONTAINERS:
            incomplete("unsupported_effect_location")
    return EventReferenceRecord(candidate, tuple(references), not reasons, tuple(reasons))


def extract_event_records(candidates, parsed: ParseResult, source: bytes,
                          context: SourceContext) -> tuple[EventReferenceRecord, ...]:
    roots = {(node.span.byte_start, node.span.byte_end): node
             for node in parsed.document.items if isinstance(node, PairNode)}
    return tuple(extract_event_references(c, parsed, source, context,
                 _root=roots.get((c.source_ref.byte_start, c.source_ref.byte_end)))
                 for c in candidates)
