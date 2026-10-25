"""Deterministic, citation-verified static technology answers.

No game-engine evaluation, model calls, filesystem source writes, or implicit
snapshot switching. A searched entity is read by its exact immutable key.
"""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from typing import Any, Literal

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.localisation import LocalisationReferenceSelection
from stellaris_supporter.parsing import BlockNode, PairNode, parse_bytes
from stellaris_supporter.retrieval import Query, SearchHit, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository
from stellaris_supporter.storage.identity import storage_json
from stellaris_supporter.storage.repository import MAX_JSON_BYTES

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
    match_source_ref: SourceRef | None = None
    match_reference_selections: tuple[LocalisationReferenceSelection, ...] = ()
    match_language_used: str | None = None


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


class _Budget:
    """One envelope-wide budget, shared by all results, not reset per hit."""

    def __init__(self) -> None:
        self.facts = 0
        self.citations = 0
        self.output = 0
        self.truncated = False

    def charge(self, *, facts: int = 0, citations: int = 0, output: int = 0) -> bool:
        if (self.facts + facts > MAX_FACTS
                or self.citations + citations > MAX_CITATIONS
                or self.output + output > MAX_OUTPUT_BYTES):
            self.truncated = True
            return False
        self.facts += facts
        self.citations += citations
        self.output += output
        return True


def _same_file(left: SourceRef, right: SourceRef) -> bool:
    return (
        left.snapshot_id, left.source_kind, left.source_id,
        left.relative_path, left.file_sha256
    ) == (
        right.snapshot_id, right.source_kind, right.source_id,
        right.relative_path, right.file_sha256
    )


def _span(ref: SourceRef, offset: int) -> tuple[int, int]:
    return ref.byte_start - offset, ref.byte_end - offset


def _field_structure(
    definition: SourceRef, original: bytes, fields: list[Any], game_id: str,
) -> None:
    """Compare persisted fields with the parser's ordered, direct child pairs.

    Parsing ONLY the bounded citation definition prevents nested/comment/string
    substrings from posing as top-level technology fields. No inferred values.
    """
    if len(original) > 1024 * 1024:
        raise SnapshotError("LIMIT_EXCEEDED", "Definition reparse exceeds 1 MiB.")
    parsed = parse_bytes(original, max_bytes=1024 * 1024)
    if not parsed.ok or len(parsed.document.items) != 1:
        raise SnapshotError("SOURCE_CHANGED", "Definition source cannot be verified.")
    root = parsed.document.items[0]
    if not isinstance(root, PairNode) or not isinstance(root.value, BlockNode):
        raise SnapshotError("SOURCE_CHANGED", "Definition is not a parsed key and block.")
    if root.key_text != game_id:
        raise SnapshotError("SOURCE_CHANGED", "Root technology ID differs from stored identity.")
    actual = [item for item in root.value.items if isinstance(item, PairNode)]
    if len(actual) != len(fields):
        raise SnapshotError("SOURCE_CHANGED", "Stored fields differ from original structure.")
    occurrences: dict[str, int] = {}
    for stored, item in zip(fields, actual, strict=True):
        if not isinstance(stored, dict):
            raise SnapshotError("SOURCE_CHANGED", "Stored field is malformed.")
        name = item.key_text
        occurrences[name] = occurrences.get(name, 0) + 1
        field_ref = _ref(stored["source_ref"])
        raw_ref = stored["value_source_ref"]
        value_ref = None if raw_ref is None else _ref(raw_ref)
        if (
            not _same_file(definition, field_ref)
            or _span(field_ref, definition.byte_start) != (
                item.span.byte_start, item.span.byte_end
            )
            or stored["name"] != name
            or stored["operator"] != item.operator_text
            or stored["occurrence"] != occurrences[name]
            or (value_ref is None) != (item.value is None)
        ):
            raise SnapshotError("SOURCE_CHANGED", "Stored field structure was altered.")
        if value_ref is not None and item.value is not None:
            if (
                not _same_file(definition, value_ref)
                or _span(value_ref, definition.byte_start) != (
                    item.value.span.byte_start, item.value.span.byte_end
                )
            ):
                raise SnapshotError("SOURCE_CHANGED", "Stored field value is not its child.")


