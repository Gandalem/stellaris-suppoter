"""Bounded, source-grounded adapters for explicitly registered non-technology fixtures.

Only four authored synthetic grammars are supported here. Registry paths are
investigation candidates, not claims of compatibility with an installed game.
The existing technology/SQLite/search/CLI contracts are intentionally unchanged.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import PurePosixPath
from typing import Literal

from stellaris_supporter.domain.technology import (
    DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES,
    RawNodeRef,
    SourceContext,
    SourceRef,
    _RawOutputBudget,
    _raw_node,
    _source_ref,
)
from stellaris_supporter.parsing import (
    AstNode,
    BlockNode,
    PairNode,
    ParseResult,
    ScalarNode,
    UnknownNode,
    parse_bytes,
)
from stellaris_supporter.parsing.lexer import (
    DEFAULT_LEXER_MAX_BYTES,
    DEFAULT_LEXER_MAX_TOKENS,
)
from stellaris_supporter.parsing.parser import (
    DEFAULT_PARSER_MAX_DIAGNOSTICS,
    DEFAULT_PARSER_MAX_NODES,
)

DomainKind = Literal["component_template", "building", "district", "pop_job"]
IdRule = Literal["root_identifier", "literal_key_field"]
Resolution = Literal["raw_definition", "partial", "ambiguous"]
SupportLevel = Literal["synthetic_static", "partial", "unsupported"]

_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_HARD_PARSE_CODES = frozenset(
    {"LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT", "PARSE_DIAGNOSTIC_LIMIT"}
)


@dataclass(frozen=True, slots=True)
class DomainSpec:
    kind: DomainKind
    path_prefix: str
    id_rule: IdRule
    wrapper: str | None = None
    condition_fields: tuple[str, ...] = ()
    localisation_rule: Literal["id_key"] = "id_key"


# These are opt-in synthetic grammars. Never silently infer paths or ID rules.
DOMAIN_REGISTRY: dict[str, DomainSpec] = {
    "component_template": DomainSpec(
        "component_template",
        "common/component_templates/",
        "literal_key_field",
        wrapper="component_template",
        condition_fields=("potential", "allow", "restriction", "prerequisites"),
    ),
    "building": DomainSpec(
        "building",
        "common/buildings/",
        "root_identifier",
        condition_fields=("potential", "allow", "prerequisites", "trigger"),
    ),
    "district": DomainSpec(
        "district",
        "common/districts/",
        "root_identifier",
        condition_fields=("potential", "allow", "prerequisites", "can_build"),
    ),
    "pop_job": DomainSpec(
        "pop_job",
        "common/pop_jobs/",
        "root_identifier",
        condition_fields=("possible", "potential", "weight", "trigger"),
    ),
}


@dataclass(frozen=True, slots=True)
class DomainDiagnostic:
    code: str
    severity: Literal["info", "warning", "error"]
    message: str
    source_ref: SourceRef
    origin: Literal["adapter", "parser", "lexer"] = "adapter"

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source_ref": self.source_ref.to_dict(),
            "origin": self.origin,
        }


@dataclass(frozen=True, slots=True)
class DomainField:
    name: str
    occurrence: int
    operator: str
    value: RawNodeRef | None
    source_ref: SourceRef

    @property
    def raw_value(self) -> str | None:
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
class DomainCandidate:
    game_id: str | None
    kind: DomainKind
    definition_occurrence: int
    items: tuple[RawNodeRef, ...]
    fields: tuple[DomainField, ...]
    conditions: tuple[DomainField, ...]
    source_ref: SourceRef
    id_source_ref: SourceRef | None
    diagnostics: tuple[DomainDiagnostic, ...]
    resolution: Resolution
    support_level: SupportLevel
    localisation_key: str | None

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        _budget: _RawOutputBudget | None = None,
    ) -> dict[str, object]:
        return {
            "game_id": self.game_id,
            "kind": self.kind,
            "definition_occurrence": self.definition_occurrence,
            "items": [
                node.to_dict(include_raw=include_raw, _budget=_budget)
                for node in self.items
            ],
            "fields": [item.to_dict() for item in self.fields],
            "conditions": [item.to_dict() for item in self.conditions],
            "source_ref": self.source_ref.to_dict(),
            "id_source_ref": (
                None if self.id_source_ref is None else self.id_source_ref.to_dict()
            ),
            "diagnostics": [item.to_dict() for item in self.diagnostics],
            "resolution": self.resolution,
            "support_level": self.support_level,
            "localisation_key": self.localisation_key,
        }


@dataclass(frozen=True, slots=True)
class DomainAdaptResult:
    candidates: tuple[DomainCandidate, ...]
    diagnostics: tuple[DomainDiagnostic, ...]
    unhandled: tuple[RawNodeRef, ...]
    complete: bool
    blocked: bool = False

    @property
    def ok(self) -> bool:
        return not self.blocked and not any(
            d.severity == "error" for d in self.diagnostics
        )

    def to_dict(
        self,
        *,
        include_raw: bool = False,
        max_raw_bytes: int = DEFAULT_ADAPTER_MAX_RAW_OUTPUT_BYTES,
    ) -> dict[str, object]:
        if type(max_raw_bytes) is not int:
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
            "unhandled": [
                item.to_dict(include_raw=include_raw, _budget=budget)
                for item in self.unhandled
            ],
            "complete": self.complete,
            "blocked": self.blocked,
        }


@dataclass(frozen=True, slots=True)
class DomainConflict:
    kind: DomainKind
    game_id: str
    definition_source_refs: tuple[SourceRef, ...]


@dataclass(frozen=True, slots=True)
class DomainLocalisedName:
    candidate: DomainCandidate
    localisation: object


def _checked_span(node: AstNode, source: bytes, parent: AstNode | None) -> None:
    """Reject foreign/moved AST spans before making them citation evidence."""

    span = node.span
    if not 0 <= span.byte_start <= span.byte_end <= len(source):
        raise ValueError("AST span is outside verified source bytes")
    if parent is not None and not (
        parent.span.byte_start <= span.byte_start
        and span.byte_end <= parent.span.byte_end
    ):
        raise ValueError("AST child span escapes parent definition")

    if isinstance(node, ScalarNode):
        if source[span.byte_start:span.byte_end].decode("utf-8") != node.text:
            raise ValueError("AST scalar text does not match source bytes")
    elif isinstance(node, PairNode):
        if not (
            span.byte_start == node.key_span.byte_start
            and node.key_span.byte_end <= node.operator_span.byte_start
            and node.operator_span.byte_end <= span.byte_end
        ):
            raise ValueError("AST pair key/operator spans are not ordered")
        if source[node.key_span.byte_start:node.key_span.byte_end].decode(
            "utf-8"
        ) != node.key_text:
            raise ValueError("AST pair key does not match source bytes")
        if source[node.operator_span.byte_start:node.operator_span.byte_end].decode(
            "utf-8"
        ) != node.operator_text:
            raise ValueError("AST pair operator does not match source bytes")
        if node.value is not None:
            if node.value.span.byte_start < node.operator_span.byte_end:
                raise ValueError("AST pair value precedes operator")
            _checked_span(node.value, source, node)
    elif isinstance(node, BlockNode):
        if source[span.byte_start:span.byte_start + 1] != b"{":
            raise ValueError("AST block opening does not match source bytes")
        if node.closed and source[span.byte_end - 1:span.byte_end] != b"}":
            raise ValueError("AST block closing does not match source bytes")
        previous = span.byte_start
        for child in node.items:
            if child.span.byte_start < previous:
                raise ValueError("AST block items are out of order")
            _checked_span(child, source, node)
            previous = child.span.byte_end
    elif isinstance(node, UnknownNode):
        for token in node.tokens:
            if not (span.byte_start <= token.span.byte_start
                    <= token.span.byte_end <= span.byte_end):
                raise ValueError("Unknown-token span is not in its raw node")
            if source[token.span.byte_start:token.span.byte_end].decode(
                "utf-8"
            ) != token.text:
                raise ValueError("Unknown token does not match source bytes")


def _validate_inputs(
    parsed: ParseResult,
    source: bytes,
    context: SourceContext,
    spec: DomainSpec,
) -> None:
    if not isinstance(source, bytes):
        raise TypeError("source must be bytes")
    if len(source) > DEFAULT_LEXER_MAX_BYTES:
        raise ValueError("LIMIT_EXCEEDED: input exceeds the per-file byte budget")
    if not isinstance(context, SourceContext):
        raise TypeError("context must be SourceContext")
    if not isinstance(context.snapshot_id, str) or not context.snapshot_id:
        raise ValueError("source snapshot_id must be non-empty")
    if not isinstance(context.source_id, str) or not context.source_id:
        raise ValueError("source_id must be non-empty")
    if context.source_kind not in (
        "synthetic", "base", "mod", "official", "wiki", "community"
    ):
        raise ValueError("unrecognised source_kind")
    path = context.relative_path
    if not isinstance(path, str) or (
        path != PurePosixPath(path).as_posix()
        or path.startswith("/")
        or "\\" in path
        or any(part in ("..", ".", "") for part in path.split("/"))
        or not path.startswith(spec.path_prefix)
        or not path.endswith(".txt")
    ):
        raise ValueError("source path is not registered for this domain")
    if (
        not isinstance(context.file_sha256, str)
        or context.file_sha256 != hashlib.sha256(source).hexdigest()
    ):
        raise ValueError("SOURCE_CHANGED: source hash does not match context")
    if not isinstance(parsed, ParseResult):
        raise TypeError("parsed must be ParseResult")
    if (
        parsed.node_count > DEFAULT_PARSER_MAX_NODES
        or len(parsed.tokens) > DEFAULT_LEXER_MAX_TOKENS
        or len(parsed.diagnostics) > DEFAULT_PARSER_MAX_DIAGNOSTICS
    ):
        raise ValueError("LIMIT_EXCEEDED: parsed resource budget exceeded")
    for token in parsed.tokens:
        span = token.span
        if not (0 <= span.byte_start <= span.byte_end <= len(source)):
            raise ValueError("Parser token span outside verified file")
        if source[span.byte_start:span.byte_end].decode("utf-8") != token.text:
            raise ValueError("Parser token text does not match source file")
    previous = 0
    for node in parsed.document.items:
        if node.span.byte_start < previous:
            raise ValueError("Document items out of source order")
        _checked_span(node, source, None)
        previous = node.span.byte_end


def _literal(node: AstNode | None) -> str | None:
    if not isinstance(node, ScalarNode):
        return None
    if node.token_kind == "identifier":
        value = node.text
    elif (
        node.token_kind == "string"
        and len(node.text) >= 2
        and node.text.startswith('"')
        and node.text.endswith('"')
        and "\\" not in node.text
    ):
        value = node.text[1:-1]
    else:
        return None
    return value if _ID.fullmatch(value) else None


def _unknown_nodes(node: AstNode):
    if isinstance(node, UnknownNode):
        yield node
    elif isinstance(node, BlockNode):
        for child in node.items:
            yield from _unknown_nodes(child)
    elif isinstance(node, PairNode) and node.value is not None:
        yield from _unknown_nodes(node.value)


def _make_candidate(
    pair: PairNode,
    spec: DomainSpec,
    source: bytes,
    context: SourceContext,
    parse_diagnostics: tuple[DomainDiagnostic, ...],
) -> DomainCandidate:
    ref = _source_ref(context, pair.span)
    raw_items = (
        tuple(_raw_node(item, source, context) for item in pair.value.items)
        if isinstance(pair.value, BlockNode) else ()
    )
    fields: list[DomainField] = []
    diagnostics = [
        d for d in parse_diagnostics
        if (
            d.source_ref.byte_start < ref.byte_end
            and d.source_ref.byte_end > ref.byte_start
        ) or (
            d.source_ref.byte_start == d.source_ref.byte_end
            and ref.byte_start <= d.source_ref.byte_start <= ref.byte_end
        )
    ]
    occurrences: dict[str, int] = {}
    if isinstance(pair.value, BlockNode):
        for item, raw in zip(pair.value.items, raw_items, strict=True):
            if not isinstance(item, PairNode):
                continue
            occurrences[item.key_text] = occurrences.get(item.key_text, 0) + 1
            fields.append(DomainField(
                item.key_text,
                occurrences[item.key_text],
                item.operator_text,
                raw.children[0] if item.value is not None else None,
                _source_ref(context, item.span),
            ))
            if item.operator_kind != "assign":
                diagnostics.append(DomainDiagnostic(
                    "DOMAIN_UNSUPPORTED_OPERATOR", "warning",
                    "Non-assignment field retained without evaluated semantics.",
                    _source_ref(context, item.span),
                ))
        for node in _unknown_nodes(pair.value):
            diagnostics.append(DomainDiagnostic(
                "DOMAIN_UNKNOWN_STRUCTURE", "warning",
                "Unsupported nested syntax retained as raw AST.",
                _source_ref(context, node.span),
            ))
    else:
        diagnostics.append(DomainDiagnostic(
            "DOMAIN_INVALID_DEFINITION", "warning",
            "Domain definition is not a block; raw pair retained.",
            ref,
        ))

    game_id: str | None = None
    id_ref: SourceRef | None = None
    if spec.id_rule == "root_identifier":
        game_id = _literal(ScalarNode(
            "scalar", pair.key_kind, pair.key_text, pair.key_span
        ))
        if game_id is not None:
            id_ref = _source_ref(context, pair.key_span)
    else:
        keys = [item for item in fields if item.name == "key"]
        if len(keys) == 1 and keys[0].operator == "=":
            # ID is the *value* of the key field, not the wrapper name.
            id_node = next(
                item.value for item in pair.value.items
                if isinstance(item, PairNode) and item.key_text == "key"
            ) if isinstance(pair.value, BlockNode) else None
            game_id = _literal(id_node)
            if game_id is not None and id_node is not None:
                id_ref = _source_ref(context, id_node.span)

    if game_id is None:
        diagnostics.append(DomainDiagnostic(
            "DOMAIN_UNRESOLVED_ID", "warning",
            "A unique non-dynamic literal ID was not established.",
            ref,
        ))
    if isinstance(pair.value, BlockNode) and not pair.value.closed:
        diagnostics.append(DomainDiagnostic(
            "DOMAIN_UNCLOSED_BLOCK", "warning",
            "Unclosed definition cannot be treated as fully supported.",
            ref,
        ))

    partial = bool(diagnostics)
    conditions = tuple(f for f in fields if f.name in spec.condition_fields)
    return DomainCandidate(
        game_id=game_id,
        kind=spec.kind,
        definition_occurrence=1,
        items=raw_items,
        fields=tuple(fields),
        conditions=conditions,
        source_ref=ref,
        id_source_ref=id_ref,
        diagnostics=tuple(diagnostics),
        resolution="partial" if partial else "raw_definition",
        support_level="partial" if partial else "synthetic_static",
        localisation_key=game_id,
    )


def adapt_domain(
    parsed: ParseResult,
    source: bytes,
    context: SourceContext,
    kind: DomainKind,
) -> DomainAdaptResult:
    """Extract raw definitions without applying game/mod priority or calculations."""

    spec = DOMAIN_REGISTRY.get(kind)
    if spec is None:
        raise ValueError("unregistered domain adapter")
    _validate_inputs(parsed, source, context, spec)
    parse_diagnostics = tuple(
        DomainDiagnostic(d.code, d.severity, d.message,
                         _source_ref(context, d.span), d.origin)
        for d in parsed.diagnostics
    )
    if any(d.code in _HARD_PARSE_CODES for d in parse_diagnostics):
        # A resource stop is never a partial candidate that callers may activate.
        return DomainAdaptResult((), parse_diagnostics, (), False, blocked=True)

    candidates: list[DomainCandidate] = []
    diagnostics: list[DomainDiagnostic] = list(parse_diagnostics)
    unhandled: list[RawNodeRef] = []
    occurrences: dict[str, int] = {}
    for node in parsed.document.items:
        if (
            isinstance(node, PairNode)
            and node.key_kind == "identifier"
            and node.operator_kind == "assign"
            and (
                (spec.id_rule == "root_identifier" and _ID.fullmatch(node.key_text))
                or (spec.id_rule == "literal_key_field" and node.key_text == spec.wrapper)
            )
        ):
            candidate = _make_candidate(
                node, spec, source, context, parse_diagnostics
            )
            if candidate.game_id is not None:
                from dataclasses import replace

                occurrences[candidate.game_id] = (
                    occurrences.get(candidate.game_id, 0) + 1
                )
                candidate = replace(
                    candidate,
                    definition_occurrence=occurrences[candidate.game_id],
                )
            candidates.append(candidate)
            diagnostics.extend(d for d in candidate.diagnostics if d.origin == "adapter")
        else:
            unhandled.append(_raw_node(node, source, context))
            diagnostics.append(DomainDiagnostic(
                "DOMAIN_UNSUPPORTED_TOP_LEVEL", "warning",
                "Unrecognised top-level definition or directive was retained.",
                _source_ref(context, node.span),
            ))
        if len(diagnostics) >= DEFAULT_PARSER_MAX_DIAGNOSTICS:
            hard = DomainDiagnostic(
                "LIMIT_EXCEEDED", "error",
                "Domain diagnostic budget exhausted; no candidates accepted.",
                _source_ref(context, node.span),
            )
            return DomainAdaptResult((), (hard,), (), False, blocked=True)

    # Duplicates are ambiguous and never resolved by input/file order.
    if occurrences:
        from dataclasses import replace

        candidates = [
            replace(c, resolution="ambiguous", support_level="partial")
            if c.game_id is not None and occurrences[c.game_id] > 1
            else c for c in candidates
        ]
        for c in candidates:
            if c.resolution == "ambiguous":
                diagnostics.append(DomainDiagnostic(
                    "DOMAIN_DUPLICATE_ID", "warning",
                    "Multiple definitions share this ID; no precedence inferred.",
                    c.source_ref,
                ))
                if len(diagnostics) >= DEFAULT_PARSER_MAX_DIAGNOSTICS:
                    return DomainAdaptResult((), (
                        DomainDiagnostic(
                            "LIMIT_EXCEEDED", "error",
                            "Domain diagnostic budget exhausted.",
                            c.source_ref,
                        ),
                    ), (), False, blocked=True)
    return DomainAdaptResult(
        tuple(candidates),
        tuple(diagnostics),
        tuple(unhandled),
        parsed.ok and not unhandled and all(
            c.resolution == "raw_definition" for c in candidates
        ),
    )


def find_domain_collisions(
    candidates: tuple[DomainCandidate, ...],
) -> tuple[DomainConflict, ...]:
    """Group same-snapshot, same-kind IDs, retaining all definition occurrences."""

    snapshots = {c.source_ref.snapshot_id for c in candidates}
    if len(snapshots) > 1:
        raise ValueError("Cannot combine candidates across snapshots")
    grouped: dict[tuple[DomainKind, str], list[SourceRef]] = {}
    for candidate in candidates:
        if candidate.game_id is not None:
            grouped.setdefault(
                (candidate.kind, candidate.game_id), []
            ).append(candidate.source_ref)
    return tuple(
        DomainConflict(kind, game_id, tuple(refs))
        for (kind, game_id), refs in grouped.items() if len(refs) > 1
    )


def verify_domain_candidate(
    candidate: DomainCandidate,
    source: bytes,
    context: SourceContext,
) -> bool:
    """Fail closed on modified IDs, kinds, spans, occurrences or source hashes."""

    try:
        parsed = parse_bytes(source)
        rebuilt = adapt_domain(parsed, source, context, candidate.kind)
    except (TypeError, ValueError, UnicodeError):
        return False
    for expected in rebuilt.candidates:
        if expected != candidate:
            continue
        # RawNodeRef excludes its backing bytes from structural equality.
        def source_matches(node: RawNodeRef) -> bool:
            return (
                node.raw_bytes() == node.source_ref.raw_bytes(source)
                and all(source_matches(child) for child in node.children)
            )
        return all(source_matches(item) for item in candidate.items)
    return False


def resolve_domain_name(
    candidate: DomainCandidate,
    catalog: object,
    requested_language: str = "korean",
    **limits: int,
) -> DomainLocalisedName:
    """Explicit synthetic game-ID key mapping, with existing resolver evidence."""

    from stellaris_supporter.localisation.resolver import (
        LocalisationCatalog,
        resolve_localisation,
    )

    if not isinstance(catalog, LocalisationCatalog):
        raise TypeError("catalog must be LocalisationCatalog")
    if catalog.snapshot_id is not None and (
        candidate.source_ref.snapshot_id != catalog.snapshot_id
    ):
        raise ValueError("Domain and localisation snapshots do not match")
    if candidate.localisation_key is None:
        raise ValueError("Domain has no verified static localisation key")
    result = resolve_localisation(
        catalog, candidate.localisation_key, requested_language, **limits
    )
    return DomainLocalisedName(candidate, result)
