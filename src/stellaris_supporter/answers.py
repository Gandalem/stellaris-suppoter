"""Deterministic, citation-verified static technology answers.

No game-engine evaluation, model calls, filesystem source writes, or implicit
snapshot switching. A searched entity is read by its exact immutable key.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.localisation import LocalisationReferenceSelection
from stellaris_supporter.retrieval import Query, SearchHit, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository

AnswerStatus = Literal["ok", "partial", "not_found", "unsupported", "error"]
MAX_FACTS = 64
MAX_FIELD_BYTES = 512
MAX_CITATIONS = 256
MAX_OUTPUT_BYTES = 64 * 1024
_UNSUPPORTED = re.compile(
    r"(?:\bprobability\b|\bchance\b|\bcombat\b|\bwin.rate\b|"
    r"\bresearch.time\b|\bcompletion.time\b|\beffective\b|\bmod.effect\b|"
    r"확률|승률|완료\s*시간|최종\s*효과|조건.*(?:참|평가))",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class AnswerDiagnostic:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class AnswerFact:
    field_name: str
    occurrence: int
    operator: str
    raw_expression: str | None
    value_kind: str
    support_status: str
    source_ref: SourceRef
    value_source_ref: SourceRef | None
    diagnostics: tuple[AnswerDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class AnswerResult:
    snapshot_id: str
    entity_key: str
    game_id: str
    kind: str
    display_name: str
    match_reason: str
    facts: tuple[AnswerFact, ...]
    source_refs: tuple[SourceRef, ...]
    definition_source_ref: SourceRef
    localisation_source_ref: SourceRef | None
    localisation_reference_selections: tuple[LocalisationReferenceSelection, ...]
    resolution: str
    fallback: str
    warnings: tuple[AnswerDiagnostic, ...]


@dataclass(frozen=True, slots=True)
class AnswerContext:
    snapshot_id: str
    kind: str | None
    game_version: str | None
    game_version_source: str
    branch: str
    context_kind: str
    mod_state: str
    checked_at: str | None
    snapshot_status: str


@dataclass(frozen=True, slots=True)
class AnswerEnvelope:
    schema_version: int
    status: AnswerStatus
    query: Query
    context: AnswerContext | None
    results: tuple[AnswerResult, ...]
    diagnostics: tuple[AnswerDiagnostic, ...]
    truncated: bool


def _ref(value: dict[str, object]) -> SourceRef:
    return SourceRef(**value)


def _diag(code: str, message: str, severity: str = "warning") -> AnswerDiagnostic:
    return AnswerDiagnostic(code, severity, message)


class AnswerService:
    """Statically format the result of SearchService.search, pinned to one snapshot."""

    def __init__(self, search: SearchService, repository: SnapshotRepository) -> None:
        if search.repository is not repository:
            raise ValueError("SearchService and repository must be identical objects")
        self.search = search
        self.repository = repository

    def _validate_ref(self, ref: SourceRef, sid: str) -> bytes:
        if ref.snapshot_id != sid:
            raise SnapshotError("SOURCE_CHANGED", "Citation points outside pinned snapshot.")
        return self.repository.citation_bytes(ref)

    def _format_hit(self, hit: SearchHit, sid: str, wanted: str | None) -> AnswerResult:
        stored = self.repository.answer_entity(sid, hit.entity_key)
        candidate = stored["candidate"]
        definition = _ref(candidate["source_ref"])
        if (stored["game_id"] != hit.game_id or stored["kind"] != hit.kind
                or definition != hit.definition_source_ref):
            raise SnapshotError("SOURCE_CHANGED", "Search entity and stored candidate differ.")
        self._validate_ref(definition, sid)
        citations: list[SourceRef] = [definition]
        if hit.localisation_source_ref is not None:
            self._validate_ref(hit.localisation_source_ref, sid)
            citations.append(hit.localisation_source_ref)
        for selection in hit.localisation_reference_selections:
            self._validate_ref(selection.source_ref, sid)
            citations.append(selection.source_ref)
        self._validate_ref(hit.match_source_ref, sid)
        citations.append(hit.match_source_ref)
        for selection in hit.match_reference_selections:
            self._validate_ref(selection.source_ref, sid)
            citations.append(selection.source_ref)
        if len(citations) > MAX_CITATIONS:
            raise SnapshotError("LIMIT_EXCEEDED", "Answer has too many source citations.")

        facts: list[AnswerFact] = []
        warnings: list[AnswerDiagnostic] = [
            _diag(item.code, item.message, item.severity) for item in hit.diagnostics
        ]
        fields = candidate["fields"]
        if not isinstance(fields, list):
            raise SnapshotError("SOURCE_CHANGED", "Candidate fields are malformed.")
        budget = MAX_OUTPUT_BYTES
        matching = 0
        for item in fields:
            if wanted is not None and item["name"] != wanted:
                continue
            matching += 1
            if len(facts) >= MAX_FACTS:
                warnings.append(_diag("FACT_LIMIT", "Answer facts truncated."))
                break
            ref = _ref(item["source_ref"])
            value = None if item["value_source_ref"] is None else _ref(item["value_source_ref"])
            field_span = self._validate_ref(ref, sid)
            if not (definition.byte_start <= ref.byte_start < ref.byte_end
                    <= definition.byte_end):
                raise SnapshotError("SOURCE_CHANGED", "Field is outside its definition.")
            raw: str | None = None
            if value is not None:
                if not (ref.byte_start <= value.byte_start < value.byte_end <= ref.byte_end):
                    raise SnapshotError("SOURCE_CHANGED", "Value is outside field span.")
                value_span = self._validate_ref(value, sid)
                if field_span[value.byte_start - ref.byte_start:
                              value.byte_end - ref.byte_start] != value_span:
                    raise SnapshotError("SOURCE_CHANGED", "Value span does not match field bytes.")
                if len(value_span) > MAX_FIELD_BYTES:
                    warnings.append(_diag("VALUE_LIMIT", "Long field expression was omitted."))
                    continue
                raw = value_span.decode("utf-8")
            field_name = item["name"]
            if not isinstance(field_name, str) or not field_name:
                raise SnapshotError("SOURCE_CHANGED", "Invalid field name.")
            if field_name.encode("utf-8") not in field_span:
                raise SnapshotError("SOURCE_CHANGED", "Field label is absent from citation.")
            if item["operator"].encode("utf-8") not in field_span:
                raise SnapshotError("SOURCE_CHANGED", "Field operator absent from citation.")
            budget -= len(field_span) + (0 if raw is None else len(raw.encode("utf-8")))
            if budget < 0:
                warnings.append(_diag("OUTPUT_LIMIT", "Answer text budget exceeded."))
                break
            # A literal token is merely an observed script literal, NOT a
            # calculated game value. References and blocks stay expressions.
            literal = (raw is not None and not raw.startswith(("@", "{", "[", "$"))
                       and not any(x in raw for x in ("£", "§")))
            status = "literal" if literal else "unsupported_expression"
            diagnostics = () if literal else (
                _diag("DYNAMIC_UNEVALUATED", "Only original static expression is known."),
            )
            facts.append(AnswerFact(
                field_name, item["occurrence"], item["operator"], raw,
                "raw_literal" if literal else "raw_expression", status,
                ref, value, diagnostics,
            ))
            citations.append(ref)
            if value is not None:
                citations.append(value)
            if len(citations) > MAX_CITATIONS:
                raise SnapshotError("LIMIT_EXCEEDED", "Answer citation budget exceeded.")
        if wanted is not None and matching == 0:
            warnings.append(_diag("FIELD_NOT_FOUND", "Requested field is absent."))
        if not facts:
            warnings.append(_diag("NO_VERIFIED_FIELDS", "No supported field facts were returned."))
        if hit.resolution in {"partial", "ambiguous"}:
            warnings.append(_diag("DEFINITION_" + hit.resolution.upper(),
                                  "Definition cannot be treated as unambiguous."))
        return AnswerResult(
            sid, hit.entity_key, hit.game_id, hit.kind, hit.display_name,
            hit.match_reason, tuple(facts), tuple(dict.fromkeys(citations)),
            definition, hit.localisation_source_ref,
            hit.localisation_reference_selections, hit.resolution,
            hit.fallback, tuple(warnings),
        )

    def answer(self, query: Query, *, field: str | None = None) -> AnswerEnvelope:
        """Search once then use its snapshot ID throughout, even if active changes."""
        if field is not None and (not isinstance(field, str) or not field
                                  or len(field) > 128):
            return AnswerEnvelope(1, "error", query, None, (),
                                  (_diag("QUERY_INVALID", "Invalid field selector.", "error"),), False)
        if not isinstance(query, Query):
            return AnswerEnvelope(1, "error", Query(""), None, (),
                                  (_diag("QUERY_INVALID", "Typed query required.", "error"),), False)
        # Requests for game-engine calculations must not be transformed into
        # apparently supported static fields or numeric answers.
        if isinstance(query.text, str) and _UNSUPPORTED.search(query.text):
            return AnswerEnvelope(
                1, "unsupported", query, None, (),
                (_diag("UNSUPPORTED_CALCULATION",
                       "Game probability/effective-state computations are not available."),),
                False,
            )
        found = self.search.search(query)
        if found.status == "error" or found.context is None:
            return AnswerEnvelope(1, "error", query, None, (),
                                  tuple(_diag(d.code, d.message, d.severity)
                                        for d in found.diagnostics), found.truncated)
        sid = found.context.snapshot_id
        context: AnswerContext | None = None
        try:
            meta = self.repository.answer_snapshot_context(sid)
            context = AnswerContext(
                sid, found.context.kind, meta["game_version"],
                meta["game_version_source"], meta["branch"],
                meta["context_kind"], meta["mod_state"], meta["checked_at"], meta["status"],
            )
            if not found.results:
                return AnswerEnvelope(
                    1, "partial" if found.status == "partial" else "not_found",
                    query, context, (), tuple(_diag(d.code, d.message, d.severity)
                                               for d in found.diagnostics), found.truncated,
                )
            results = tuple(self._format_hit(hit, sid, field) for hit in found.results)
            warnings = tuple(_diag(d.code, d.message, d.severity)
                             for d in found.diagnostics)
            truncated = found.truncated or any(
                warning.code in {"FACT_LIMIT", "VALUE_LIMIT", "OUTPUT_LIMIT"}
                for hit in results for warning in hit.warnings
            )
            partial = (
                found.status == "partial" or truncated or
                any(hit.warnings or any(f.support_status != "literal" for f in hit.facts)
                    for hit in results)
            )
            return AnswerEnvelope(1, "partial" if partial else "ok", query, context,
                                  results, warnings, truncated)
        except SnapshotError as exc:
            return AnswerEnvelope(1, "error", query, context, (),
                                  (_diag(exc.code, str(exc), "error"),), False)
        except (KeyError, ValueError, TypeError, UnicodeError, OverflowError):
            return AnswerEnvelope(1, "error", query, context, (),
                                  (_diag("SOURCE_CHANGED", "Stored answer provenance is invalid.",
                                         "error"),), False)
