"""Bounded, source-grounded adapters for explicitly registered non-technology fixtures.

Only eleven opt-in authored synthetic grammars are supported here. Registry paths are
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
    _raw_node,
    _RawOutputBudget,
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

DomainKind = Literal[
    "component_template", "building", "district", "pop_job",
    "trait", "government", "civic", "origin",
    "tradition", "ascension_perk", "event",
]
IdRule = Literal[
    "root_identifier", "nested_identifier", "nested_id_field",
    "literal_key_field", "literal_id_field",
]
Resolution = Literal["raw_definition", "partial", "ambiguous"]
SupportLevel = Literal["synthetic_static", "partial", "unsupported"]

_ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_HARD_PARSE_CODES = frozenset(
    {
        "ENCODING_ERROR",
        "LIMIT_EXCEEDED",
        "PARSE_DEPTH_LIMIT",
        "PARSE_NODE_LIMIT",
        "PARSE_DIAGNOSTIC_LIMIT",
    }
)


@dataclass(frozen=True, slots=True)
class DomainSpec:
    kind: DomainKind
    path_prefix: str
    id_rule: IdRule
    wrapper: str | None = None
    condition_fields: tuple[str, ...] = ()
    localisation_rule: Literal["id_key", "name_field", "title_field"] = "id_key"
    flat_files_only: bool = False


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
    "trait": DomainSpec(
        "trait",
        "common/traits/",
        "root_identifier",
        condition_fields=("potential", "allow", "species_potential"),
    ),
    "government": DomainSpec(
        "government",
        "common/governments/",
        "nested_identifier",
        wrapper="governments",
        condition_fields=("potential", "allow", "possible"),
        localisation_rule="name_field",
        flat_files_only=True,
    ),
    "civic": DomainSpec(
        "civic",
        "common/governments/civics/",
        "literal_key_field",
        wrapper="civic",
        condition_fields=("potential", "allow", "possible"),
        localisation_rule="name_field",
    ),
    "origin": DomainSpec(
        "origin",
        "common/governments/origins/",
        "literal_id_field",
        wrapper="origin",
        condition_fields=("potential", "allow", "possible"),
        localisation_rule="name_field",
    ),
    # Authored synthetic only: neither the outer group nor a child group
    # key becomes an ID. A direct child must carry a unique static id field.
    "tradition": DomainSpec(
        "tradition",
        "common/traditions/",
        "nested_id_field",
        wrapper="traditions",
        condition_fields=("potential", "allow", "prerequisites", "weight"),
        localisation_rule="name_field",
    ),
    # Authored synthetic only: an ascension_perk wrapper has a unique literal
    # ID field; the type name, filename and order cannot substitute for it.
    "ascension_perk": DomainSpec(
        "ascension_perk",
        "common/ascension_perks/",
        "literal_id_field",
        wrapper="ascension_perk",
        condition_fields=("potential", "allow", "possible", "prerequisites"),
        localisation_rule="name_field",
    ),
    # Authored synthetic country_event/planet_event only. The event parser
    # validates file-global namespace declarations separately; only an
    # explicit unique literal id field can identify the event.
    "event": DomainSpec(
        "event",
        "events/",
        "literal_id_field",
        condition_fields=("trigger", "potential", "allow"),
        localisation_rule="title_field",
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
        or (spec.flat_files_only and "/" in path[len(spec.path_prefix):])
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


class _DomainDiagnosticBudget(Exception):
    """Internal early-stop signal; never leak incomplete candidates."""

    def __init__(self, source_ref: SourceRef) -> None:
        self.source_ref = source_ref


def _make_candidate(
    pair: PairNode,
    spec: DomainSpec,
    source: bytes,
    context: SourceContext,
    parse_diagnostics: tuple[DomainDiagnostic, ...],
    *,
    remaining_diagnostics: int = DEFAULT_PARSER_MAX_DIAGNOSTICS,
) -> DomainCandidate:
    ref = _source_ref(context, pair.span)

    # A single definition can itself contain thousands of warning-producing
    # fields. Preflight the same unsupported operators and unknown nodes before
    # allocating any RawNodeRef projections. This preserves the overall parser
    # and adapter diagnostic budget even for just one candidate.
    if isinstance(pair.value, BlockNode):
        pending = 0
        for item in pair.value.items:
            if isinstance(item, PairNode) and item.operator_kind != "assign":
                pending += 1
            for _ in _unknown_nodes(item):
                pending += 1
            if pending >= remaining_diagnostics:
                raise _DomainDiagnosticBudget(_source_ref(context, item.span))

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
    added_warnings = 0

    def warning(code: str, message: str, source_ref: SourceRef) -> None:
        nonlocal added_warnings
        # Reserve the warning slot *before* creating the object. Reaching the
        # existing shared limit is a hard stop, not a truncated partial result.
        if added_warnings + 1 >= remaining_diagnostics:
            raise _DomainDiagnosticBudget(source_ref)
        diagnostics.append(DomainDiagnostic(code, "warning", message, source_ref))
        added_warnings += 1

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
                warning(
                    "DOMAIN_UNSUPPORTED_OPERATOR",
                    "Non-assignment field retained without evaluated semantics.",
                    _source_ref(context, item.span),
                )
        for node in _unknown_nodes(pair.value):
            warning(
                "DOMAIN_UNKNOWN_STRUCTURE",
                "Unsupported nested syntax retained as raw AST.",
                _source_ref(context, node.span),
            )
    else:
        warning(
            "DOMAIN_INVALID_DEFINITION",
            "Domain definition is not a block; raw pair retained.",
            ref,
        )

    game_id: str | None = None
    id_ref: SourceRef | None = None
    if spec.id_rule in ("root_identifier", "nested_identifier"):
        # Only identifier-based rules use a pair key as the game ID.
        # Nested id-field rules use the unique value of an explicit id field.
        game_id = _literal(ScalarNode(
            "scalar", pair.key_kind, pair.key_text, pair.key_span
        ))
        if game_id is not None:
            id_ref = _source_ref(context, pair.key_span)
    else:
        # Unique literal ID-bearing field; a dynamic/duplicate/missing ID is
        # never inferred from a wrapper, filename or definition occurrence.
        id_name = "key" if spec.id_rule == "literal_key_field" else "id"
        id_pairs = (
            [
                item for item in pair.value.items
                if isinstance(item, PairNode) and item.key_text == id_name
            ]
            if isinstance(pair.value, BlockNode) else []
        )
        if len(id_pairs) == 1 and id_pairs[0].operator_kind == "assign":
            game_id = _literal(id_pairs[0].value)
            if game_id is not None and id_pairs[0].value is not None:
                id_ref = _source_ref(context, id_pairs[0].value.span)

    if game_id is None:
        warning(
            "DOMAIN_UNRESOLVED_ID",
            "A unique non-dynamic literal ID was not established.",
            ref,
        )
    if isinstance(pair.value, BlockNode) and not pair.value.closed:
        warning(
            "DOMAIN_UNCLOSED_BLOCK",
            "Unclosed definition cannot be treated as fully supported.",
            ref,
        )

    # This is an explicit authored-synthetic localisation-key policy. A
    # display-name field is different from a game ID and must be a *unique*
    # static literal; an unknown/dynamic name remains unresolved, not guessed.
    localisation_key = game_id
    if spec.localisation_rule in ("name_field", "title_field"):
        name_field = "title" if spec.localisation_rule == "title_field" else "name"
        names = (
            [
                item for item in pair.value.items
                if isinstance(item, PairNode) and item.key_text == name_field
            ]
            if isinstance(pair.value, BlockNode) else []
        )
        localisation_key = (
            _literal(names[0].value)
            if len(names) == 1 and names[0].operator_kind == "assign"
            else None
        )
        if localisation_key is None or game_id is None:
            localisation_key = None
            warning(
                "DOMAIN_UNRESOLVED_LOCALISATION_KEY",
                "A unique literal display-name localisation key was not established.",
                ref,
            )

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
        localisation_key=localisation_key,
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

    # Validate the whole token/document/diagnostic/coordinate contract exactly
    # once per input file, not once for each candidate. Span-only checks cannot
    # detect a different (or empty) ParseResult that omits valid definitions.
    # Hard resource/encoding stops remain blocked without raising their limits
    # or re-parsing hostile input with more generous limits.
    if not any(d.code in _HARD_PARSE_CODES for d in parsed.diagnostics):
        if parsed != parse_bytes(source):
            raise ValueError(
                "ParseResult does not match the complete verified source bytes."
            )
    return _adapt_bound_domain(parsed, source, context, spec)


def _adapt_bound_domain(
    parsed: ParseResult,
    source: bytes,
    context: SourceContext,
    spec: DomainSpec,
) -> DomainAdaptResult:
    """Internal extraction for an already validated, source-bound parse."""

    parse_diagnostics = tuple(
        DomainDiagnostic(d.code, d.severity, d.message,
                         _source_ref(context, d.span), d.origin)
        for d in parsed.diagnostics
    )
    if any(d.code in _HARD_PARSE_CODES for d in parse_diagnostics):
        # A resource stop is never a partial candidate that callers may activate.
        return DomainAdaptResult((), parse_diagnostics, (), False, blocked=True)

    if spec.kind == "event":
        # The namespace-aware adapter receives only an already validated
        # whole-file canonical ParseResult; no weaker parsing path is exposed.
        from stellaris_supporter.domain.event import adapt_events_bound

        return adapt_events_bound(parsed, source, context, spec, parse_diagnostics)

    candidates: list[DomainCandidate] = []
    diagnostics: list[DomainDiagnostic] = list(parse_diagnostics)
    unhandled: list[RawNodeRef] = []
    occurrences: dict[str, int] = {}

    def diagnostic_limit_result(ref: SourceRef) -> DomainAdaptResult:
        hard = DomainDiagnostic(
            "LIMIT_EXCEEDED", "error",
            "Domain diagnostic budget exhausted; no candidates accepted.",
            ref,
        )
        return DomainAdaptResult((), (hard,), (), False, blocked=True)

    def accept(pair: PairNode) -> DomainAdaptResult | None:
        from dataclasses import replace

        try:
            candidate = _make_candidate(
                pair, spec, source, context, parse_diagnostics,
                remaining_diagnostics=(
                    DEFAULT_PARSER_MAX_DIAGNOSTICS - len(diagnostics)
                ),
            )
        except _DomainDiagnosticBudget as exceeded:
            return diagnostic_limit_result(exceeded.source_ref)
        if candidate.game_id is not None:
            occurrences[candidate.game_id] = occurrences.get(candidate.game_id, 0) + 1
            candidate = replace(
                candidate, definition_occurrence=occurrences[candidate.game_id]
            )
        candidates.append(candidate)
        diagnostics.extend(d for d in candidate.diagnostics if d.origin == "adapter")
        return None

    def retain_unsupported(item: AstNode) -> None:
        unhandled.append(_raw_node(item, source, context))
        diagnostics.append(DomainDiagnostic(
            "DOMAIN_UNSUPPORTED_TOP_LEVEL", "warning",
            "Unrecognised domain definition or directive was retained.",
            _source_ref(context, item.span),
        ))

    def stop_at_diagnostic_limit(item: AstNode) -> DomainAdaptResult | None:
        # Nested domain wrappers must check every direct child, not only the
        # enclosing wrapper. Stop before projecting another candidate once
        # the shared parser+adapter diagnostic budget has been reached.
        if len(diagnostics) < DEFAULT_PARSER_MAX_DIAGNOSTICS:
            return None
        return diagnostic_limit_result(_source_ref(context, item.span))

    for node in parsed.document.items:
        if (stopped := stop_at_diagnostic_limit(node)) is not None:
            return stopped
        is_assignment = (
            isinstance(node, PairNode)
            and node.key_kind == "identifier"
            and node.operator_kind == "assign"
        )
        if (
            spec.id_rule in ("nested_identifier", "nested_id_field")
            and is_assignment
            and node.key_text == spec.wrapper
            and isinstance(node.value, BlockNode)
        ):
            # Only direct child definitions of an explicitly registered
            # wrapper qualify; its name is never a domain candidate ID.
            for child in node.value.items:
                if (
                    isinstance(child, PairNode)
                    and child.key_kind == "identifier"
                    and child.operator_kind == "assign"
                    and _ID.fullmatch(child.key_text)
                ):
                    if (stopped := accept(child)) is not None:
                        return stopped
                else:
                    retain_unsupported(child)
                if (stopped := stop_at_diagnostic_limit(child)) is not None:
                    return stopped
        elif is_assignment and (
            (spec.id_rule == "root_identifier" and _ID.fullmatch(node.key_text))
            or (
                spec.id_rule in ("literal_key_field", "literal_id_field")
                and node.key_text == spec.wrapper
            )
        ):
            if (stopped := accept(node)) is not None:
                return stopped
        else:
            retain_unsupported(node)
        if (stopped := stop_at_diagnostic_limit(node)) is not None:
            return stopped

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
        spec = DOMAIN_REGISTRY.get(candidate.kind)
        if spec is None:
            return False
        # One canonical parse per verification call. Do not reparse again in
        # adapt_domain, and do not add a full-file parse per field or child.
        parsed = parse_bytes(source)
        _validate_inputs(parsed, source, context, spec)
        rebuilt = _adapt_bound_domain(parsed, source, context, spec)
    except (TypeError, ValueError, UnicodeError):
        return False
    for expected in rebuilt.candidates:
        if expected != candidate:
            continue

        # RawNodeRef._source is intentionally excluded from dataclass equality.
        # Each independent projection (items, fields, conditions) and every
        # nested child must instead agree with the validated source bytes.
        def source_matches(node: RawNodeRef) -> bool:
            return (
                node.raw_bytes() == node.source_ref.raw_bytes(source)
                and all(source_matches(child) for child in node.children)
            )

        return (
            all(source_matches(item) for item in candidate.items)
            and all(
                item.value is None or source_matches(item.value)
                for item in candidate.fields
            )
            and all(
                item.value is None or source_matches(item.value)
                for item in candidate.conditions
            )
        )
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
