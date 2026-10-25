"""Versioned disk localisation products; bounded writer, immutable snapshot mappings."""

from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import uuid
from collections import defaultdict
from contextlib import contextmanager
from dataclasses import replace

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.domain import SourceContext, SourceRef
from stellaris_supporter.localisation import reader
from stellaris_supporter.localisation.resolver import (
    LocalisationReferenceSelection,
    LocalisationResolution,
    resolve_localisation,
)
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.cache import _ensure_directory
from stellaris_supporter.storage.source_pool import SourcePool

VERSION = "localisation-disk-2"
MAX_ROWS = 2_000_000
BATCH_ROWS = 1000
BATCH_BYTES = 8 * 1024 * 1024
MAX_LOOKUP = 4096


def packed(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def digest(value):
    return hashlib.sha256(packed(value).encode()).hexdigest()


@contextmanager
def index_lock(directory):
    path = directory / "index-v2.lock"
    _ensure_directory(directory)
    _check_components(path)
    fd = os.open(path, os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0), 0o600)
    try:
        if os.fstat(fd).st_size == 0:
            os.write(fd, b"0")
        os.lseek(fd, 0, 0)
        try:
            if os.name == "nt":
                import msvcrt

                msvcrt.locking(fd, msvcrt.LK_NBLCK, 1)
            else:
                import fcntl

                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise SnapshotError("SQLITE_BUSY", "Another index writer is running.") from None
        yield
    finally:
        os.close(fd)


