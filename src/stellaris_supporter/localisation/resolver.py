"""Bounded deterministic localisation lookup and static reference expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Literal

from stellaris_supporter.domain.technology import SourceRef, TechnologyCandidate
from stellaris_supporter.localisation.reader import (
    LocalisationDiagnostic,
    LocalisationDocument,
    LocalisationEntry,
)

MAX_CATALOG_ENTRIES = 100_000
DEFAULT_MAX_DEPTH = 64
DEFAULT_MAX_VISITS = 4_096
DEFAULT_MAX_SCAN_BYTES = 8 * 1024 * 1024
DEFAULT_MAX_OUTPUT_BYTES = 1024 * 1024
DEFAULT_MAX_DIAGNOSTICS = 100

_REFERENCE_KEY = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]*\Z")
_LANGUAGE = re.compile(r"[a-z][a-z0-9_]*\Z")
Resolution = Literal["resolved", "partial", "unresolved", "ambiguous"]
Fallback = Literal["none", "english", "id"]


def _language(value: str) -> str:
    normalised = value.strip().lower()
    if normalised.startswith("l_"):
        normalised = normalised[2:]
    if _LANGUAGE.fullmatch(normalised) is None:
        raise ValueError("unsupported localisation language identifier")
    return normalised


@dataclass(frozen=True, slots=True)
class LocalisationCatalog:
    entries: tuple[LocalisationEntry, ...]
    diagnostics: tuple[LocalisationDiagnostic, ...]
    complete: bool
    snapshot_id: str | None
    _index: dict[tuple[str, str], tuple[LocalisationEntry, ...]] = field(
        repr=False, compare=False
    )

    def definitions(self, language: str, key: str) -> tuple[LocalisationEntry, ...]:
        return self._index.get((_language(language), key), ())


def build_localisation_catalog(
    documents: tuple[LocalisationDocument, ...],
    *,
    max_entries: int = MAX_CATALOG_ENTRIES,
    max_diagnostics: int = 1_000,
) -> LocalisationCatalog:
    if isinstance(max_entries, bool) or not isinstance(max_entries, int) or max_entries < 1:
        raise ValueError("max_entries must be a positive integer")

    if isinstance(max_diagnostics, bool) or not isinstance(max_diagnostics, int) or max_diagnostics < 1:
        raise ValueError("max_diagnostics must be a positive integer")

    snapshot = documents[0].context.snapshot_id if documents else None
    diagnostics: list[LocalisationDiagnostic] = []
    complete = True
    entries: list[LocalisationEntry] = []
    index: dict[tuple[str, str], list[LocalisationEntry]] = {}
    for document in documents:
        if len(diagnostics) + len(document.diagnostics) >= max_diagnostics:
            diagnostics = diagnostics[: max_diagnostics - 1]
            diagnostics.append(LocalisationDiagnostic(
                "LIMIT_EXCEEDED", "error", "Localisation catalog diagnostic budget exceeded."
            ))
            return LocalisationCatalog((), tuple(diagnostics), False, snapshot, {})
        diagnostics.extend(document.diagnostics)
        complete = complete and document.complete
        if document.context.snapshot_id != snapshot:
            diagnostics.append(
                LocalisationDiagnostic(
                    "LOC_SNAPSHOT_MISMATCH", "error",
                    "Cannot combine localisation sources from different snapshots.",
                )
            )
            return LocalisationCatalog((), tuple(diagnostics), False, None, {})
        if len(entries) + len(document.entries) > max_entries:
            diagnostics.append(
                LocalisationDiagnostic(
                    "LIMIT_EXCEEDED", "error", "Localisation catalog entry count exceeded."
                )
            )
            return LocalisationCatalog((), tuple(diagnostics), False, snapshot, {})
        for entry in document.entries:
            entries.append(entry)
            index.setdefault((entry.language, entry.key), []).append(entry)
    return LocalisationCatalog(
        tuple(entries), tuple(diagnostics), complete, snapshot,
        {key: tuple(value) for key, value in index.items()},
    )


@dataclass(frozen=True, slots=True)
class LocalisationReferenceSelection:
    key: str
    language_used: str
    source_ref: SourceRef

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "language_used": self.language_used,
            "source_ref": self.source_ref.to_dict(),
        }


@dataclass(frozen=True, slots=True)
class LocalisationResolution:
    key: str
    language_requested: str
    language_used: str | None
    display_value: str
    source_ref: SourceRef | None
    reference_source_refs: tuple[SourceRef, ...]
    fallback: Fallback
    resolution: Resolution
    diagnostics: tuple[LocalisationDiagnostic, ...]
    visits: int
    scanned_bytes: int
    output_bytes: int
    truncated: bool
    reference_selections: tuple[LocalisationReferenceSelection, ...] = ()

    @property
    def ok(self) -> bool:
        return self.resolution == "resolved" and not self.diagnostics

    @property
    def complete(self) -> bool:
        return self.resolution == "resolved" and not self.truncated

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "language_requested": self.language_requested,
            "language_used": self.language_used,
            "display_value": self.display_value,
            "source_ref": None if self.source_ref is None else self.source_ref.to_dict(),
            "reference_source_refs": [ref.to_dict() for ref in self.reference_source_refs],
            "reference_selections": [ref.to_dict() for ref in self.reference_selections],
            "fallback": self.fallback,
            "resolution": self.resolution,
            "diagnostics": [d.to_dict() for d in self.diagnostics],
            "visits": self.visits,
            "scanned_bytes": self.scanned_bytes,
            "output_bytes": self.output_bytes,
            "truncated": self.truncated,
        }


@dataclass(frozen=True, slots=True)
class TechnologyLocalisedName:
    candidate: TechnologyCandidate
    localisation: LocalisationResolution

    @property
    def technology_source_ref(self) -> SourceRef:
        return self.candidate.source_ref


def resolve_technology_name(
    candidate: TechnologyCandidate,
    catalog: LocalisationCatalog,
    requested_language: str = "korean",
    **limits: int,
) -> TechnologyLocalisedName:
    if catalog.snapshot_id is not None and candidate.source_ref.snapshot_id != catalog.snapshot_id:
        raise ValueError("technology and localisation snapshots do not match")
    return TechnologyLocalisedName(
        candidate,
        resolve_localisation(catalog, candidate.game_id, requested_language, **limits),
    )


def resolve_localisation(
    catalog: LocalisationCatalog,
    key: str,
    requested_language: str = "korean",
    *,
    max_depth: int = DEFAULT_MAX_DEPTH,
    max_visits: int = DEFAULT_MAX_VISITS,
    max_scan_bytes: int = DEFAULT_MAX_SCAN_BYTES,
    max_output_bytes: int = DEFAULT_MAX_OUTPUT_BYTES,
    max_diagnostics: int = DEFAULT_MAX_DIAGNOSTICS,
) -> LocalisationResolution:
    """Resolve without assuming mod precedence or evaluating game expressions."""

    for name, limit in (
        ("max_depth", max_depth),
        ("max_visits", max_visits),
        ("max_scan_bytes", max_scan_bytes),
        ("max_output_bytes", max_output_bytes),
        ("max_diagnostics", max_diagnostics),
    ):
        if isinstance(limit, bool) or not isinstance(limit, int) or limit < 1:
            raise ValueError(f"{name} must be a positive integer")
    if max_depth > DEFAULT_MAX_DEPTH:
        raise ValueError("supported max_depth is 64 to avoid interpreter recursion overflow")
    requested = _language(requested_language)
    if not isinstance(key, str) or not key:
        raise ValueError("localisation key must be non-empty")
    if len(key.encode("utf-8")) > max_output_bytes:
        diagnostic = LocalisationDiagnostic(
            "LIMIT_EXCEEDED", "error", "Localisation key exceeds output byte budget."
        )
        return LocalisationResolution(
            key, requested, None, "", None, (), "id", "partial",
            (diagnostic,), 0, 0, 0, True,
        )
    languages = (requested,) if requested == "english" else (requested, "english")

    def select(name: str) -> tuple[LocalisationEntry | None, str | None, str]:
        for language in languages:
            definitions = catalog._index.get((language, name), ())
            if len(definitions) > 1:
                return None, language, "ambiguous"
            if definitions:
                return definitions[0], language, "selected"
        return None, None, "missing"

    selected, used, selection = select(key)
    if selection != "selected":
        if selection == "ambiguous":
            diagnostics = (
                LocalisationDiagnostic(
                    "LOC_DUPLICATE_KEY", "warning",
                    "Multiple definitions exist; no precedence was applied.",
                ),
            )
            fallback: Fallback = "none"
            resolution: Resolution = "ambiguous"
        else:
            diagnostics = (
                LocalisationDiagnostic(
                    "LOC_MISSING_TRANSLATION", "warning",
                    "No requested-language or English translation was found.",
                ),
            )
            fallback = "id"
            resolution = "unresolved"
        if not catalog.complete:
            diagnostics += (
                LocalisationDiagnostic(
                    "LOC_INCOMPLETE_SOURCE", "error",
                    "Some localisation sources were not read completely.",
                ),
            )
            resolution = "partial"
        return LocalisationResolution(
            key, requested, None, key, None, (), fallback, resolution,
            diagnostics, 0, 0, len(key.encode("utf-8")), False,
        )

    assert selected is not None and used is not None
    fallback = "none" if used == requested else "english"
    diagnostics_list: list[LocalisationDiagnostic] = []
    ref_sources: list[SourceRef] = []
    ref_selections: list[LocalisationReferenceSelection] = []
    chunks: list[str] = []
    output_bytes = 0
    visits = 0
    scanned_bytes = 0
    partial = not catalog.complete
    truncated = False
    stopped = False

    def emit(code: str, severity: Literal["warning", "error"], message: str,
             ref: SourceRef | None = None) -> None:
        nonlocal partial, stopped, truncated
        partial = True
        if len(diagnostics_list) >= max_diagnostics - 1:
            truncated = True
            if not any(d.code == "LIMIT_EXCEEDED" for d in diagnostics_list):
                diagnostics_list.append(
                    LocalisationDiagnostic(
                        "LIMIT_EXCEEDED", "error",
                        "Localisation diagnostic budget exhausted.", ref,
                    )
                )
            stopped = True
            return
        diagnostics_list.append(LocalisationDiagnostic(code, severity, message, ref))

    def append(text: str) -> None:
        nonlocal output_bytes, stopped, truncated
        if stopped or not text:
            return
        encoded_size = len(text.encode("utf-8"))
        if encoded_size > max_output_bytes - output_bytes:
            truncated = True
            emit("LIMIT_EXCEEDED", "error", "Expanded localisation output exceeds byte budget.")
            stopped = True
            return
        chunks.append(text)
        output_bytes += encoded_size

    def append_literal(text: str, entry: LocalisationEntry) -> None:
        if not text:
            return
        if ("[" in text and "]" in text) or "£" in text or "§" in text:
            emit(
                "LOC_DYNAMIC_UNSUPPORTED", "warning",
                "Dynamic scope or markup is preserved without interpretation.",
                entry.value_source_ref,
            )
        append(text)

    if not catalog.complete:
        emit(
            "LOC_INCOMPLETE_SOURCE", "error",
            "Some localisation sources were not read completely.",
        )

    def expand(entry: LocalisationEntry, active: tuple[tuple[str, str], ...]) -> None:
        nonlocal visits, scanned_bytes, truncated, stopped
        if stopped:
            return
        identifier = (entry.language, entry.key)
        placeholder = "$" + entry.key + "$"
        if identifier in active:
            emit("LOC_CYCLE", "error", "Static localisation reference cycle.", entry.source_ref)
            append(placeholder)
            return
        if len(active) >= max_depth:
            truncated = True
            emit("LIMIT_EXCEEDED", "error", "Localisation depth limit exceeded.", entry.source_ref)
            append(placeholder)
            return
        if visits >= max_visits:
            truncated = True
            emit("LIMIT_EXCEEDED", "error", "Localisation visit limit exceeded.", entry.source_ref)
            append(placeholder)
            return
        size = entry.value_source_ref.byte_end - entry.value_source_ref.byte_start
        if size > max_scan_bytes - scanned_bytes:
            truncated = True
            emit("LIMIT_EXCEEDED", "error", "Localisation scan budget exceeded.", entry.source_ref)
            append(placeholder)
            return
        visits += 1
        scanned_bytes += size
        path = (*active, identifier)
        if entry.has_unsupported_escape:
            emit(
                "LOC_UNSUPPORTED_ESCAPE", "warning",
                "Unsupported escape was retained literally.", entry.value_source_ref,
            )
        value = entry.display_value
        cursor = 0
        while not stopped and cursor < len(value):
            pos = value.find("$", cursor)
            if pos == -1:
                append_literal(value[cursor:], entry)
                break
            append_literal(value[cursor:pos], entry)
            if stopped:
                break
            end = value.find("$", pos + 1)
            if end == -1:
                emit(
                    "LOC_DYNAMIC_UNSUPPORTED", "warning",
                    "Unmatched dollar expression was retained literally.", entry.value_source_ref,
                )
                append(value[pos:])
                break
            target = value[pos + 1 : end]
            raw_ref = value[pos : end + 1]
            if _REFERENCE_KEY.fullmatch(target) is None:
                emit(
                    "LOC_DYNAMIC_UNSUPPORTED", "warning",
                    "Unsupported dollar expression was preserved.", entry.value_source_ref,
                )
                append(raw_ref)
            else:
                ref, _, status = select(target)
                if status == "ambiguous":
                    emit(
                        "LOC_DUPLICATE_REFERENCE", "warning",
                        "Referenced key has multiple definitions.", entry.value_source_ref,
                    )
                    append(raw_ref)
                elif status == "missing":
                    emit(
                        "LOC_MISSING_REFERENCE", "warning",
                        "Referenced key does not exist.", entry.value_source_ref,
                    )
                    append(raw_ref)
                else:
                    assert ref is not None
                    ref_sources.append(ref.source_ref)
                    ref_selections.append(LocalisationReferenceSelection(target, ref.language, ref.source_ref))
                    expand(ref, path)
            cursor = end + 1

    expand(selected, ())
    return LocalisationResolution(
        key=key, language_requested=requested, language_used=used,
        display_value="".join(chunks), source_ref=selected.source_ref,
        reference_source_refs=tuple(ref_sources), fallback=fallback,
        resolution="partial" if partial else "resolved",
        diagnostics=tuple(diagnostics_list), visits=visits,
        scanned_bytes=scanned_bytes, output_bytes=output_bytes, truncated=truncated,
        reference_selections=tuple(ref_selections),
    )
