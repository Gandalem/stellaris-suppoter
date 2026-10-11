"""Staging, validation, immutable reads and atomic SQLite snapshot activation.

No parser, game file or network operations happen here. All SourceRefs are
checked against manifest bytes. A build is committed as 'building' first to
make interrupted work observable after restart. The active pointer is updated
only after *all* cached bytes and foreign keys are checked within a bounded
BEGIN IMMEDIATE transaction.
"""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
from array import array
from bisect import bisect_left
from collections import OrderedDict
from collections.abc import Callable
from contextlib import closing, contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from stellaris_supporter.domain import SourceRef, TechnologyAdaptResult, TechnologyCandidate
from stellaris_supporter.localisation import (
    LocalisationDocument,
    LocalisationEntry,
    TechnologyLocalisedName,
)
from stellaris_supporter.storage.cache import (
    BlobCache,
    _ensure_directory,
    _is_unsafe_link,
    live_source_relative_path,
    verify_live_source,
)
from stellaris_supporter.storage.identity import (
    MAX_POLICY_JSON_BYTES,
    MAX_SOURCE_BYTES,
    SCHEMA_VERSION,
    SnapshotError,
    SnapshotIdentity,
    SnapshotPolicy,
    SourceDescriptor,
    SourceFileInput,
    snapshot_identity,
    storage_json,
)
from stellaris_supporter.storage.schema import check_schema, connect, initialise_schema

MAX_RECORDS = 100_000
MAX_JSON_BYTES = 1024 * 1024
MAX_DIAGNOSTICS = 10_000
_SOURCE_REF_KEYS = {
    "snapshot_id", "source_kind", "source_id", "relative_path",
    "file_sha256", "byte_start", "byte_end", "line_start", "line_end",
}
_CANCEL = Callable[[], bool]
_HOOK = Callable[[], None]


def _utc() -> str:
    return datetime.now(UTC).isoformat().replace("+00:00", "Z")


def _db_error(exc: sqlite3.DatabaseError) -> SnapshotError:
    message = str(exc).lower()
    if "locked" in message or "busy" in message:
        return SnapshotError("SQLITE_BUSY", "Snapshot database is held by another writer.")
    if "full" in message or "disk" in message or "readonly" in message:
        return SnapshotError("SQLITE_WRITE_ERROR", "Snapshot database write failed.")
    return SnapshotError("SQLITE_ERROR", "Snapshot database operation failed.")


@contextmanager
def _immediate(conn: sqlite3.Connection):
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield
        conn.execute("COMMIT")
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise


def _as_json(obj: Any) -> str:
    return storage_json(obj, max_bytes=MAX_JSON_BYTES).decode("utf-8")


def _validate_ref(
    ref: SourceRef | dict[str, Any],
    snapshot_id: str,
    descriptors: dict[tuple[str, str, str], SourceDescriptor],
) -> None:
    value = ref.to_dict() if isinstance(ref, SourceRef) else ref
    if value.get("snapshot_id") != snapshot_id:
        raise SnapshotError("SOURCE_CHANGED", "SourceRef belongs to a different snapshot.")
    key = (value.get("source_kind"), value.get("source_id"), value.get("relative_path"))
    item = descriptors.get(key)
    if item is None or item.file_sha256 != value.get("file_sha256"):
        raise SnapshotError("SOURCE_CHANGED", "SourceRef does not match the source manifest.")
    start, end = value.get("byte_start"), value.get("byte_end")
    line_start, line_end = value.get("line_start"), value.get("line_end")
    if (
        isinstance(start, bool) or not isinstance(start, int)
        or isinstance(end, bool) or not isinstance(end, int)
        or start < 0 or end < start or end > item.size
        or isinstance(line_start, bool) or not isinstance(line_start, int)
        or isinstance(line_end, bool) or not isinstance(line_end, int)
        or line_start < 1 or line_end < line_start
    ):
        raise SnapshotError("SOURCE_CHANGED", "SourceRef has an invalid original byte span.")


def _validate_payload_refs(
    obj: Any, sid: str, manifest: dict[tuple[str, str, str], SourceDescriptor]
) -> None:
    """Walk only bounded output JSON; verify every nested SourceRef is in manifest."""
    remaining = MAX_RECORDS

    def visit(value: Any, depth: int) -> None:
        nonlocal remaining
        remaining -= 1
        if remaining < 0 or depth > 280:
            raise SnapshotError("LIMIT_EXCEEDED", "Provenance traversal budget exceeded.")
        if isinstance(value, dict):
            if _SOURCE_REF_KEYS <= value.keys():
                _validate_ref(value, sid, manifest)
            for child in value.values():
                visit(child, depth + 1)
        elif isinstance(value, list):
            for child in value:
                visit(child, depth + 1)

    visit(obj, 0)


def _validate_own_source(
    actual: bytes, ref: SourceRef, manifest_data: dict[tuple[str, str, str], bytes]
) -> None:
    key = (ref.source_kind, ref.source_id, ref.relative_path)
    expected = manifest_data.get(key)
    if expected is None or actual != expected:
        raise SnapshotError("SOURCE_CHANGED", "Record source bytes differ from manifest.")


def _entry_data(entry: LocalisationEntry) -> dict[str, Any]:
    return {
        "key": entry.key,
        "language": entry.language,
        "marker": entry.marker,
        "occurrence": entry.occurrence,
        "source_ref": entry.source_ref.to_dict(),
        "value_source_ref": entry.value_source_ref.to_dict(),
        "quoted_value_source_ref": entry.quoted_value_source_ref.to_dict(),
        "column_start": entry.column_start,
        "column_end": entry.column_end,
        "value_column_start": entry.value_column_start,
        "raw_value": entry.raw_value,
        "display_value": entry.display_value,
        "has_unsupported_escape": entry.has_unsupported_escape,
    }