class FileCatalogue:
    def __init__(self, repository, read_only=False):
        self.repository = repository
        self.read_only = read_only
        self.path = repository.data_dir / "localisation-products.sqlite3"
        for path in (
            self.path,
            self.path.with_name(self.path.name + "-wal"),
            self.path.with_name(self.path.name + "-shm"),
        ):
            _check_components(path)
        if self.path.exists() and self.path.stat().st_size:
            probe = sqlite3.connect(self.path.as_uri() + "?mode=ro", uri=True)
            try:
                version = probe.execute("PRAGMA user_version").fetchone()[0]
                application = probe.execute("PRAGMA application_id").fetchone()[0]
                tables = {
                    r[0]
                    for r in probe.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
                    )
                }
                expected = {
                    "file_versions",
                    "entries",
                    "opaque",
                    "snapshot_files",
                    "derived",
                    "jobs",
                }
                if version not in {0, 1} or (
                    tables != expected and not (not tables and application == 0x53534C32)
                ):
                    raise SnapshotError(
                        "SCHEMA_VERSION_UNSUPPORTED", "Unsupported localisation product schema."
                    )
                if tables and "suspected_key" not in {
                    r[1] for r in probe.execute("PRAGMA table_info(opaque)")
                }:
                    raise SnapshotError(
                        "SCHEMA_VERSION_UNSUPPORTED", "Localisation product columns differ."
                    )
            finally:
                probe.close()
        self.conn = (
            sqlite3.connect(
                self.path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=0.25
            )
            if read_only
            else sqlite3.connect(self.path, isolation_level=None, timeout=0.25)
        )
        self.conn.row_factory = sqlite3.Row
        if not read_only:
            self.conn.execute("PRAGMA application_id=1397967922")
            self.conn.execute("PRAGMA journal_mode=WAL")
            self.conn.execute("PRAGMA synchronous=FULL")
            self.conn.execute("PRAGMA foreign_keys=ON")
            self.conn.execute("PRAGMA max_page_count=524288")
            self.conn.executescript("""
            BEGIN IMMEDIATE;
            CREATE TABLE IF NOT EXISTS file_versions (
                file_id TEXT PRIMARY KEY, source_kind TEXT, source_id TEXT, path TEXT,
                sha TEXT, size INTEGER, parser TEXT, status TEXT, complete INTEGER,
                product_hash TEXT, counts TEXT, samples TEXT, entry_count INTEGER);
            CREATE TABLE IF NOT EXISTS entries (
                file_id TEXT NOT NULL REFERENCES file_versions(file_id), ordinal INTEGER,
                language TEXT, key TEXT, occurrence INTEGER, marker TEXT,
                start INTEGER, end INTEGER, line INTEGER, vs INTEGER, ve INTEGER,
                qs INTEGER, qe INTEGER, cs INTEGER, ce INTEGER, vcs INTEGER,
                unsupported INTEGER, raw TEXT, display TEXT,
                PRIMARY KEY(file_id,ordinal));
            CREATE INDEX IF NOT EXISTS loc_lookup ON entries(language,key,file_id,occurrence);
            CREATE TABLE IF NOT EXISTS opaque (
                file_id TEXT REFERENCES file_versions(file_id), ordinal INTEGER,
                start INTEGER,end INTEGER,line INTEGER,suspected_key TEXT,PRIMARY KEY(file_id,ordinal));
            CREATE TABLE IF NOT EXISTS snapshot_files (
                sid TEXT, file_id TEXT REFERENCES file_versions(file_id), product_hash TEXT,
                PRIMARY KEY(sid,file_id));
            CREATE TABLE IF NOT EXISTS derived (
                key TEXT PRIMARY KEY, dependencies TEXT, payload TEXT, checksum TEXT);
            CREATE TABLE IF NOT EXISTS jobs (
                job_id TEXT PRIMARY KEY, sid TEXT, status TEXT, error TEXT,
                files_done INTEGER DEFAULT 0, files_total INTEGER DEFAULT 0);
            PRAGMA user_version=1;
            COMMIT;
            """)
        self.pool = SourcePool(repository.cache)
        self.verified = set()
        self.total = self.conn.execute("SELECT count(*) FROM entries").fetchone()[0]

    def close(self):
        self.conn.close()

    def start(self):
        self.conn.execute("UPDATE jobs SET status='interrupted' WHERE status='running'")
        job = uuid.uuid4().hex
        self.conn.execute("INSERT INTO jobs(job_id,status) VALUES(?,'running')", (job,))
        return job

    def finish(self, job, status, sid=None, error=None):
        self.conn.execute(
            "UPDATE jobs SET status=?,sid=?,error=? WHERE job_id=?", (status, sid, error, job)
        )

    @staticmethod
    def file_id(source):
        descriptor = source.descriptor()
        return digest([VERSION, *descriptor.key, descriptor.file_sha256])

    def _rows_hash(self, file_id):
        value = hashlib.sha256()
        opaque = hashlib.sha256()
        for row in self.conn.execute(
            "SELECT * FROM entries WHERE file_id=? ORDER BY ordinal", (file_id,)
        ):
            value.update(packed(list(row)[1:]).encode() + b"\n")
        for row in self.conn.execute(
            "SELECT ordinal,start,end,line,suspected_key FROM opaque WHERE file_id=? ORDER BY ordinal",
            (file_id,),
        ):
            opaque.update(packed(list(row)).encode() + b"\n")
        return hashlib.sha256(value.digest() + opaque.digest()).hexdigest()

    def verify_file(self, file_id, expected=None):
        row = self.conn.execute(
            "SELECT * FROM file_versions WHERE file_id=?", (file_id,)
        ).fetchone()
        if row is None or row["status"] not in {"ready", "partial"}:
            raise SnapshotError("CACHE_MISSING", "Incomplete localisation file product.")
        if expected is not None and row["product_hash"] != expected:
            raise SnapshotError("SOURCE_CHANGED", "Localisation product receipt differs.")
        if file_id not in self.verified:
            if self._rows_hash(file_id) != row["product_hash"]:
                raise SnapshotError("SOURCE_CHANGED", "Localisation product was modified.")
            self.verified.add(file_id)
        return dict(row)

    def ingest(self, source, cancel=None, force=False):
        fid = self.file_id(source)
        row = self.conn.execute(
            "SELECT status FROM file_versions WHERE file_id=?", (fid,)
        ).fetchone()
        repair = False
        if row and row[0] in {"ready", "partial"}:
            try:
                meta = self.verify_file(fid)
            except SnapshotError as exc:
                if exc.code != "SOURCE_CHANGED":
                    raise
                repair = True
            else:
                if force:
                    self.reparse(source, meta, cancel)
                return fid, not force
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            old = self.conn.execute(
                "SELECT count(*) FROM entries WHERE file_id=?", (fid,)
            ).fetchone()[0]
            self.conn.execute("DELETE FROM entries WHERE file_id=?", (fid,))
            self.conn.execute("DELETE FROM opaque WHERE file_id=?", (fid,))
            d = source.descriptor()
            self.conn.execute(
                "INSERT OR REPLACE INTO file_versions VALUES(?,?,?,?,?,?,?,'building',0,'','{}','[]',0)",
                (fid, *d.key, d.file_sha256, d.size, VERSION),
            )
            if not repair:
                self.conn.execute("COMMIT")
            self.total -= old
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        entries, unknown = [], []
        size = ordinal = unknown_count = 0
        counts = {}

        def flush():
            nonlocal size
            if cancel and cancel():
                raise SnapshotError("CANCELLED", "Index cancelled between file batches.")
            if not entries and not unknown:
                return
            if self.total + len(entries) > MAX_ROWS:
                raise SnapshotError("LIMIT_EXCEEDED", "Localisation disk row budget exceeded.")
            if not repair:
                self.conn.execute("BEGIN IMMEDIATE")
            try:
                self.conn.executemany(
                    "INSERT INTO entries VALUES(" + ",".join("?" for _ in range(19)) + ")", entries
                )
                self.conn.executemany("INSERT INTO opaque VALUES(?,?,?,?,?,?)", unknown)
                if not repair:
                    self.conn.execute("COMMIT")
            except Exception:
                if self.conn.in_transaction:
                    self.conn.execute("ROLLBACK")
                raise
            self.total += len(entries)
            entries.clear()
            unknown.clear()
            size = 0

        def accept(kind, value):
            nonlocal size, ordinal, unknown_count
            if cancel and cancel():
                raise SnapshotError("CANCELLED", "Index cancelled during localisation scan.")
            if kind == "entry":
                ordinal += 1
                r, v, q = value.source_ref, value.value_source_ref, value.quoted_value_source_ref
                raw, display = value.raw_value, value.display_value
                entries.append(
                    (
                        fid,
                        ordinal,
                        value.language,
                        value.key,
                        value.occurrence,
                        value.marker,
                        r.byte_start,
                        r.byte_end,
                        r.line_start,
                        v.byte_start,
                        v.byte_end,
                        q.byte_start,
                        q.byte_end,
                        value.column_start,
                        value.column_end,
                        value.value_column_start,
                        int(value.has_unsupported_escape),
                        raw,
                        display,
                    )
                )
                size += len(raw.encode()) + len(display.encode()) + 256
            elif kind == "unknown":
                unknown_count += 1
                raw_line = value.raw_text(source.data)
                match = re.match(r"[ \t]*([A-Za-z_][A-Za-z0-9_.-]*)[ \t]*:", raw_line)
                suspected = (
                    match.group(1) if match else "*" if raw_line.lstrip().startswith("l_") else ""
                )
                unknown.append(
                    (
                        fid,
                        unknown_count,
                        value.byte_start,
                        value.byte_end,
                        value.line_start,
                        suspected,
                    )
                )
                size += 64
            if len(entries) + len(unknown) >= BATCH_ROWS or size >= BATCH_BYTES:
                flush()

        context = SourceContext("0" * 64, *d.key, d.file_sha256)
        try:
            doc = reader.parse_localisation(
                source.data, context, sink=accept, diagnostic_counts=counts, game_compatibility=True
            )
            flush()
            if any(
                k.startswith("LIMIT_EXCEEDED:")
                or k.startswith("ENCODING_ERROR:")
                or k.startswith("LOC_SOURCE_MISMATCH:")
                for k in counts
            ):
                raise SnapshotError(
                    "LIMIT_EXCEEDED"
                    if any(k.startswith("LIMIT_") for k in counts)
                    else "SOURCE_CHANGED",
                    "Localisation capture did not finish safely.",
                )
            checksum = self._rows_hash(fid)
            self.conn.execute(
                "UPDATE file_versions SET status=?,complete=?,product_hash=?,counts=?,samples=?,entry_count=? WHERE file_id=?",
                (
                    "ready" if doc.complete else "partial",
                    int(doc.complete),
                    checksum,
                    packed(counts),
                    packed([d.to_dict() for d in doc.diagnostics]),
                    ordinal,
                    fid,
                ),
            )
            if repair:
                self.conn.execute("COMMIT")
            self.verified.add(fid)
            return fid, False
        except Exception:
            if self.conn.in_transaction:
                self.conn.execute("ROLLBACK")
            if not repair:
                self.conn.execute(
                    "UPDATE file_versions SET status='failed' WHERE file_id=?", (fid,)
                )
            raise

    def reparse(self, source, meta, cancel):
        d = source.descriptor()
        value, opaque = hashlib.sha256(), hashlib.sha256()
        ordinal = unknown_count = 0
        counts = {}

        def accept(kind, item):
            nonlocal ordinal, unknown_count
            if cancel and cancel():
                raise SnapshotError("CANCELLED", "Full scan cancelled.")
            if kind == "entry":
                ordinal += 1
                r, v, q = item.source_ref, item.value_source_ref, item.quoted_value_source_ref
                row = (
                    ordinal,
                    item.language,
                    item.key,
                    item.occurrence,
                    item.marker,
                    r.byte_start,
                    r.byte_end,
                    r.line_start,
                    v.byte_start,
                    v.byte_end,
                    q.byte_start,
                    q.byte_end,
                    item.column_start,
                    item.column_end,
                    item.value_column_start,
                    int(item.has_unsupported_escape),
                    item.raw_value,
                    item.display_value,
                )
                value.update(packed(row).encode() + b"\n")
            elif kind == "unknown":
                unknown_count += 1
                raw = item.raw_text(source.data)
                match = re.match(r"[ \t]*([A-Za-z_][A-Za-z0-9_.-]*)[ \t]*:", raw)
                suspected = (
                    match.group(1) if match else "*" if raw.lstrip().startswith("l_") else ""
                )
                opaque.update(
                    packed(
                        (unknown_count, item.byte_start, item.byte_end, item.line_start, suspected)
                    ).encode()
                    + b"\n"
                )

        doc = reader.parse_localisation(
            source.data,
            SourceContext("0" * 64, *d.key, d.file_sha256),
            sink=accept,
            diagnostic_counts=counts,
            game_compatibility=True,
        )
        checksum = hashlib.sha256(value.digest() + opaque.digest()).hexdigest()
        if (
            checksum != meta["product_hash"]
            or bool(doc.complete) != bool(meta["complete"])
            or packed(counts) != meta["counts"]
        ):
            raise SnapshotError(
                "SOURCE_CHANGED", "Fresh parse differs from immutable file product."
            )

    def bind(self, sid, sources):
        manifest = []
        for source in sources:
            if not source.relative_path.startswith("localisation/"):
                continue
            fid = self.file_id(source)
            meta = self.verify_file(fid)
            manifest.append((fid, meta["product_hash"]))
        manifest.sort()
        existing = [
            tuple(row)
            for row in self.conn.execute(
                "SELECT file_id,product_hash FROM snapshot_files WHERE sid=? ORDER BY file_id",
                (sid,),
            )
        ]
        if existing and existing != manifest:
            raise SnapshotError(
                "SOURCE_CHANGED", "Immutable localisation snapshot mapping differs."
            )
        self.conn.executemany(
            "INSERT OR IGNORE INTO snapshot_files VALUES(?,?,?)", ((sid, *row) for row in manifest)
        )
        return digest(manifest)

    def catalogue(self, sid):
        return DiskCatalogue(self, sid)

    @classmethod
    def for_snapshot(cls, repository, sid):
        with repository._connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", ("localisation-v2:" + sid,)
            ).fetchone()
        if row is None:
            return None
        store = cls(repository, read_only=True)
        manifest = [
            tuple(r)
            for r in store.conn.execute(
                "SELECT file_id,product_hash FROM snapshot_files WHERE sid=? ORDER BY file_id",
                (sid,),
            )
        ]
        if digest(manifest) != row[0]:
            store.close()
            raise SnapshotError("SOURCE_CHANGED", "Localisation snapshot receipt is invalid.")
        return store