class AnswerService:
    """One search, pinned manifest, verified field syntax and global budgets."""

    def __init__(self, search: SearchService, repository: SnapshotRepository) -> None:
        if search.repository is not repository:
            raise ValueError("SearchService and repository must be identical objects")
        self.search = search
        self.repository = repository

    def _format_hit(
        self, hit: SearchHit, sid: str, wanted: str | None,
        reader: Any, budget: _Budget,
    ) -> AnswerResult | None:
        stored = self.repository.answer_entity(sid, hit.entity_key)
        candidate = stored["candidate"]
        definition = _ref(candidate["source_ref"])
        if (
            stored["game_id"] != hit.game_id
            or candidate["game_id"] != hit.game_id
            or stored["kind"] != hit.kind
            or candidate["kind"] != hit.kind
            or hit.kind != "technology"
            or definition != hit.definition_source_ref
            or (definition.source_kind, definition.source_id,
                definition.relative_path, definition.byte_start, definition.byte_end)
            != (stored["source_kind"], stored["source_id"],
                stored["relative_path"], stored["byte_start"], stored["byte_end"])
            or isinstance(stored["occurrence"], bool)
            or not isinstance(stored["occurrence"], int)
            or stored["occurrence"] < 1
        ):
            raise SnapshotError("SOURCE_CHANGED", "Search result differs from candidate.")
        expected_key = hashlib.sha256(storage_json({
            "kind": stored["kind"], "game_id": stored["game_id"],
            "source": definition.to_dict(), "occurrence": stored["occurrence"],
        }, max_bytes=MAX_JSON_BYTES)).hexdigest()
        if expected_key != hit.entity_key:
            raise SnapshotError("SOURCE_CHANGED", "Entity key does not match source identity.")
        original = reader.read(definition)
        fields = candidate["fields"]
        if not isinstance(fields, list):
            raise SnapshotError("SOURCE_CHANGED", "Candidate fields are malformed.")
        _field_structure(definition, original, fields, hit.game_id)
        if not budget.charge(output=len(hit.display_name.encode("utf-8"))):
            return None
        citations: list[SourceRef] = [
            definition, hit.match_source_ref,
        ]
        if hit.localisation_source_ref is not None:
            citations.append(hit.localisation_source_ref)
        citations.extend(item.source_ref for item in hit.localisation_reference_selections)
        citations.extend(item.source_ref for item in hit.match_reference_selections)
        for ref in citations:
            reader.read(ref)
        unique = list(dict.fromkeys(citations))
        if not budget.charge(citations=len(unique)):
            return None
        facts: list[AnswerFact] = []
        warnings = [
            _diag(x.code, x.message, x.severity) for x in hit.diagnostics
        ]
        found = False
        for item in fields:
            if wanted is not None and item["name"] != wanted:
                continue
            found = True
            ref = _ref(item["source_ref"])
            value_ref = (
                None if item["value_source_ref"] is None
                else _ref(item["value_source_ref"])
            )
            # The parser-verified offsets must ALSO be from this definition's
            # exact original file, not another valid file in the snapshot.
            if not _same_file(definition, ref):
                raise SnapshotError("SOURCE_CHANGED", "Field source differs from definition.")
            span = reader.read(ref)
            value_span = None
            if value_ref is not None:
                if not _same_file(definition, value_ref):
                    raise SnapshotError("SOURCE_CHANGED", "Value source differs from definition.")
                value_span = reader.read(value_ref)
            if value_span is not None and len(value_span) > MAX_FIELD_BYTES:
                warnings.append(_diag("VALUE_LIMIT", "Raw expression omitted by byte budget."))
                budget.truncated = True
                continue
            raw = None if value_span is None else value_span.decode("utf-8")
            charge = len(span) + (0 if value_span is None else len(value_span))
            needed = int(ref not in unique) + int(
                value_ref is not None and value_ref not in unique and value_ref != ref
            )
            if not budget.charge(facts=1, citations=needed, output=charge):
                warnings.append(_diag("ANSWER_LIMIT", "Global fact/citation/output limit."))
                break
            if ref not in unique:
                unique.append(ref)
            if value_ref is not None and value_ref not in unique:
                unique.append(value_ref)
            literal = (
                raw is not None and not raw.startswith(("@", "{", "[", "$"))
                and not any(x in raw for x in ("£", "§"))
            )
            status = "literal" if literal else "unsupported_expression"
            facts.append(AnswerFact(
                item["name"], item["occurrence"], item["operator"], raw,
                "raw_literal" if literal else "raw_expression", status,
                ref, value_ref,
                () if literal else (
                    _diag("DYNAMIC_UNEVALUATED", "Only original expression is known."),
                ),
            ))
        if wanted is not None and not found:
            warnings.append(_diag("FIELD_NOT_FOUND", "Requested field is absent."))
        if not facts:
            warnings.append(_diag("NO_VERIFIED_FIELDS", "No field facts were returned."))
        if hit.resolution in {"partial", "ambiguous"}:
            warnings.append(_diag(
                "DEFINITION_" + hit.resolution.upper(), "Definition is not unambiguous."
            ))
        return AnswerResult(
            sid, hit.entity_key, hit.game_id, hit.kind, hit.display_name,
            hit.match_reason, tuple(facts), tuple(unique),
            definition, hit.localisation_source_ref,
            hit.localisation_reference_selections, hit.resolution,
            hit.fallback, tuple(warnings),
            hit.match_source_ref, hit.match_reference_selections,
            None,  # SearchHit does not expose independent match language yet.
        )

    def answer(
        self, query: Query, *, field: str | None = None,
        exact_game_id: bool = False, entity_key: str | None = None,
    ) -> AnswerEnvelope:
        if entity_key is not None and (not isinstance(entity_key, str) or not re.fullmatch(r"[0-9a-f]{64}", entity_key)):
            return AnswerEnvelope(1, "error", query, None, (),
                                  (_diag("QUERY_INVALID", "Invalid entity selector.", "error"),), False)
        if field is not None and (
            not isinstance(field, str) or not field or len(field) > 128
        ):
            return AnswerEnvelope(
                1, "error", query, None, (),
                (_diag("QUERY_INVALID", "Invalid field selector.", "error"),), False,
            )
        if not isinstance(query, Query):
            return AnswerEnvelope(
                1, "error", Query(""), None, (),
                (_diag("QUERY_INVALID", "Typed query required.", "error"),), False,
            )
        # Typed validation precedes intent decisions. An exact technology name
        # always wins over a broad English keyword such as "Combat".
        _, error = SearchService._validate(query)
        if error is not None:
            return AnswerEnvelope(
                1, "error", query, None, (),
                (_diag("QUERY_INVALID", error, "error"),), False,
            )
        found = self.search.search(query)
        if found.status == "error" or found.context is None:
            return AnswerEnvelope(
                1, "error", query, None, (),
                tuple(_diag(d.code, d.message, d.severity)
                      for d in found.diagnostics), found.truncated,
            )
        sid = found.context.snapshot_id
        context: AnswerContext | None = None
        try:
            meta = self.repository.answer_snapshot_context(sid)
            context = AnswerContext(
                sid, found.context.kind, meta["game_version"],
                meta["game_version_source"], meta["branch"],
                meta["context_kind"], meta["mod_state"],
                meta["checked_at"], meta["status"],
            )
            is_question = bool(_UNSUPPORTED.search(query.text))
            # An exact ID/name/alias is a lookup, regardless of its spelling.
            exact = any(x.match_reason in {
                "game_id_exact", "name_exact", "alias_exact"
            } for x in found.results)
            if is_question and not exact:
                return AnswerEnvelope(
                    1, "unsupported", query, context, (),
                    (_diag("UNSUPPORTED_CALCULATION",
                           "Game calculations/effective-state analysis are unsupported."),),
                    False,
                )
            selected = (
                tuple(hit for hit in found.results
                      if hit.game_id == query.text and hit.match_reason == "game_id_exact")
                if exact_game_id else found.results
            )
            if entity_key is not None:
                selected = tuple(hit for hit in selected if hit.entity_key == entity_key)
            if not selected:
                return AnswerEnvelope(
                    1, "partial" if found.status == "partial" else "not_found",
                    query, context, (),
                    tuple(_diag(d.code, d.message, d.severity)
                          for d in found.diagnostics), found.truncated,
                )
            budget = _Budget()
            results: list[AnswerResult] = []
            with self.repository.citation_reader(sid) as reader:
                for hit in selected:
                    if budget.truncated:
                        break
                    result = self._format_hit(hit, sid, field, reader, budget)
                    if result is not None:
                        results.append(result)
            warnings = tuple(
                _diag(d.code, d.message, d.severity) for d in found.diagnostics
            )
            truncated = found.truncated or budget.truncated
            partial = (
                found.status == "partial" or truncated
                or any(
                    result.warnings
                    or any(f.support_status != "literal" for f in result.facts)
                    for result in results
                )
            )
            if budget.truncated:
                warnings += (_diag("ANSWER_LIMIT", "Envelope resource limit reached."),)
            return AnswerEnvelope(
                1, "partial" if partial else "ok", query, context,
                tuple(results), warnings, truncated,
            )
        except SnapshotError as exc:
            return AnswerEnvelope(
                1, "error", query, context, (),
                (_diag(exc.code, str(exc), "error"),), False,
            )
        except (KeyError, ValueError, TypeError, UnicodeError, OverflowError):
            return AnswerEnvelope(
                1, "error", query, context, (),
                (_diag("SOURCE_CHANGED", "Stored answer provenance is invalid.", "error"),),
                False,
            )