@dataclass(frozen=True, slots=True)
class SnapshotSummary:
    snapshot_id: str
    content_hash: str
    status: str
    game_version: str | None



# Per-answer verified content cache: source bytes plus compact newline indices.
# 16 MiB maximum physical blob, 1,000,000 newline positions (4 MiB), and
# 24 MiB retained verified buffers across ALL files of one answer.
MAX_ANSWER_CACHE_BYTES = 24 * 1024 * 1024
MAX_ANSWER_NEWLINES = 1_000_000


class _VerifiedCitationReader:
    """Read-only, snapshot-pinned, bounded LRU of fully SHA-verified blobs.

    One SQLite read transaction fixes the source-file manifest for the answer.
    Each unique (SHA, size) is rehashed by BlobCache.read exactly once while
    resident; repeated SourceRefs reuse the exact verified bytes and binary-
    searched original newline positions rather than rescanning whole files.
    """

    def __init__(
        self, repository: SnapshotRepository, conn: sqlite3.Connection, sid: str
    ) -> None:
        self.repository = repository
        self.conn = conn
        self.snapshot_id = sid
        self._blobs: OrderedDict[
            tuple[str, int], tuple[bytes, array, int]
        ] = OrderedDict()
        self._bytes = 0

    def _evict(self) -> None:
        _, (_, _, charge) = self._blobs.popitem(last=False)
        self._bytes -= charge

    def _verified(self, digest: str, size: int) -> tuple[bytes, array]:
        key = (digest, size)
        if key in self._blobs:
            self._blobs.move_to_end(key)
            data, newlines, _ = self._blobs[key]
            return data, newlines
        if size < 0 or size > MAX_SOURCE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Cached source exceeds file budget.")
        while self._blobs and self._bytes + size > MAX_ANSWER_CACHE_BYTES:
            self._evict()
        data = self.repository.cache.read(digest, size)
        newlines = array("I")
        # Deterministic upper bound on auxiliary line-index memory.
        start = 0
        while True:
            pos = data.find(b"\n", start)
            if pos < 0:
                break
            if len(newlines) >= MAX_ANSWER_NEWLINES:
                raise SnapshotError("LIMIT_EXCEEDED", "Citation line-index limit exceeded.")
            newlines.append(pos)
            start = pos + 1
        charge = len(data) + len(newlines) * newlines.itemsize
        if charge > MAX_ANSWER_CACHE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Citation blob exceeds cache budget.")
        while self._blobs and self._bytes + charge > MAX_ANSWER_CACHE_BYTES:
            self._evict()
        self._blobs[key] = (data, newlines, charge)
        self._bytes += charge
        return data, newlines

    def read(self, ref: SourceRef) -> bytes:
        if (
            not isinstance(ref, SourceRef) or ref.snapshot_id != self.snapshot_id
            or any(isinstance(x, bool) or not isinstance(x, int) for x in (
                ref.byte_start, ref.byte_end, ref.line_start, ref.line_end
            ))
        ):
            raise SnapshotError("SOURCE_CHANGED", "Citation is not in the pinned snapshot.")
        row = self.conn.execute(
            "SELECT file_sha256,cache_sha256,byte_size FROM source_files "
            "WHERE snapshot_id=? AND source_kind=? AND source_id=? AND relative_path=?",
            (self.snapshot_id, ref.source_kind, ref.source_id, ref.relative_path),
        ).fetchone()
        if (
            row is None or ref.file_sha256 != row["file_sha256"]
            or row["cache_sha256"] != row["file_sha256"]
            or ref.byte_start < 0 or ref.byte_start >= ref.byte_end
            or ref.byte_end > row["byte_size"]
        ):
            raise SnapshotError("SOURCE_CHANGED", "Citation source or byte span differs.")
        data, newlines = self._verified(row["cache_sha256"], row["byte_size"])
        start_line = bisect_left(newlines, ref.byte_start) + 1
        end_line = bisect_left(newlines, ref.byte_end - 1) + 1
        if ref.line_start != start_line or ref.line_end != end_line:
            raise SnapshotError("SOURCE_CHANGED", "Citation line positions differ.")
        span = data[ref.byte_start:ref.byte_end]
        try:
            span.decode("utf-8", errors="strict")
        except UnicodeError as exc:
            raise SnapshotError("SOURCE_CHANGED", "Citation cuts a UTF-8 codepoint.") from exc
        return span