class DiskCatalogue:
    def __init__(self, store, sid):
        self.store, self.snapshot_id = store, sid
        self._index = self
        self.queries = set()
        self.rows = {}
        self.selected = {}
        self.diagnostics = ()
        self.complete = True
        self.source_complete = not bool(
            store.conn.execute(
                "SELECT 1 FROM snapshot_files m JOIN file_versions f USING(file_id) WHERE m.sid=? AND f.complete=0 LIMIT 1",
                (sid,),
            ).fetchone()
        )

    def get(self, identifier, default=()):
        return self.definitions(*identifier)

    def definitions(self, language, key):
        language = language.removeprefix("l_").lower()
        self.queries.add((language, key))
        if not self.coverage(key):
            self.complete = False
        rows = list(
            self.store.conn.execute(
                "SELECT e.*,f.source_kind,f.source_id,f.path,f.sha,f.size,m.product_hash AS receipt FROM entries e JOIN snapshot_files m USING(file_id) JOIN file_versions f USING(file_id) WHERE m.sid=? AND e.language=? AND e.key=? ORDER BY f.source_kind,f.source_id,f.path,e.occurrence LIMIT ?",
                (self.snapshot_id, language, key, MAX_LOOKUP + 1),
            )
        )
        if len(rows) > MAX_LOOKUP:
            raise SnapshotError("LIMIT_EXCEEDED", "Localisation key has too many definitions.")
        return tuple(self.entry(dict(row)) for row in rows)

    def entry(self, row):
        self.store.verify_file(row["file_id"], row["receipt"])
        data = self.store.pool.read(row["sha"], row["size"])

        def ref(start, end):
            return SourceRef(
                self.snapshot_id,
                row["source_kind"],
                row["source_id"],
                row["path"],
                row["sha"],
                start,
                end,
                row["line"],
                row["line"],
            )

        r, v, q = (
            ref(row["start"], row["end"]),
            ref(row["vs"], row["ve"]),
            ref(row["qs"], row["qe"]),
        )
        line_start = data.rfind(b"\n", 0, r.byte_start) + 1
        line_end = data.find(b"\n", r.byte_start)
        if line_end < 0:
            line_end = len(data)
        body = data[line_start:line_end].decode("utf-8-sig").rstrip("\r")
        prefix = reader._scan_entry_prefix(body)
        closing, unsupported = (
            reader._end_of_quote(body, prefix.opening, game_compatibility=True)
            if prefix
            else (None, False)
        )
        base = line_start + (3 if line_start == 0 and data.startswith(b"\xef\xbb\xbf") else 0)
        if (
            prefix is None
            or closing is None
            or prefix.key != row["key"]
            or prefix.marker != row["marker"]
            or r.byte_start != base + len(body[: prefix.key_start].encode())
            or r.byte_end != base + len(body[: closing + 1].encode())
            or v.byte_start != base + len(body[: prefix.opening + 1].encode())
            or v.byte_end != base + len(body[:closing].encode())
            or q.byte_start != v.byte_start - 1
            or q.byte_end != v.byte_end + 1
            or row["line"] != data.count(b"\n", 0, r.byte_start) + 1
            or unsupported != bool(row["unsupported"])
        ):
            raise SnapshotError(
                "SOURCE_CHANGED", "Stored localisation entry differs from original line."
            )
        value = reader.LocalisationEntry(
            row["key"],
            row["language"],
            row["marker"],
            row["occurrence"],
            r,
            v,
            q,
            row["cs"],
            row["ce"],
            row["vcs"],
            bool(row["unsupported"]),
            data,
            True,
        )
        if value.raw_value != row["raw"] or value.display_value != row["display"]:
            raise SnapshotError(
                "SOURCE_CHANGED", "Stored localisation value differs from original bytes."
            )
        self.selected[(row["file_id"], row["ordinal"])] = value
        return value

    def coverage(self, key):
        return not bool(
            self.store.conn.execute(
                "SELECT 1 FROM opaque o JOIN snapshot_files m USING(file_id) WHERE m.sid=? AND o.suspected_key IN (?, '*') LIMIT 1",
                (self.snapshot_id, key),
            ).fetchone()
        )

    def fingerprint(self, language, key):
        values = self.definitions(language, key)
        return digest(
            [
                self.coverage(key),
                [
                    (
                        v.raw_value,
                        v.marker,
                        v.has_unsupported_escape,
                        v.source_ref.source_kind,
                        v.source_ref.source_id,
                        v.source_ref.relative_path,
                        v.occurrence,
                    )
                    for v in values
                ],
            ]
        )

    def resolve(self, key, language):
        cache_key = digest([VERSION, "name", key, language])
        self.complete = True
        cached = self.store.conn.execute(
            "SELECT * FROM derived WHERE key=?", (cache_key,)
        ).fetchone()
        if cached:
            try:
                payload = json.loads(cached["payload"])
                dependencies = json.loads(cached["dependencies"])
                if digest([dependencies, payload]) != cached["checksum"]:
                    raise ValueError()
                if any(self.fingerprint(lang, k) != sig for lang, k, sig in dependencies):
                    raise ValueError()
                used = payload["language_used"]
                root = self.definitions(used, key) if used else ()
                if used and len(root) != 1:
                    raise ValueError()
                selections = []
                for item in payload["reference_selections"]:
                    definitions = self.definitions(item["language_used"], item["key"])
                    if len(definitions) != 1:
                        raise ValueError()
                    selections.append(
                        LocalisationReferenceSelection(
                            item["key"], item["language_used"], definitions[0].source_ref
                        )
                    )
                diagnostics = tuple(
                    reader.LocalisationDiagnostic(**d) for d in payload["diagnostics"]
                )
                if any(d.source_ref is not None for d in diagnostics):
                    raise ValueError()
                result = LocalisationResolution(
                    payload["key"],
                    payload["language_requested"],
                    used,
                    payload["display_value"],
                    root[0].source_ref if root else None,
                    tuple(s.source_ref for s in selections),
                    payload["fallback"],
                    payload["resolution"],
                    diagnostics,
                    payload["visits"],
                    payload["scanned_bytes"],
                    payload["output_bytes"],
                    payload["truncated"],
                    tuple(selections),
                )
                return result, True
            except (KeyError, ValueError, TypeError):
                pass
        previous = self.queries
        self.queries = set()
        result = resolve_localisation(self, key, language)
        if not self.complete and result.resolution == "resolved":
            result = replace(
                result,
                resolution="partial",
                diagnostics=result.diagnostics
                + (
                    reader.LocalisationDiagnostic(
                        "LOC_INCOMPLETE_SOURCE",
                        "error",
                        "Lookup source contains an unreadable candidate.",
                    ),
                ),
            )
        dependencies = [(lang, k, self.fingerprint(lang, k)) for lang, k in sorted(self.queries)]
        self.queries |= previous
        if not self.store.read_only and all(d.source_ref is None for d in result.diagnostics):
            payload = result.to_dict()
            self.store.conn.execute(
                "INSERT OR REPLACE INTO derived VALUES(?,?,?,?)",
                (cache_key, packed(dependencies), packed(payload), digest([dependencies, payload])),
            )
        return result, False

    def documents(self):
        groups = defaultdict(list)
        for value in self.selected.values():
            groups[
                (
                    value.source_ref.source_kind,
                    value.source_ref.source_id,
                    value.source_ref.relative_path,
                )
            ].append(value)
        result = []
        for key, values in groups.items():
            context = SourceContext(self.snapshot_id, *key, values[0].source_ref.file_sha256)
            result.append(
                reader.LocalisationDocument(
                    tuple(values), (), (), (), (), True, context, values[0]._source
                )
            )
        return tuple(result)
