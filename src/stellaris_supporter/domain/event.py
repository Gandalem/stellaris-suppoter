"""C1 authored-synthetic event/namespace adapter.

This module is *only* called by generic._adapt_bound_domain after the original
whole-file SHA, SourceRef, AST, and canonical ParseResult checks. It never
evaluates event triggers, event scheduling, nested event effects, or mod order.
Only 'country_event' and 'planet_event' are authored synthetic grammars here.
"""

from __future__ import annotations

import re
from dataclasses import replace
from typing import Literal

from stellaris_supporter.domain import generic as domain
from stellaris_supporter.domain.technology import SourceContext, SourceRef
from stellaris_supporter.parsing import PairNode, ParseResult

_SUPPORTED_EVENT_TYPES = frozenset({"country_event", "planet_event"})
_NAMESPACE = re.compile(r"[A-Za-z_][A-Za-z0-9_]*\Z")


def adapt_events_bound(
    parsed: ParseResult,
    source: bytes,
    context: SourceContext,
    spec: domain.DomainSpec,
    parse_diagnostics: tuple[domain.DomainDiagnostic, ...],
) -> domain.DomainAdaptResult:
    """Extract only explicitly registered events from a verified source parse."""

    diagnostics: list[domain.DomainDiagnostic] = list(parse_diagnostics)
    candidates: list[domain.DomainCandidate] = []
    unhandled: list[domain.RawNodeRef] = []
    occurrences: dict[str, int] = {}
    namespaces: set[str] = set()
    namespace_issue = False

    def block(ref: SourceRef) -> domain.DomainAdaptResult:
        return domain.DomainAdaptResult(
            (), (domain.DomainDiagnostic(
                "LIMIT_EXCEEDED", "error",
                "Event parser+adapter diagnostic budget exhausted.",
                ref,
            ),), (), False, blocked=True,
        )

    def add(
        code: str,
        severity: Literal["info", "warning", "error"],
        message: str,
        ref: SourceRef,
    ) -> domain.DomainAdaptResult | None:
        diagnostics.append(domain.DomainDiagnostic(code, severity, message, ref))
        if len(diagnostics) >= domain.DEFAULT_PARSER_MAX_DIAGNOSTICS:
            return block(ref)
        return None

    # All namespace declarations in this file are source-grounded. A different
    # file's declaration is *never* inferred to apply to this snapshot/file.
    # Retain a distinct informational SourceRef for each identical declaration.
    for node in parsed.document.items:
        if not isinstance(node, PairNode) or node.key_text != "namespace":
            continue
        ref = domain._source_ref(context, node.span)
        if node.key_kind != "identifier" or node.operator_kind != "assign":
            namespace_issue = True
            stopped = add(
                "DOMAIN_EVENT_NAMESPACE_INVALID", "warning",
                "Unsupported namespace declaration operator retained.",
                ref,
            )
        else:
            value = domain._literal(node.value)
            if value is None or _NAMESPACE.fullmatch(value) is None:
                namespace_issue = True
                stopped = add(
                    "DOMAIN_EVENT_NAMESPACE_INVALID", "warning",
                    "Namespace is not a unique static identifier in this file.",
                    ref,
                )
            else:
                namespaces.add(value)
                stopped = add(
                    "DOMAIN_EVENT_NAMESPACE", "info",
                    "Authored synthetic namespace declaration (provenance only).",
                    ref,
                )
        if stopped is not None:
            return stopped

    if len(namespaces) > 1:
        namespace_issue = True
        for node in parsed.document.items:
            if isinstance(node, PairNode) and node.key_text == "namespace":
                stopped = add(
                    "DOMAIN_EVENT_NAMESPACE_CONFLICT", "warning",
                    "Conflicting namespaces; no file- or engine-precedence inferred.",
                    domain._source_ref(context, node.span),
                )
                if stopped is not None:
                    return stopped
                break
    declared_namespace = (
        next(iter(namespaces))
        if len(namespaces) == 1 and not namespace_issue else None
    )

    # Definitions remain in their original top-level order. Nested event-looking
    # expressions are raw members of the parent, never independent candidates.
    for node in parsed.document.items:
        if isinstance(node, PairNode) and node.key_text == "namespace":
            continue  # its SourceRef is retained above as a diagnostic
        ref = domain._source_ref(context, node.span)
        if len(diagnostics) >= domain.DEFAULT_PARSER_MAX_DIAGNOSTICS:
            return block(ref)
        is_event = (
            isinstance(node, PairNode)
            and node.key_kind == "identifier"
            and node.operator_kind == "assign"
            and node.key_text in _SUPPORTED_EVENT_TYPES
        )
        if not is_event:
            unhandled.append(domain._raw_node(node, source, context))
            stopped = add(
                "DOMAIN_UNSUPPORTED_TOP_LEVEL", "warning",
                "Unsupported event type or structure preserved as raw AST.",
                ref,
            )
            if stopped is not None:
                return stopped
            continue

        try:
            candidate = domain._make_candidate(
                node, spec, source, context, parse_diagnostics,
                remaining_diagnostics=(
                    domain.DEFAULT_PARSER_MAX_DIAGNOSTICS - len(diagnostics)
                ),
            )
        except domain._DomainDiagnosticBudget as exceeded:
            return block(exceeded.source_ref)

        # Adapter-origin warnings inside a definition consume the shared
        # diagnostic budget, exactly as in the generic domain adapter.
        for d in candidate.diagnostics:
            if d.origin != "adapter":
                continue
            diagnostics.append(d)
            if len(diagnostics) >= domain.DEFAULT_PARSER_MAX_DIAGNOSTICS:
                return block(d.source_ref)

        def candidate_warning(
            code: str, message: str, source_ref: SourceRef
        ) -> domain.DomainAdaptResult | None:
            nonlocal candidate
            warning = domain.DomainDiagnostic(code, "warning", message, source_ref)
            candidate = replace(
                candidate,
                diagnostics=(*candidate.diagnostics, warning),
                resolution="partial",
                support_level="partial",
            )
            return add(code, "warning", message, source_ref)

        if declared_namespace is None:
            reason = (
                "Conflicting/invalid local declarations; external namespace "
                "bindings are not inferred."
                if namespace_issue else
                "No file-local namespace declaration; cross-file scope unverified."
            )
            stopped = candidate_warning(
                "DOMAIN_EVENT_NAMESPACE_UNVERIFIED", reason, ref
            )
            if stopped is not None:
                return stopped
        elif candidate.game_id is not None:
            if "." not in candidate.game_id:
                stopped = candidate_warning(
                    "DOMAIN_EVENT_UNQUALIFIED_ID",
                    "Explicit event ID is not namespace-qualified.",
                    candidate.id_source_ref or ref,
                )
                if stopped is not None:
                    return stopped
            elif candidate.game_id.split(".", 1)[0] != declared_namespace:
                stopped = candidate_warning(
                    "DOMAIN_EVENT_NAMESPACE_MISMATCH",
                    "Static event ID prefix does not match the local namespace.",
                    candidate.id_source_ref or ref,
                )
                if stopped is not None:
                    return stopped

        if candidate.game_id is not None:
            occurrences[candidate.game_id] = (
                occurrences.get(candidate.game_id, 0) + 1
            )
            candidate = replace(
                candidate,
                definition_occurrence=occurrences[candidate.game_id],
            )
        candidates.append(candidate)

    # Ambiguous same-ID definitions are never reduced to last-wins. This
    # includes duplicates across *different supported event type wrappers*.
    if occurrences:
        candidates = [
            replace(c, resolution="ambiguous", support_level="partial")
            if c.game_id is not None and occurrences[c.game_id] > 1
            else c for c in candidates
        ]
        for candidate in candidates:
            if candidate.resolution != "ambiguous":
                continue
            stopped = add(
                "DOMAIN_DUPLICATE_ID", "warning",
                "Multiple event definitions share an ID; no precedence inferred.",
                candidate.source_ref,
            )
            if stopped is not None:
                return stopped

    return domain.DomainAdaptResult(
        tuple(candidates),
        tuple(diagnostics),
        tuple(unhandled),
        parsed.ok
        and not namespace_issue
        and not unhandled
        and all(c.resolution == "raw_definition" for c in candidates),
    )