class SnapshotRepository:
    def __init__(self, data_dir: Path, *, game_root: Path | None = None) -> None:
        self.data_dir = Path(os.path.abspath(data_dir))
        self.game_root = None if game_root is None else Path(os.path.abspath(game_root))
        if not Path(data_dir).is_absolute():
            raise SnapshotError("PATH_REJECTED", "Private data_dir must be absolute.")
        if self.game_root is not None:
            if self.data_dir.is_relative_to(self.game_root) or self.game_root.is_relative_to(self.data_dir):
                raise SnapshotError("PATH_REJECTED", "Private data and game roots overlap.")
            if _is_unsafe_link(self.game_root):
                raise SnapshotError("PATH_REJECTED", "Game root is a link.")
        _ensure_directory(self.data_dir)
        self.db_path = self.data_dir / "snapshots.sqlite3"
        self._ensure_db_paths()
        exists = self.db_path.exists()
        if exists:
            # Preflight in read-only mode, before WAL settings can write to an
            # unsupported future schema.
            with closing(connect(self.db_path, read_only=True)) as conn:
                check_schema(conn)
        with closing(connect(self.db_path)) as conn:
            initialise_schema(conn, new_db=not exists)
        self.cache = BlobCache(self.data_dir / "cache")
        # Do not automatically invalidate an active build owned by another process.
        # recover_interrupted() is an explicit, lock-protected operator action.

    def _ensure_db_paths(self) -> None:
        for path in (self.db_path, Path(str(self.db_path) + "-wal"),
                     Path(str(self.db_path) + "-shm")):
            if path.is_symlink() or (path.exists() and _is_unsafe_link(path)):
                raise SnapshotError("PATH_REJECTED", "Database file path is unsafe.")

    @contextmanager
    def _connection(self, *, read_only: bool = False):
        self._ensure_db_paths()
        try:
            conn = connect(self.db_path, read_only=read_only)
        except SnapshotError:
            raise
        try:
            check_schema(conn, full_integrity=not read_only)
            yield conn
        except sqlite3.DatabaseError as exc:
            raise _db_error(exc) from exc
        finally:
            conn.close()

    def recover_interrupted(self) -> tuple[str, ...]:
        with self._connection() as conn, _immediate(conn):
            rows = conn.execute(
                "SELECT snapshot_id FROM snapshots WHERE status='building' "
                "ORDER BY snapshot_id"
            ).fetchall()
            conn.execute(
                "UPDATE snapshots SET status='failed', diagnostics_json=? "
                "WHERE status='building'",
                ('[{"code":"INTERRUPTED_BUILD","severity":"error",'
                 '"message":"Previous staging did not complete."}]',),
            )
            return tuple(row[0] for row in rows)

    def _live_root_hash(self) -> str:
        if self.game_root is None:
            raise SnapshotError("PATH_REJECTED", "Live sources require an explicit game root.")
        # Private DB binding, never included in SnapshotPolicy, snapshot_id or evidence.
        spelling = os.path.normcase(os.path.abspath(self.game_root))
        return hashlib.sha256(os.fsencode(spelling)).hexdigest()

    def _check_live(
        self, source: SourceFileInput, descriptor: SourceDescriptor
    ) -> tuple[str | None, str | None]:
        if source.live_path is None:
            if source.source_kind != "synthetic":
                raise SnapshotError(
                    "SOURCE_UNVERIFIED", "Real sources require an allowed live path."
                )
            return None, None
        if self.game_root is None:
            raise SnapshotError("PATH_REJECTED", "Live sources require an explicit game root.")
        physical_relative = verify_live_source(
            source.live_path, self.game_root, descriptor.file_sha256, descriptor.size
        )
        return self._live_root_hash(), physical_relative

    def stage_from_results(
        self,
        sources: tuple[SourceFileInput, ...],
        policy: SnapshotPolicy,
        *,
        technology_results: tuple[TechnologyAdaptResult, ...] = (),
        localisation_documents: tuple[LocalisationDocument, ...] = (),
        localised_names: tuple[TechnologyLocalisedName, ...] = (),
        cancel: _CANCEL | None = None,
    ) -> SnapshotIdentity:
        """Safe adapter/reader boundary: preserve original diagnostics/completeness.

        The low-level stage() accepts pre-validated records. This entrypoint
        accepts full ParseResult-derived and LocalisationDocument-derived
        products so an encoding/limit/unknown error cannot become an
        unexplained successful empty snapshot merely by dropping diagnostics.
        """
        expected = snapshot_identity(sources, policy)
        descriptions = {d.key: d for d in expected.sources}
        original = {s.descriptor().key: s.data for s in sources}
        for doc in localisation_documents:
            context = doc.context
            key = (context.source_kind, context.source_id, context.relative_path)
            descriptor = descriptions.get(key)
            if (
                context.snapshot_id != expected.snapshot_id or descriptor is None
                or descriptor.file_sha256 != context.file_sha256
                or doc._source != original.get(key)
            ):
                raise SnapshotError(
                    "SOURCE_CHANGED", "Localisation document and input manifest differ."
                )
        candidates = tuple(c for result in technology_results for c in result.candidates)
        entries = tuple(entry for doc in localisation_documents for entry in doc.entries)
        diagnostics = tuple(
            diagnostic
            for result in technology_results for diagnostic in result.diagnostics
        ) + tuple(
            diagnostic for doc in localisation_documents for diagnostic in doc.diagnostics
        )
        partial = (
            any(not result.complete or not result.ok for result in technology_results)
            or any(not doc.complete or not doc.ok for doc in localisation_documents)
        )
        return self.stage(
            sources, policy, candidates=candidates, entries=entries,
            localised_names=localised_names, diagnostics=diagnostics,
            partial=partial, cancel=cancel,
        )

    def stage(
        self,
        sources: tuple[SourceFileInput, ...],
        policy: SnapshotPolicy,
        *,
        candidates: tuple[TechnologyCandidate, ...] = (),
        entries: tuple[LocalisationEntry, ...] = (),
        localised_names: tuple[TechnologyLocalisedName, ...] = (),
        diagnostics: tuple[Any, ...] = (),
        partial: bool = False,
        cancel: _CANCEL | None = None,
        before_ready: _HOOK | None = None,
    ) -> SnapshotIdentity:
        """Write a new immutable snapshot. Never changes the active pointer.

        An identical already-ready snapshot is not overwritten. Clients may
        explicitly activate it again; failed/building IDs require new policy
        or source content rather than unsafe partial replacement.
        """
        identity = snapshot_identity(sources, policy)
        if policy.schema_version != SCHEMA_VERSION:
            raise SnapshotError("SCHEMA_VERSION_UNSUPPORTED", "Repository cannot write this schema.")
        if len(identity.policy_json.encode("utf-8")) > MAX_POLICY_JSON_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Policy exceeds its identity byte budget.")
        sid = identity.snapshot_id
        by_key = {d.key: d for d in identity.sources}
        source_by_key = {item.descriptor().key: item for item in sources}
        bytes_by_key = {key: item.data for key, item in source_by_key.items()}
        relation_count = sum(len(candidate.prerequisites) for candidate in candidates)
        if (len(candidates) + len(entries) + relation_count > MAX_RECORDS
                or len(diagnostics) > MAX_DIAGNOSTICS):
            raise SnapshotError("LIMIT_EXCEEDED", "Indexed record count exceeds budget.")
        for key, source in source_by_key.items():
            self._check_live(source, by_key[key])
        if cancel is not None and cancel():
            raise SnapshotError("CANCELLED", "Staging was cancelled before starting.")

        with self._connection() as conn, _immediate(conn):
            if conn.execute(
                "SELECT 1 FROM snapshots WHERE snapshot_id=?", (sid,)
            ).fetchone():
                raise SnapshotError("SNAPSHOT_EXISTS", "Snapshot ID already exists; no overwrite.")
            # Commit the exact bounded policy that was hashed, not a second
            # read of caller-owned mutable Mapping fields.
            fields = json.loads(identity.policy_json)
            conn.execute(
                "INSERT INTO snapshots("
                "snapshot_id,content_hash,schema_version,parser_version,adapter_version,"
                "policy_hash,context_kind,policy_json,game_version,game_version_source,"
                "build_id,branch,dlc_state_json,mod_state,created_at,checked_at,"
                "status,security_ok,diagnostics_json"
                ") VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (
                    sid, identity.content_hash, SCHEMA_VERSION,
                    fields["parser_version"], fields["adapter_version"], fields["policy_hash"],
                    fields["context_kind"], identity.policy_json, fields["game_version"],
                    fields["game_version_source"], fields["build_id"], fields["branch"],
                    _as_json(fields["dlc_state"]), fields["mod_state"], _utc(), None,
                    "building", 1, "[]",
                ),
            )

        try:
            with self._connection() as conn, _immediate(conn):
                for key, source in source_by_key.items():
                    if cancel is not None and cancel():
                        raise SnapshotError("CANCELLED", "Staging was cancelled.")
                    self.cache.put(source.data, by_key[key].file_sha256)
                for desc in identity.sources:
                    self.cache.verify(desc.file_sha256, desc.size)
                if before_ready is not None:
                    before_ready()
                if cancel is not None and cancel():
                    raise SnapshotError("CANCELLED", "Staging was cancelled.")

                for d in identity.sources:
                    original = source_by_key[d.key]
                    root_sha, physical_relative = self._check_live(original, d)
                    conn.execute(
                        "INSERT INTO source_files(snapshot_id,source_kind,source_id,"
                        "relative_path,file_sha256,byte_size,cache_sha256,live_required,"
                        "live_relative_path,live_root_sha256)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?)",
                        (
                            sid, d.source_kind, d.source_id, d.relative_path,
                            d.file_sha256, d.size, d.file_sha256,
                            int(original.live_path is not None),
                            physical_relative, root_sha,
                        ),
                    )
                is_partial = bool(partial)
                ordered_candidates = sorted(
                    candidates,
                    key=lambda c: (
                        c.source_ref.source_kind, c.source_ref.source_id,
                        c.source_ref.relative_path, c.source_ref.byte_start,
                        c.source_ref.byte_end, c.game_id,
                    ),
                )
                keys: dict[tuple[str, str], int] = {}
                entity_map: dict[tuple[str, str, str, str, int, int], str] = {}
                for candidate in ordered_candidates:
                    if cancel is not None and cancel():
                        raise SnapshotError("CANCELLED", "Staging was cancelled.")
                    ref = candidate.source_ref
                    _validate_ref(ref, sid, by_key)
                    _validate_own_source(
                        candidate.items[0]._source if candidate.items else bytes_by_key[(
                            ref.source_kind, ref.source_id, ref.relative_path
                        )],
                        ref, bytes_by_key,
                    )
                    payload = candidate.to_dict(include_raw=False)
                    _validate_payload_refs(payload, sid, by_key)
                    occurrence = keys.get((candidate.kind, candidate.game_id), 0) + 1
                    keys[(candidate.kind, candidate.game_id)] = occurrence
                    entity_key = hashlib.sha256(storage_json({
                        "kind": candidate.kind, "game_id": candidate.game_id,
                        "source": ref.to_dict(), "occurrence": occurrence,
                    }, max_bytes=MAX_JSON_BYTES)).hexdigest()
                    match = (
                        candidate.game_id, ref.source_kind, ref.source_id,
                        ref.relative_path, ref.byte_start, ref.byte_end,
                    )
                    if match in entity_map:
                        raise SnapshotError("COLLISION_UNRESOLVED", "Repeated entity source span.")
                    entity_map[match] = entity_key
                    is_partial = is_partial or candidate.resolution == "partial"
                    conn.execute(
                        "INSERT INTO entities(snapshot_id,entity_key,game_id,kind,occurrence,"
                        "source_kind,source_id,relative_path,byte_start,byte_end,resolution,"
                        "candidate_json,localisation_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                        (
                            sid, entity_key, candidate.game_id, candidate.kind, occurrence,
                            ref.source_kind, ref.source_id, ref.relative_path,
                            ref.byte_start, ref.byte_end, candidate.resolution,
                            _as_json(payload),
                        ),
                    )
                    for ordinal, prerequisite in enumerate(candidate.prerequisites, 1):
                        _validate_ref(prerequisite.source_ref, sid, by_key)
                        conn.execute(
                            "INSERT INTO relations(snapshot_id,from_entity_key,occurrence,"
                            "relation_kind,target_game_id,target_entity_key,status,"
                            "source_ref_json,conditions_raw) VALUES(?,?,?,?,?,?,?,?,?)",
                            (
                                sid, entity_key, ordinal, "prerequisite",
                                prerequisite.target_game_id, None, "unresolved",
                                _as_json(prerequisite.source_ref.to_dict()), None,
                            ),
                        )

                for name in localised_names:
                    c = name.candidate
                    ref = c.source_ref
                    match = (
                        c.game_id, ref.source_kind, ref.source_id,
                        ref.relative_path, ref.byte_start, ref.byte_end,
                    )
                    entity_key = entity_map.get(match)
                    if entity_key is None:
                        raise SnapshotError("SCHEMA_ERROR", "Localised name has no source entity.")
                    resolution = name.localisation.to_dict()
                    _validate_payload_refs(resolution, sid, by_key)
                    is_partial = is_partial or resolution["resolution"] != "resolved"
                    updated = conn.execute(
                        "UPDATE entities SET localisation_json=? WHERE snapshot_id=? "
                        "AND entity_key=? AND localisation_json IS NULL",
                        (_as_json(resolution), sid, entity_key),
                    )
                    if updated.rowcount != 1:
                        raise SnapshotError("COLLISION_UNRESOLVED", "Duplicate translated entity.")

                for entry in sorted(entries, key=lambda x: (
                    x.source_ref.source_kind, x.source_ref.source_id,
                    x.source_ref.relative_path, x.source_ref.byte_start,
                    x.language, x.key, x.occurrence
                )):
                    if cancel is not None and cancel():
                        raise SnapshotError("CANCELLED", "Staging was cancelled.")
                    ref = entry.source_ref
                    _validate_ref(ref, sid, by_key)
                    _validate_own_source(entry._source, ref, bytes_by_key)
                    payload = _entry_data(entry)
                    _validate_payload_refs(payload, sid, by_key)
                    conn.execute(
                        "INSERT INTO localisation_entries(snapshot_id,source_kind,source_id,"
                        "relative_path,language,localisation_key,occurrence,marker,raw_value,"
                        "display_value,has_unsupported_escape,byte_start,byte_end,entry_json)"
                        " VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                        (
                            sid, ref.source_kind, ref.source_id, ref.relative_path,
                            entry.language, entry.key, entry.occurrence, entry.marker,
                            entry.raw_value, entry.display_value, int(entry.has_unsupported_escape),
                            ref.byte_start, ref.byte_end, _as_json(payload),
                        ),
                    )

                diagnostics_data: list[dict[str, Any]] = []
                for ordinal, diagnostic in enumerate(diagnostics):
                    payload = diagnostic.to_dict()
                    ref = payload.get("source_ref")
                    if ref is not None:
                        _validate_ref(ref, sid, by_key)
                    if payload["severity"] == "error":
                        is_partial = True
                    message = payload["message"]
                    if not isinstance(message, str) or len(message) > 512:
                        raise SnapshotError("SCHEMA_ERROR", "Diagnostic message is not bounded.")
                    diagnostics_data.append(payload)
                    conn.execute(
                        "INSERT INTO diagnostics(snapshot_id,ordinal,code,severity,message,"
                        "source_ref_json) VALUES(?,?,?,?,?,?)",
                        (
                            sid, ordinal, payload["code"], payload["severity"],
                            message, None if ref is None else _as_json(ref),
                        ),
                    )

                if cancel is not None and cancel():
                    raise SnapshotError("CANCELLED", "Staging was cancelled.")
                target_status = "partial" if is_partial else "ready"
                if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                    raise SnapshotError("SCHEMA_ERROR", "Foreign-key validation failed.")
                conn.execute(
                    "UPDATE snapshots SET status=?, checked_at=?, diagnostics_json=? "
                    "WHERE snapshot_id=? AND status='building'",
                    (target_status, _utc(), _as_json(diagnostics_data), sid),
                )
        except Exception as exc:
            self._fail_build(sid, exc)
            if isinstance(exc, SnapshotError):
                raise
            if isinstance(exc, sqlite3.DatabaseError):
                raise _db_error(exc) from exc
            if isinstance(exc, OSError):
                raise SnapshotError("SQLITE_WRITE_ERROR", "Snapshot staging failed.") from exc
            raise
        return identity

    def _fail_build(self, sid: str, cause: Exception) -> None:
        code = cause.code if isinstance(cause, SnapshotError) else "BUILD_FAILED"
        try:
            with self._connection() as conn, _immediate(conn):
                conn.execute(
                    "UPDATE snapshots SET status='failed', diagnostics_json=? "
                    "WHERE snapshot_id=? AND status='building'",
                    (_as_json([{"code": code, "severity": "error",
                                "message": "Snapshot build did not complete."}]), sid),
                )
        except (sqlite3.DatabaseError, SnapshotError):
            # If even marking failed is impossible, 'building' is still never
            # eligible for activation and is marked failed on the next restart.
            pass

    def _summary(self, row: sqlite3.Row) -> SnapshotSummary:
        return SnapshotSummary(row["snapshot_id"], row["content_hash"],
                               row["status"], row["game_version"])

    def snapshot(self, sid: str) -> SnapshotSummary | None:
        with self._connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT snapshot_id,content_hash,status,game_version "
                "FROM snapshots WHERE snapshot_id=?", (sid,)
            ).fetchone()
            return None if row is None else self._summary(row)

    def active_snapshot_id(self) -> str | None:
        with self._connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='active_snapshot'"
            ).fetchone()
            return None if row is None else str(row[0])

    def _ensure_ready(self, conn: sqlite3.Connection, sid: str) -> sqlite3.Row:
        row = conn.execute(
            "SELECT * FROM snapshots WHERE snapshot_id=?", (sid,)
        ).fetchone()
        if row is None or row["status"] not in {"ready", "partial"}:
            raise SnapshotError("SNAPSHOT_NOT_READY", "Snapshot is not queryable.")
        if not row["security_ok"]:
            raise SnapshotError("PATH_REJECTED", "Snapshot failed security validation.")
        return row

    def _snapshot_for_query(
        self, conn: sqlite3.Connection, sid: str | None
    ) -> str:
        if sid is None:
            row = conn.execute(
                "SELECT value FROM settings WHERE key='active_snapshot'"
            ).fetchone()
            if row is None:
                raise SnapshotError("SNAPSHOT_NOT_READY", "No active snapshot.")
            sid = row[0]
        self._ensure_ready(conn, sid)
        return sid

    def search_snapshot(self, snapshot_id: str | None = None) -> dict[str, Any]:
        """Pin one query to an active or explicit ready/partial snapshot."""
        with self._connection(read_only=True) as conn:
            sid = self._snapshot_for_query(conn, snapshot_id)
            row = conn.execute(
                "SELECT snapshot_id,status,game_version,checked_at "
                "FROM snapshots WHERE snapshot_id=?", (sid,),
            ).fetchone()
            assert row is not None
            return dict(row)

    def iter_search_rows(
        self, snapshot_id: str, record_kind: str
    ):
        """Stream one verified snapshot in bounded batches for index reconstruction.

        This is a cold-path projection builder, not the search hot path.
        The only allowed selectors are hardcoded (no user-supplied SQL identifiers).
        No entity candidate JSON or whole table is materialised into Python lists.
        """
        if record_kind not in {"entities", "localisation"}:
            raise SnapshotError("QUERY_INVALID", "Unsupported search record type.")
        with self._connection(read_only=True) as conn:
            # A read transaction ensures every yielded row comes from one
            # SQLite snapshot, even during a concurrent active-pointer change.
            conn.execute("BEGIN")
            self._snapshot_for_query(conn, snapshot_id)
            if record_kind == "entities":
                cursor = conn.execute(
                    "SELECT e.entity_key,e.game_id,e.kind,e.occurrence,"
                    "e.relative_path,e.source_kind,e.source_id,e.byte_start,e.byte_end,"
                    "e.resolution,e.localisation_json,s.file_sha256,"
                    "json_extract(e.candidate_json,'$.source_ref.line_start') AS line_start,"
                    "json_extract(e.candidate_json,'$.source_ref.line_end') AS line_end "
                    "FROM entities e JOIN source_files s "
                    "ON e.snapshot_id=s.snapshot_id AND e.source_kind=s.source_kind "
                    "AND e.source_id=s.source_id AND e.relative_path=s.relative_path "
                    "WHERE e.snapshot_id=? "
                    "ORDER BY e.kind,e.game_id,e.relative_path,e.occurrence,e.entity_key",
                    (snapshot_id,),
                )
            else:
                cursor = conn.execute(
                    "SELECT language,localisation_key,display_value,entry_json "
                    "FROM localisation_entries WHERE snapshot_id=? "
                    "ORDER BY language,localisation_key,relative_path,occurrence",
                    (snapshot_id,),
                )
            while batch := cursor.fetchmany(128):
                for row in batch:
                    yield dict(row)
            conn.execute("ROLLBACK")

    def answer_snapshot_context(self, snapshot_id: str) -> dict[str, Any]:
        """Get pinned version/branch evidence without consulting the active pointer."""
        with self._connection(read_only=True) as conn:
            row = self._ensure_ready(conn, snapshot_id)
            return {
                key: row[key] for key in (
                    "snapshot_id", "status", "checked_at", "game_version",
                    "game_version_source", "branch", "context_kind", "mod_state",
                )
            }

    def answer_entity(self, snapshot_id: str, entity_key: str) -> dict[str, Any]:
        """Read one immutable candidate by (snapshot, entity_key), never a table scan."""
        if (not isinstance(entity_key, str) or len(entity_key) != 64
                or any(ch not in "0123456789abcdef" for ch in entity_key)):
            raise SnapshotError("QUERY_INVALID", "Entity key must be a SHA-256 ID.")
        with self._connection(read_only=True) as conn:
            self._ensure_ready(conn, snapshot_id)
            row = conn.execute(
                "SELECT game_id,kind,resolution,candidate_json,localisation_json "
                "FROM entities WHERE snapshot_id=? AND entity_key=? LIMIT 1",
                (snapshot_id, entity_key),
            ).fetchone()
            if row is None:
                raise SnapshotError("SOURCE_CHANGED", "Entity is not in the pinned snapshot.")
            return {
                "snapshot_id": snapshot_id, "entity_key": entity_key,
                "game_id": row["game_id"], "kind": row["kind"],
                "resolution": row["resolution"],
                "candidate": json.loads(row["candidate_json"]),
                "localisation": (
                    None if row["localisation_json"] is None
                    else json.loads(row["localisation_json"])
                ),
            }

    @contextmanager
    def citation_reader(self, snapshot_id: str):
        """Share bounded verified SHA/line evidence within one answer request."""
        with self._connection(read_only=True) as conn:
            conn.execute("BEGIN")
            self._ensure_ready(conn, snapshot_id)
            yield _VerifiedCitationReader(self, conn, snapshot_id)
            conn.execute("ROLLBACK")

    def citation_bytes(self, ref: SourceRef) -> bytes:
        """Read an exact cached span and validate *original* byte and line positions.

        Unlike a file-level hash alone, this rejects forged line numbers, interior
        UTF-8 offsets, impossible ranges and misplaced trailing newline spans.
        The entire cache blob is rehashed by BlobCache.read before citation.
        """
        if (not isinstance(ref, SourceRef)
                or any(isinstance(x, bool) or not isinstance(x, int) for x in (
                    ref.byte_start, ref.byte_end, ref.line_start, ref.line_end
                ))):
            raise SnapshotError("SOURCE_CHANGED", "Citation has invalid offsets.")
        with self._connection(read_only=True) as conn:
            self._ensure_ready(conn, ref.snapshot_id)
            row = conn.execute(
                "SELECT file_sha256,cache_sha256,byte_size FROM source_files "
                "WHERE snapshot_id=? AND source_kind=? AND source_id=? AND relative_path=?",
                (ref.snapshot_id, ref.source_kind, ref.source_id, ref.relative_path),
            ).fetchone()
            if row is None or (ref.file_sha256 != row["file_sha256"]
                               or row["cache_sha256"] != row["file_sha256"]):
                raise SnapshotError("SOURCE_CHANGED", "Citation source/cache identity is invalid.")
            if (ref.byte_start < 0 or ref.byte_end <= ref.byte_start
                    or ref.byte_end > row["byte_size"]):
                raise SnapshotError("SOURCE_CHANGED", "Citation byte range is invalid.")
            data = self.cache.read(row["cache_sha256"], row["byte_size"])
            line_start = data.count(b"\n", 0, ref.byte_start) + 1
            line_end = data.count(b"\n", 0, ref.byte_end - 1) + 1
            if (ref.line_start != line_start or ref.line_end != line_end):
                raise SnapshotError("SOURCE_CHANGED", "Citation line positions differ from source.")
            span = data[ref.byte_start:ref.byte_end]
            try:
                span.decode("utf-8", errors="strict")
            except UnicodeError as exc:
                raise SnapshotError(
                    "SOURCE_CHANGED", "Citation cuts a UTF-8 codepoint."
                ) from exc
            return span

    def entities(self, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        with self._connection(read_only=True) as conn:
            sid = self._snapshot_for_query(conn, snapshot_id)
            rows = conn.execute(
                "SELECT entity_key,game_id,kind,occurrence,resolution,"
                "candidate_json,localisation_json FROM entities "
                "WHERE snapshot_id=? ORDER BY kind,game_id,occurrence,entity_key", (sid,)
            ).fetchall()
            return [
                {
                    "snapshot_id": sid, "entity_key": r["entity_key"],
                    "game_id": r["game_id"], "kind": r["kind"],
                    "occurrence": r["occurrence"], "resolution": r["resolution"],
                    "candidate": json.loads(r["candidate_json"]),
                    "localisation": (
                        None if r["localisation_json"] is None
                        else json.loads(r["localisation_json"])
                    ),
                }
                for r in rows
            ]

    def localisation_entries(self, snapshot_id: str | None = None) -> list[dict[str, Any]]:
        with self._connection(read_only=True) as conn:
            sid = self._snapshot_for_query(conn, snapshot_id)
            rows = conn.execute(
                "SELECT entry_json FROM localisation_entries WHERE snapshot_id=? "
                "ORDER BY source_kind,source_id,relative_path,byte_start,occurrence",
                (sid,),
            ).fetchall()
            return [json.loads(row[0]) for row in rows]

    def source_bytes(self, ref: SourceRef) -> bytes:
        with self._connection(read_only=True) as conn:
            self._snapshot_for_query(conn, ref.snapshot_id)
            row = conn.execute(
                "SELECT file_sha256,byte_size,cache_sha256 FROM source_files "
                "WHERE snapshot_id=? AND source_kind=? AND source_id=? AND relative_path=?",
                (ref.snapshot_id,ref.source_kind,ref.source_id,ref.relative_path),
            ).fetchone()
            if row is None or ref.file_sha256 != row["file_sha256"]:
                raise SnapshotError("SOURCE_CHANGED", "SourceRef does not belong to the snapshot.")
            if row["cache_sha256"] != row["file_sha256"]:
                raise SnapshotError("SOURCE_CHANGED", "Cache pointer differs from source SHA-256.")
            if ref.byte_start < 0 or ref.byte_end < ref.byte_start or ref.byte_end > row["byte_size"]:
                raise SnapshotError("SOURCE_CHANGED", "SourceRef range is invalid.")
            return self.cache.read(row["cache_sha256"], row["byte_size"])[
                ref.byte_start:ref.byte_end
            ]

    def _verify_cache_rows(self, conn: sqlite3.Connection, sid: str) -> None:
        for row in conn.execute(
            "SELECT cache_sha256,file_sha256,byte_size FROM source_files WHERE snapshot_id=?",
            (sid,),
        ):
            if row["cache_sha256"] != row["file_sha256"]:
                raise SnapshotError("SOURCE_CHANGED", "Cache and source hashes disagree.")
            self.cache.verify(row["cache_sha256"], row["byte_size"])

    def _verify_live_manifest(
        self, conn: sqlite3.Connection, sid: str,
        sources: tuple[SourceFileInput, ...] | None
    ) -> None:
        rows = conn.execute(
            "SELECT source_kind,source_id,relative_path,file_sha256,byte_size,live_required, "
            "live_relative_path,live_root_sha256 "
            "FROM source_files WHERE snapshot_id=? "
            "ORDER BY source_kind,source_id,relative_path",
            (sid,),
        ).fetchall()
        if any(row["live_required"] for row in rows) and sources is None:
            raise SnapshotError("SOURCE_UNVERIFIED", "Current live inventory is required.")
        if sources is None:
            return
        supplied = sorted(
            ((s.descriptor(), s) for s in sources), key=lambda item: item[0].key
        )
        if len(supplied) != len(rows):
            raise SnapshotError("SOURCE_CHANGED", "Source inventory changed after staging.")
        for row, (descriptor, original) in zip(rows, supplied, strict=True):
            if (descriptor.key != (
                row["source_kind"], row["source_id"], row["relative_path"]
            ) or descriptor.file_sha256 != row["file_sha256"]
                    or descriptor.size != row["byte_size"]):
                raise SnapshotError("SOURCE_CHANGED", "Source inventory changed after staging.")
            if bool(row["live_required"]) != (original.live_path is not None):
                raise SnapshotError("SOURCE_UNVERIFIED", "Live-source requirement changed.")
            if row["live_required"]:
                if self.game_root is None:
                    raise SnapshotError("SOURCE_UNVERIFIED", "Original game root is unavailable.")
                if row["live_root_sha256"] != self._live_root_hash():
                    raise SnapshotError("SOURCE_CHANGED", "Staged live-source root changed.")
                # Compare targets BEFORE reading bytes; a same-hash copy cannot
                # take the place of the file bound during stage().
                actual_relative = live_source_relative_path(
                    original.live_path, self.game_root
                )
                if actual_relative != row["live_relative_path"]:
                    raise SnapshotError("SOURCE_CHANGED", "Staged live-source path changed.")
            root_sha, relative = self._check_live(original, descriptor)
            if (root_sha != row["live_root_sha256"]
                    or relative != row["live_relative_path"]):
                raise SnapshotError("SOURCE_CHANGED", "Staged live-source binding changed.")

    def activate(
        self,
        snapshot_id: str,
        *,
        allow_partial: bool = False,
        sources: tuple[SourceFileInput, ...] | None = None,
        cancel: _CANCEL | None = None,
        before_commit: _HOOK | None = None,
    ) -> None:
        """Atomic pointer change; all failure paths leave old active untouched."""
        if cancel is not None and cancel():
            raise SnapshotError("CANCELLED", "Activation was cancelled.")
        with self._connection() as conn, _immediate(conn):
            row = self._ensure_ready(conn, snapshot_id)
            if row["status"] == "partial" and not allow_partial:
                raise SnapshotError("PARTIAL_INDEX", "Partial snapshots require explicit approval.")
            self._verify_live_manifest(conn, snapshot_id, sources)
            self._verify_cache_rows(conn, snapshot_id)
            if conn.execute("PRAGMA foreign_key_check").fetchone() is not None:
                raise SnapshotError("SCHEMA_ERROR", "Foreign-key validation failed.")
            if cancel is not None and cancel():
                raise SnapshotError("CANCELLED", "Activation was cancelled.")
            conn.execute(
                "INSERT INTO settings(key,value) VALUES('active_snapshot',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (snapshot_id,),
            )
            if before_commit is not None:
                before_commit()
            if cancel is not None and cancel():
                raise SnapshotError("CANCELLED", "Activation was cancelled.")

    def backup(self, name: str) -> Path:
        """Consistent SQLite backup only; cache blobs must accompany external backups."""
        if not isinstance(name, str) or not name or any(
            ch not in "abcdefghijklmnopqrstuvwxyz0123456789-_" for ch in name
        ) or len(name) > 60:
            raise SnapshotError("PATH_REJECTED", "Unsafe backup name.")
        directory = self.data_dir / "backups"
        _ensure_directory(directory)
        target = directory / (name + ".sqlite3")
        if target.exists() or target.is_symlink():
            raise SnapshotError("PATH_REJECTED", "Backup destination already exists.")
        temporary = directory / (name + ".partial.sqlite3")
        if temporary.exists() or temporary.is_symlink():
            raise SnapshotError("PATH_REJECTED", "Backup temporary destination is occupied.")
        try:
            with self._connection(read_only=True) as source:
                with closing(sqlite3.connect(temporary)) as destination:
                    source.backup(destination)
            with closing(connect(temporary, read_only=True)) as verified:
                check_schema(verified)
            os.replace(temporary, target)
            return target
        except (OSError, sqlite3.DatabaseError) as exc:
            raise SnapshotError("SQLITE_WRITE_ERROR", "Consistent DB backup failed.") from exc
        finally:
            if temporary.exists():
                temporary.unlink()
