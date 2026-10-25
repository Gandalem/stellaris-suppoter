"""Dedicated, bounded reader for the supported Stellaris localisation subset.

This is not a YAML parser. Entries retain source spans and duplicate occurrences.
Unrecognised syntax is reported, never turned into an invented translation.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from io import StringIO
from pathlib import PurePosixPath
from typing import Literal

from stellaris_supporter.domain.technology import SourceContext, SourceRef

MAX_LOCALISATION_BYTES = 16 * 1024 * 1024
MAX_LOCALISATION_LINE_BYTES = 1024 * 1024
MAX_LOCALISATION_ENTRIES = 100_000
MAX_LOCALISATION_DIAGNOSTICS = 1_000

_HEADER = re.compile(r"[ \t]*l_([a-z][a-z0-9_]*):[ \t]*(?:#.*)?\Z")
_KEY_INITIAL = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz_"
_KEY_REST = _KEY_INITIAL + "0123456789.-"


@dataclass(frozen=True, slots=True)
class _EntryPrefix:
    key: str
    marker: str | None
    key_start: int
    opening: int


def _scan_entry_prefix(line: str) -> _EntryPrefix | None:
    """Scan once left-to-right; no overlapping optional whitespace branches.

    Each index only moves forward. Even a very long malformed no-quote line
    requires at most len(line) + a constant number of indexed character reads.
    """

    i = 0
    length = len(line)
    while i < length and line[i] in " \t":
        i += 1
    key_start = i
    if i >= length or line[i] not in _KEY_INITIAL:
        return None
    i += 1
    while i < length and line[i] in _KEY_REST:
        i += 1
    key_end = i
    while i < length and line[i] in " \t":
        i += 1
    if i >= length or line[i] != ":":
        return None
    i += 1
    while i < length and line[i] in " \t":
        i += 1
    marker_start = i
    while i < length and "0" <= line[i] <= "9":
        i += 1
    marker = line[marker_start:i] if i > marker_start else None
    while i < length and line[i] in " \t":
        i += 1
    if i >= length or line[i] != '"':
        return None
    return _EntryPrefix(line[key_start:key_end], marker, key_start, i)
Severity = Literal["info", "warning", "error"]


@dataclass(frozen=True, slots=True)
class LocalisationDiagnostic:
    code: str
    severity: Severity
    message: str
    source_ref: SourceRef | None = None
    column: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
            "source_ref": None if self.source_ref is None else self.source_ref.to_dict(),
            "column": self.column,
        }


@dataclass(frozen=True, slots=True)
class LocalisationComment:
    source_ref: SourceRef
    column_start: int
    _source: bytes = field(repr=False, compare=False)

    @property
    def raw(self) -> str:
        return self.source_ref.raw_text(self._source)


@dataclass(frozen=True, slots=True)
class LocalisationHeader:
    language: str
    source_ref: SourceRef
    column_start: int
    _source: bytes = field(repr=False, compare=False)

    @property
    def raw(self) -> str:
        return self.source_ref.raw_text(self._source)


@dataclass(frozen=True, slots=True)
class LocalisationEntry:
    key: str
    language: str
    marker: str | None
    occurrence: int
    source_ref: SourceRef
    value_source_ref: SourceRef
    quoted_value_source_ref: SourceRef
    column_start: int
    column_end: int
    value_column_start: int
    has_unsupported_escape: bool
    _source: bytes = field(repr=False, compare=False)
    _game_escapes: bool = field(default=False, repr=False, compare=False)

    @property
    def raw_value(self) -> str:
        """Original bytes between the quotes, without normalisation."""

        return self.value_source_ref.raw_text(self._source)

    @property
    def quoted_value(self) -> str:
        return self.quoted_value_source_ref.raw_text(self._source)

    @property
    def display_value(self) -> str:
        """Only the two supported lexical escapes are decoded; no game evaluation."""

        raw = self.raw_value
        if "\\" not in raw:
            return raw
        result = StringIO()
        start = 0
        i = 0
        while i < len(raw):
            if raw[i] == "\\" and i + 1 < len(raw):
                result.write(raw[start:i])
                next_char = raw[i + 1]
                if self._game_escapes and next_char in {"n", "t", "r"}:
                    result.write({"n": "\n", "t": "\t", "r": "\r"}[next_char])
                else:
                    result.write(next_char if next_char in {'"', "\\"} else raw[i : i + 2])
                i += 2
                start = i
            else:
                i += 1
        result.write(raw[start:])
        return result.getvalue()

    def to_dict(self) -> dict[str, object]:
        return {
            "key": self.key,
            "language": self.language,
            "marker": self.marker,
            "occurrence": self.occurrence,
            "source_ref": self.source_ref.to_dict(),
            "value_source_ref": self.value_source_ref.to_dict(),
            "quoted_value_source_ref": self.quoted_value_source_ref.to_dict(),
            "column_start": self.column_start,
            "column_end": self.column_end,
            "value_column_start": self.value_column_start,
            "has_unsupported_escape": self.has_unsupported_escape,
        }


@dataclass(frozen=True, slots=True)
class LocalisationDocument:
    entries: tuple[LocalisationEntry, ...]
    headers: tuple[LocalisationHeader, ...]
    comments: tuple[LocalisationComment, ...]
    unknown_spans: tuple[SourceRef, ...]
    diagnostics: tuple[LocalisationDiagnostic, ...]
    complete: bool
    context: SourceContext
    _source: bytes = field(repr=False, compare=False)

    @property
    def ok(self) -> bool:
        return self.complete and not any(d.severity == "error" for d in self.diagnostics)

    def raw_bytes(self, span: SourceRef) -> bytes:
        if (
            span.snapshot_id != self.context.snapshot_id
            or span.source_kind != self.context.source_kind
            or span.source_id != self.context.source_id
            or span.relative_path != self.context.relative_path
            or span.file_sha256 != self.context.file_sha256
        ):
            raise ValueError("source reference does not belong to this document")
        return span.raw_bytes(self._source)


def _validate_context(context: SourceContext) -> None:
    relative = context.relative_path
    if (
        not context.snapshot_id
        or not context.source_id
        or not relative
        or "\\" in relative
        or "\x00" in relative
        or ":" in relative
        or PurePosixPath(relative).is_absolute()
        or any(part in {"", ".", ".."} for part in relative.split("/"))
    ):
        raise ValueError("localisation source context requires a safe relative path")
    if len(context.file_sha256) != 64 or any(c not in "0123456789abcdef" for c in context.file_sha256):
        raise ValueError("localisation source context requires a SHA-256 digest")


def _ref(
    context: SourceContext,
    start: int,
    end: int,
    line_start: int,
    line_end: int | None = None,
) -> SourceRef:
    return SourceRef(
        snapshot_id=context.snapshot_id,
        source_kind=context.source_kind,
        source_id=context.source_id,
        relative_path=context.relative_path,
        file_sha256=context.file_sha256,
        byte_start=start,
        byte_end=end,
        line_start=line_start,
        line_end=line_start if line_end is None else line_end,
    )


def _end_of_quote(line: str, opening: int, *, game_compatibility: bool = False) -> tuple[int | None, bool]:
    i = opening + 1
    unsupported = False
    while i < len(line):
        ch = line[i]
        if ch == '"':
            tail = line[i+1:].lstrip(" \t")
            if not game_compatibility or not tail or tail.startswith("#"):
                return i, unsupported
        if ch == "\\":
            if i + 1 >= len(line):
                return None, unsupported
            if line[i + 1] not in ({'"', "\\", "n", "t", "r"} if game_compatibility else {'"', "\\"}):
                unsupported = True
            i += 2
        else:
            i += 1
    return None, unsupported


class _StreamRecords:
    def __init__(self, sink, kind):
        self.sink, self.kind, self.count = sink, kind, 0

    def append(self, value):
        self.count += 1
        self.sink(self.kind, value)

    def __len__(self):
        return self.count

    def __iter__(self):
        return iter(())


class _DiagnosticSamples(list):
    def __init__(self, counts):
        super().__init__()
        self.counts = counts

    def append(self, value):
        key = value.code + ":" + value.severity
        self.counts[key] = self.counts.get(key, 0) + 1
        if self.counts[key] <= 3:
            super().append(value)


def parse_localisation(
    source: bytes,
    context: SourceContext,
    *,
    max_bytes: int = MAX_LOCALISATION_BYTES,
    max_line_bytes: int = MAX_LOCALISATION_LINE_BYTES,
    max_entries: int = MAX_LOCALISATION_ENTRIES,
    max_records: int = MAX_LOCALISATION_ENTRIES,
    max_diagnostics: int = MAX_LOCALISATION_DIAGNOSTICS,
    sink=None,
    diagnostic_counts=None,
    game_compatibility: bool = False,
) -> LocalisationDocument:
    """Read one verified source file; all spans are original byte offsets.

    Input errors return diagnostics. Invalid policy/context arguments raise ValueError.
    """

    for name, value in (
        ("max_bytes", max_bytes),
        ("max_line_bytes", max_line_bytes),
        ("max_entries", max_entries),
        ("max_records", max_records),
        ("max_diagnostics", max_diagnostics),
    ):
        if isinstance(value, bool) or not isinstance(value, int) or value < 1:
            raise ValueError(f"{name} must be a positive integer")

    _validate_context(context)
    entries: list[LocalisationEntry] = []
    headers: list[LocalisationHeader] = []
    comments: list[LocalisationComment] = []
    unknown: list[SourceRef] = []
    diagnostics: list[LocalisationDiagnostic] = []
    complete = True

    if sink is not None:
        entries = _StreamRecords(sink, "entry")
        headers = _StreamRecords(sink, "header")
        comments = _StreamRecords(sink, "comment")
        unknown = _StreamRecords(sink, "unknown")
    if diagnostic_counts is not None:
        diagnostics = _DiagnosticSamples(diagnostic_counts)

    def make_result() -> LocalisationDocument:
        return LocalisationDocument(
            entries=tuple(entries),
            headers=tuple(headers),
            comments=tuple(comments),
            unknown_spans=tuple(unknown),
            diagnostics=tuple(diagnostics),
            complete=complete,
            context=context,
            _source=source,
        )

    def emit(
        code: str,
        severity: Severity,
        message: str,
        span: SourceRef | None = None,
        column: int | None = None,
    ) -> bool:
        nonlocal complete
        if len(diagnostics) >= max_diagnostics - 1:
            if not any(d.code == "LIMIT_EXCEEDED" for d in diagnostics):
                diagnostics.append(
                    LocalisationDiagnostic(
                        "LIMIT_EXCEEDED",
                        "error",
                        "Localisation diagnostic count limit exceeded.",
                        span,
                        column,
                    )
                )
            complete = False
            return False
        diagnostics.append(LocalisationDiagnostic(code, severity, message, span, column))
        if severity == "error":
            complete = False
        return True

    def reserve_record(span: SourceRef) -> bool:
        """A physical line can produce two records: charge before each append."""

        if len(entries) + len(headers) + len(comments) + len(unknown) >= max_records:
            emit("LIMIT_EXCEEDED", "error", "Localisation record count limit exceeded.", span)
            return False
        return True

    if len(source) > max_bytes:
        emit("LIMIT_EXCEEDED", "error", "Localisation input byte limit exceeded.")
        return make_result()

    if hashlib.sha256(source).hexdigest() != context.file_sha256:
        emit("LOC_SOURCE_MISMATCH", "error", "Localisation source SHA-256 does not match context.")
        return make_result()

    try:
        source.decode("utf-8", errors="strict")
    except UnicodeDecodeError as exc:
        line = source.count(b"\n", 0, exc.start) + 1
        previous_lf = source.rfind(b"\n", 0, exc.start)
        line_bytes = source[previous_lf + 1 : exc.start]
        # The prefix before the first invalid byte is necessarily valid UTF-8.
        column = len(line_bytes.decode("utf-8-sig")) + 1
        emit(
            "ENCODING_ERROR",
            "error",
            "Localisation source is not valid UTF-8.",
            _ref(context, exc.start, exc.end, line),
            column,
        )
        return make_result()

    language: str | None = None
    occurrences: dict[tuple[str, str], int] = {}
    start = 0
    line_no = 1
    while start < len(source):
        lf = source.find(b"\n", start)
        next_start = len(source) if lf < 0 else lf + 1
        physical_end = len(source) if lf < 0 else lf
        if physical_end > start and source[physical_end - 1] == 13:
            physical_end -= 1
        base = 3 if start == 0 and source.startswith(b"\xef\xbb\xbf") else 0
        body_start = start + base
        line_ref = _ref(context, body_start, physical_end, line_no)
        if physical_end - start > max_line_bytes:
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            emit("LIMIT_EXCEEDED", "error", "Localisation line byte limit exceeded.", line_ref)
            break

        text = source[body_start:physical_end].decode("utf-8")
        stripped = text.strip()
        if not stripped:
            start, line_no = next_start, line_no + 1
            continue

        if stripped.startswith("#"):
            if not reserve_record(line_ref):
                break
            pos = text.index("#")
            comments.append(
                LocalisationComment(
                    _ref(context, body_start + len(text[:pos].encode("utf-8")), physical_end, line_no),
                    pos + 1,
                    source,
                )
            )
            start, line_no = next_start, line_no + 1
            continue

        header = _HEADER.fullmatch(text)
        if header is not None:
            if not reserve_record(line_ref):
                break
            language = header.group(1)
            header_end = text.find("#") if "#" in text else len(text)
            header_start = len(text) - len(text.lstrip(" \t"))
            headers.append(
                LocalisationHeader(
                    language,
                    _ref(
                        context,
                        body_start + len(text[:header_start].encode("utf-8")),
                        body_start + len(text[:header_end].encode("utf-8")),
                        line_no,
                    ),
                    header_start + 1,
                    source,
                )
            )
            if "#" in text:
                if not reserve_record(line_ref):
                    break
                pos = text.index("#")
                comments.append(
                    LocalisationComment(
                        _ref(context, body_start + len(text[:pos].encode("utf-8")), physical_end, line_no),
                        pos + 1,
                        source,
                    )
                )
            start, line_no = next_start, line_no + 1
            continue

        match = _scan_entry_prefix(text)
        if stripped.startswith("l_") and match is None:
            language = None
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            if not emit("LOC_INVALID_HEADER", "error", "Invalid localisation language header.", line_ref):
                break
            start, line_no = next_start, line_no + 1
            continue

        if match is None:
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            code = "LOC_MISSING_HEADER" if language is None else "LOC_UNSUPPORTED_SYNTAX"
            if not emit(code, "error", "Unsupported localisation entry syntax.", line_ref):
                break
            start, line_no = next_start, line_no + 1
            continue

        if language is None:
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            if not emit("LOC_MISSING_HEADER", "error", "Entry precedes a language header.", line_ref):
                break
            start, line_no = next_start, line_no + 1
            continue

        opening = match.opening
        closing, unsupported_escape = _end_of_quote(text, opening, game_compatibility=game_compatibility)
        if closing is None:
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            if not emit("LOC_UNCLOSED_STRING", "error", "Unterminated localisation quoted value.", line_ref):
                break
            start, line_no = next_start, line_no + 1
            continue

        trailing = text[closing + 1 :].lstrip(" \t")
        if trailing and not trailing.startswith("#"):
            if not reserve_record(line_ref):
                break
            unknown.append(line_ref)
            if not emit("LOC_TRAILING_SYNTAX", "error", "Unsupported syntax after quoted value.", line_ref):
                break
            start, line_no = next_start, line_no + 1
            continue

        if len(entries) >= max_entries:
            emit("LIMIT_EXCEEDED", "error", "Localisation entry count limit exceeded.", line_ref)
            break

        if not reserve_record(line_ref):
            break
        key = match.key
        occurrence_key = (language, key)
        occurrence = occurrences.get(occurrence_key, 0) + 1
        occurrences[occurrence_key] = occurrence

        def byte_at(index: int) -> int:
            return body_start + len(text[:index].encode("utf-8"))

        key_start = match.key_start
        entry_ref = _ref(context, byte_at(key_start), byte_at(closing + 1), line_no)
        value_ref = _ref(context, byte_at(opening + 1), byte_at(closing), line_no)
        quoted_ref = _ref(context, byte_at(opening), byte_at(closing + 1), line_no)
        entries.append(
            LocalisationEntry(
                key=key,
                language=language,
                marker=match.marker,
                occurrence=occurrence,
                source_ref=entry_ref,
                value_source_ref=value_ref,
                quoted_value_source_ref=quoted_ref,
                column_start=key_start + 1,
                column_end=closing + 2,
                value_column_start=opening + 2,
                has_unsupported_escape=unsupported_escape,
                _source=source,
                _game_escapes=game_compatibility,
            )
        )
        if occurrence > 1 and not emit(
            "LOC_DUPLICATE_KEY",
            "warning",
            "Repeated localisation key requires explicit conflict resolution.",
            entry_ref,
            key_start + 1,
        ):
            break
        if unsupported_escape and not emit(
            "LOC_UNSUPPORTED_ESCAPE",
            "warning",
            "Unsupported escape is preserved literally.",
            value_ref,
            opening + 2,
        ):
            break
        if trailing.startswith("#"):
            if not reserve_record(line_ref):
                break
            pos = text.index("#", closing + 1)
            comments.append(
                LocalisationComment(
                    _ref(context, byte_at(pos), physical_end, line_no),
                    pos + 1,
                    source,
                )
            )
        start, line_no = next_start, line_no + 1
    return make_result()
