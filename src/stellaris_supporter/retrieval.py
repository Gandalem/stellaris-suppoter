"""Deterministic, snapshot-pinned retrieval over validated SQLite snapshot records.

The SQLite v1 schema is immutable. An ephemeral per-service projection is rebuilt
in bounded batches on the first query for a snapshot and reused on warm queries.
It is never authoritative; results refer back to SourceRefs in SnapshotRepository.
"""

from __future__ import annotations

import json
import re
import sqlite3
import threading
import unicodedata
from dataclasses import dataclass
from typing import Literal

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.storage import SnapshotError, SnapshotRepository

MAX_QUERY_LENGTH = 512
MAX_RESULTS = 100
MAX_ALIAS_COUNT = 1_000
MAX_INDEX_BYTES = 64 * 1024 * 1024
_ALLOWED_LANGUAGES = frozenset({"korean", "english"})
_ALLOWED_KINDS = frozenset({"technology"})
_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_Status = Literal["ok", "partial", "not_found", "unsupported", "error"]


def normalize_search(value: str) -> str:
    """NFC, Unicode casefold and whitespace collapse, for search terms only."""
    return unicodedata.normalize(
        "NFC", " ".join(unicodedata.normalize("NFC", value).casefold().split())
    )


def _like_literal(value: str) -> str:
    """Escape SQLite LIKE wildcards, including the escape character itself."""
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


@dataclass(frozen=True, slots=True)
class Query:
    text: str
    snapshot_id: str | None = None
    kind: str | None = None
    language: str = "korean"
    limit: int = 20


@dataclass(frozen=True, slots=True)
class VerifiedAlias:
    """Explicitly curated alias whose exact literal occurs in a verified source span."""

    snapshot_id: str
    entity_key: str
    text: str
    source_ref: SourceRef


@dataclass(frozen=True, slots=True)
class SearchDiagnostic:
    code: str
    severity: str
    message: str


@dataclass(frozen=True, slots=True)
class SearchContext:
    snapshot_id: str
    kind: str | None
    game_version: str | None
    checked_at: str | None
    snapshot_status: str


@dataclass(frozen=True, slots=True)
class SearchHit:
    snapshot_id: str
    entity_key: str
    game_id: str
    kind: str
    display_name: str
    match_reason: str
    language_requested: str
    language_used: str | None
    fallback: str
    resolution: str
    localisation_resolution: str
    definition_source_ref: SourceRef
    localisation_source_ref: SourceRef | None
    match_source_ref: SourceRef
    diagnostics: tuple[SearchDiagnostic, ...] = ()


@dataclass(frozen=True, slots=True)
class SearchResponse:
    schema_version: int
    status: _Status
    query: Query
    context: SearchContext | None
    results: tuple[SearchHit, ...]
    diagnostics: tuple[SearchDiagnostic, ...]
    truncated: bool
    fts5_available: bool


def _diagnostic(code: str, message: str, severity: str = "error") -> SearchDiagnostic:
    return SearchDiagnostic(code, severity, message)


def _ref(value: str | dict[str, object]) -> SourceRef:
    fields = json.loads(value) if isinstance(value, str) else value
    return SourceRef(**fields)


def _safe_name(value: str) -> bool:
    """Do not promote unknown references or dynamic markup to verified names."""
    return "$" not in value and "[" not in value and "]" not in value


class SearchService:
    """One-snapshot-at-a-time local projection; never parses game files or calls a model.

    Each query resolves the active pointer once. Projection construction streams
    authoritative DB rows with fetchmany(), never entities().fetchall().
    Missing/failed FTS does not remove ordinary exact/prefix/substring results.
    """

    def __init__(
        self,
        repository: SnapshotRepository,
        *,
        aliases: tuple[VerifiedAlias, ...] = (),
        enable_fts: bool = True,
    ) -> None:
        if not isinstance(repository, SnapshotRepository):
            raise TypeError("repository must be a SnapshotRepository")
        if len(aliases) > MAX_ALIAS_COUNT:
            raise SnapshotError("LIMIT_EXCEEDED", "Too many verified aliases.")
        self.repository = repository
        self.aliases = aliases
        self.enable_fts = enable_fts
        self._lock = threading.RLock()
        self._index: sqlite3.Connection | None = None
        self._indexed_sid: str | None = None
        self._fts_available = False

    @property
    def fts5_available(self) -> bool:
        return self._fts_available

    def close(self) -> None:
        with self._lock:
            if self._index is not None:
                self._index.close()
            self._index = None
            self._indexed_sid = None
            self._fts_available = False

    def _error(
        self, query: Query, code: str, message: str,
        context: SearchContext | None = None,
    ) -> SearchResponse:
        return SearchResponse(
            1, "error", query, context, (), (_diagnostic(code, message),),
            False, self._fts_available,
        )

    @staticmethod
    def _validate(query: Query) -> tuple[str | None, str | None]:
        if not isinstance(query, Query):
            return None, "Query must use the typed search contract."
        if not isinstance(query.text, str) or len(query.text) > MAX_QUERY_LENGTH:
            return None, "Search text must be a string of at most 512 characters."
        normalized = normalize_search(query.text)
        if not normalized:
            return None, "Search text cannot be empty or whitespace-only."
        if isinstance(query.limit, bool) or not isinstance(query.limit, int) or not (
            1 <= query.limit <= MAX_RESULTS
        ):
            return None, "Result limit must be an integer from 1 to 100."
        if query.kind is not None and (
            not isinstance(query.kind, str) or query.kind not in _ALLOWED_KINDS
        ):
            return None, "Requested entity kind is not supported."
        if not isinstance(query.language, str) or query.language not in _ALLOWED_LANGUAGES:
            return None, "Requested language must be korean or english."
        if query.snapshot_id is not None and (
            not isinstance(query.snapshot_id, str)
            or _SHA256.fullmatch(query.snapshot_id) is None
        ):
            return None, "Snapshot ID must be a lowercase SHA-256 identifier."
        return normalized, None

    def _new_index(self, sid: str) -> tuple[sqlite3.Connection, bool]:
        conn = sqlite3.connect(":memory:", isolation_level=None)
        conn.row_factory = sqlite3.Row
        conn.executescript("""
            CREATE TABLE entries (
                name_key TEXT NOT NULL, language TEXT NOT NULL,
                value TEXT NOT NULL, source_ref TEXT NOT NULL,
                unsupported INTEGER NOT NULL
            );
            CREATE INDEX entries_by_key ON entries(name_key,language);
            CREATE TABLE projection (
                entity_key TEXT PRIMARY KEY, game_id TEXT NOT NULL,
                kind TEXT NOT NULL, occurrence INTEGER NOT NULL,
                relative_path TEXT NOT NULL, definition_ref TEXT NOT NULL,
                candidate_resolution TEXT NOT NULL,
                korean TEXT, korean_ref TEXT, english TEXT, english_ref TEXT,
                chosen_resolution TEXT NOT NULL, warning TEXT
            );
            CREATE INDEX projection_by_id ON projection(game_id,kind);
            CREATE TABLE names (
                entity_key TEXT NOT NULL, language TEXT NOT NULL,
                normalized TEXT NOT NULL, source_ref TEXT NOT NULL
            );
            CREATE INDEX names_exact ON names(normalized,language,entity_key);
            CREATE TABLE descriptions (
                entity_key TEXT NOT NULL, normalized TEXT NOT NULL,
                source_ref TEXT NOT NULL
            );
            CREATE INDEX descriptions_entity ON descriptions(entity_key);
            CREATE TABLE aliases (
                entity_key TEXT NOT NULL, normalized TEXT NOT NULL,
                source_ref TEXT NOT NULL
            );
            CREATE INDEX alias_exact ON aliases(normalized,entity_key);
        """)
        fts = False
        if self.enable_fts:
            try:
                conn.execute(
                    "CREATE VIRTUAL TABLE descriptions_fts "
                    "USING fts5(entity_key UNINDEXED, body, tokenize='unicode61')"
                )
                fts = True
            except sqlite3.OperationalError:
                # Availability is a runtime capability, not a schema prerequisite.
                fts = False

        bytes_used = 0

        def charge(*values: str | None) -> None:
            nonlocal bytes_used
            for value in values:
                if value is not None:
                    bytes_used += len(value.encode("utf-8"))
            if bytes_used > MAX_INDEX_BYTES:
                raise SnapshotError(
                    "LIMIT_EXCEEDED", "Synthetic search projection exceeds 64 MiB budget."
                )

        def translated(
            key: str, language: str
        ) -> tuple[str | None, str | None, str]:
            rows = conn.execute(
                "SELECT value,source_ref,unsupported FROM entries "
                "WHERE name_key=? AND language=? LIMIT 2", (key, language),
            ).fetchall()
            if len(rows) > 1:
                return None, None, "ambiguous"
            if not rows:
                return None, None, "missing"
            if rows[0]["unsupported"] or not _safe_name(rows[0]["value"]):
                return None, None, "partial"
            return rows[0]["value"], rows[0]["source_ref"], "resolved"

        try:
            conn.execute("BEGIN")
            for row in self.repository.iter_search_rows(sid, "localisation"):
                payload = json.loads(row["entry_json"])
                if row["language"] not in _ALLOWED_LANGUAGES:
                    continue
                val = row["display_value"]
                span = json.dumps(payload["value_source_ref"], ensure_ascii=False)
                charge(row["localisation_key"], val, span)
                conn.execute(
                    "INSERT INTO entries VALUES(?,?,?,?,?)",
                    (
                        row["localisation_key"], row["language"], val, span,
                        int(payload["has_unsupported_escape"]),
                    ),
                )

            for row in self.repository.iter_search_rows(sid, "entities"):
                key = row["game_id"]
                korean, ko_ref, ko_resolution = translated(key, "korean")
                english, en_ref, en_resolution = translated(key, "english")
                resolved = json.loads(row["localisation_json"]) if row["localisation_json"] else None
                if resolved is not None and resolved["resolution"] == "resolved":
                    used = resolved["language_used"]
                    selected = resolved["display_value"]
                    selected_ref = resolved["source_ref"]
                    if used in _ALLOWED_LANGUAGES and selected_ref is not None:
                        loc_json = json.dumps(selected_ref, ensure_ascii=False)
                        if used == "korean":
                            korean, ko_ref, ko_resolution = selected, loc_json, "resolved"
                        elif used == "english":
                            english, en_ref, en_resolution = selected, loc_json, "resolved"

                warning = None
                if ko_resolution == "ambiguous" or en_resolution == "ambiguous":
                    warning = "LOC_DUPLICATE_KEY"
                elif ko_resolution == "partial" or en_resolution == "partial":
                    warning = "LOC_DYNAMIC_UNSUPPORTED"
                if resolved is not None and resolved["resolution"] in {"ambiguous", "partial"}:
                    warning = "LOC_" + resolved["resolution"].upper()
                chosen_resolution = (
                    resolved["resolution"] if resolved is not None
                    else ("ambiguous" if warning == "LOC_DUPLICATE_KEY" else "unresolved")
                )
                def_ref = {
                    "snapshot_id": sid, "source_kind": row["source_kind"],
                    "source_id": row["source_id"], "relative_path": row["relative_path"],
                    "file_sha256": row["file_sha256"],
                    "byte_start": row["byte_start"], "byte_end": row["byte_end"],
                    "line_start": row["line_start"], "line_end": row["line_end"],
                }
                def_json = json.dumps(def_ref, ensure_ascii=False)
                charge(key, row["relative_path"], def_json, korean, english)
                conn.execute(
                    "INSERT INTO projection VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)",
                    (
                        row["entity_key"], key, row["kind"], row["occurrence"],
                        row["relative_path"], def_json, row["resolution"],
                        korean, ko_ref, english, en_ref, chosen_resolution, warning,
                    ),
                )
                for language, value, ref in (
                    ("korean", korean, ko_ref), ("english", english, en_ref)
                ):
                    if value and ref:
                        conn.execute(
                            "INSERT INTO names VALUES(?,?,?,?)",
                            (row["entity_key"], language, normalize_search(value), ref),
                        )
                for language in ("korean", "english"):
                    description, desc_ref, status = translated(key + "_desc", language)
                    if description and desc_ref and status == "resolved":
                        normalized = normalize_search(description)
                        charge(normalized, desc_ref)
                        conn.execute(
                            "INSERT INTO descriptions VALUES(?,?,?)",
                            (row["entity_key"], normalized, desc_ref),
                        )
                        if fts:
                            conn.execute(
                                "INSERT INTO descriptions_fts(entity_key,body) VALUES(?,?)",
                                (row["entity_key"], normalized),
                            )

            for alias in self.aliases:
                if alias.snapshot_id != sid:
                    continue
                if not isinstance(alias.text, str) or not alias.text.strip() or (
                    len(alias.text) > MAX_QUERY_LENGTH
                ):
                    raise SnapshotError("QUERY_INVALID", "Verified alias text is invalid.")
                if alias.source_ref.snapshot_id != sid:
                    raise SnapshotError("SOURCE_CHANGED", "Alias belongs to another snapshot.")
                record = conn.execute(
                    "SELECT 1 FROM projection WHERE entity_key=?", (alias.entity_key,)
                ).fetchone()
                if record is None:
                    raise SnapshotError("SOURCE_CHANGED", "Alias entity was not found in snapshot.")
                content = self.repository.source_bytes(alias.source_ref).decode("utf-8")
                if normalize_search(alias.text) not in normalize_search(content):
                    raise SnapshotError("SOURCE_CHANGED", "Alias literal is not supported by SourceRef.")
                ref_json = json.dumps(alias.source_ref.to_dict(), ensure_ascii=False)
                charge(alias.text, ref_json)
                conn.execute(
                    "INSERT INTO aliases VALUES(?,?,?)",
                    (alias.entity_key, normalize_search(alias.text), ref_json),
                )
            conn.execute("COMMIT")
            return conn, fts
        except BaseException:
            if conn.in_transaction:
                conn.execute("ROLLBACK")
            conn.close()
            raise

    def _index_for(self, sid: str) -> sqlite3.Connection:
        if self._indexed_sid != sid or self._index is None:
            new_index, fts = self._new_index(sid)
            old_index = self._index
            self._index, self._indexed_sid, self._fts_available = new_index, sid, fts
            if old_index is not None:
                old_index.close()
        assert self._index is not None
        return self._index

    @staticmethod
    def _sql_matches(
        indexed: sqlite3.Connection, term: str, query: Query, use_fts: bool
    ) -> list[sqlite3.Row]:
        prefix = _like_literal(term) + "%"
        substring = "%" + _like_literal(term) + "%"
        # FTS is strictly an optional extra path. The ordinary LIKE path
        # remains authoritative for short Korean, punctuation and no-FTS parity.
        union = """
            SELECT p.entity_key,1 AS rank,'game_id_exact' AS reason,'' AS matched_language,
                   p.definition_ref AS match_ref FROM projection p WHERE p.game_id=?
            UNION ALL
            SELECT n.entity_key,2,'name_exact',n.language,n.source_ref
              FROM names n WHERE n.normalized=? AND n.language IN ({languages})
            UNION ALL
            SELECT a.entity_key,3,'alias_exact','',a.source_ref
              FROM aliases a WHERE a.normalized=?
            UNION ALL
            SELECT n.entity_key,4,'name_prefix',n.language,n.source_ref
              FROM names n WHERE n.normalized LIKE ? ESCAPE char(92) AND n.language IN ({languages})
            UNION ALL
            SELECT n.entity_key,5,'name_substring',n.language,n.source_ref
              FROM names n WHERE n.normalized LIKE ? ESCAPE char(92) AND n.language IN ({languages})
            UNION ALL
            SELECT d.entity_key,6,'description_lexical','',d.source_ref
              FROM descriptions d WHERE d.normalized LIKE ? ESCAPE char(92)
        """
        lang_sql = "?,?" if query.language == "korean" else "?"
        # Only constant SQL fragments are interpolated, never an input term,
        # snapshot ID, kind, language value or alias.
        parts = [union.format(languages=lang_sql)]
        allowed = (query.language, "english") if query.language == "korean" else ("english",)
        params: list[object] = [
            query.text, term, *allowed, term, prefix, *allowed,
            substring, *allowed, substring,
        ]
        if use_fts:
            parts.append("""
                SELECT d.entity_key,6,'description_lexical','',d.source_ref
                FROM descriptions_fts
                JOIN descriptions d ON d.entity_key=descriptions_fts.entity_key
                WHERE descriptions_fts MATCH ? AND d.normalized LIKE ? ESCAPE char(92)
            """)
            params.extend(['"' + term.replace('"', '""') + '"', substring])
        kind_filter = "" if query.kind is None else "WHERE p.kind=?"
        if query.kind is not None:
            params.append(query.kind)
        # Choose one reason for each entity at the smallest rank, with stable
        # language tie-breaking; do not collapse distinct entity_keys.
        sql = f"""
            WITH matches AS ({' UNION ALL '.join(parts)}),
            chosen AS (
                SELECT m.*, ROW_NUMBER() OVER (
                    PARTITION BY m.entity_key
                    ORDER BY m.rank,
                    CASE WHEN m.matched_language=? THEN 0 ELSE 1 END,
                    m.matched_language, m.match_ref
                ) AS selected
                FROM matches m
            )
            SELECT p.*,c.rank,c.reason,c.matched_language,c.match_ref,
                (SELECT count(*) FROM projection duplicates
                 WHERE duplicates.kind=p.kind AND duplicates.game_id=p.game_id) AS duplicates
            FROM chosen c JOIN projection p ON p.entity_key=c.entity_key
            {kind_filter} AND c.selected=1
            ORDER BY c.rank,p.kind,p.game_id,p.relative_path,p.occurrence,p.entity_key
            LIMIT ?
        """
        # If there is no kind predicate, use WHERE instead of AND.
        if query.kind is None:
            sql = sql.replace("AND c.selected=1", "WHERE c.selected=1")
        params.insert(len(params) - (1 if query.kind is not None else 0), query.language)
        params.append(query.limit + 1)
        return indexed.execute(sql, params).fetchall()

    def search(self, query: Query) -> SearchResponse:
        if not isinstance(query, Query):
            safe = Query("")
            return self._error(safe, "QUERY_INVALID", "Typed Query is required.")
        term, error = self._validate(query)
        if error is not None or term is None:
            return self._error(query, "QUERY_INVALID", error or "Invalid query.")
        with self._lock:
            context: SearchContext | None = None
            try:
                # Resolve the pointer exactly once; a concurrent activation
                # cannot make one response span two snapshot IDs.
                meta = self.repository.search_snapshot(query.snapshot_id)
                sid = str(meta["snapshot_id"])
                context = SearchContext(
                    sid, query.kind, meta["game_version"], meta["checked_at"],
                    str(meta["status"]),
                )
                index = self._index_for(sid)
                try:
                    rows = self._sql_matches(index, term, query, self._fts_available)
                except sqlite3.OperationalError:
                    if not self._fts_available:
                        raise
                    # FTS implementation may reject even a quoted literal:
                    # an ordinary safe lexical path must still run.
                    rows = self._sql_matches(index, term, query, False)
                truncated = len(rows) > query.limit
                verified_files: set[tuple[str, str, str, str]] = set()
                hits: list[SearchHit] = []
                any_partial = meta["status"] == "partial"
                for row in rows[:query.limit]:
                    definition = _ref(row["definition_ref"])
                    used: str | None = None
                    fallback = "id"
                    localisation_source: SourceRef | None = None
                    chosen_status = str(row["chosen_resolution"])
                    if query.language == "korean":
                        if row["korean"] is not None and row["korean_ref"]:
                            used, fallback = "korean", "none"
                            localisation_source = _ref(row["korean_ref"])
                            display = row["korean"]
                        elif row["english"] is not None and row["english_ref"]:
                            used, fallback = "english", "english"
                            localisation_source = _ref(row["english_ref"])
                            display = row["english"]
                        else:
                            display = row["game_id"]
                    elif row["english"] is not None and row["english_ref"]:
                        used, fallback = "english", "none"
                        localisation_source = _ref(row["english_ref"])
                        display = row["english"]
                    else:
                        display = row["game_id"]
                    match_source = _ref(row["match_ref"])
                    for source in (definition, localisation_source, match_source):
                        if source is None:
                            continue
                        if source.snapshot_id != sid:
                            raise SnapshotError("SOURCE_CHANGED", "Search provenance snapshot mismatched.")
                        file_key = (
                            source.source_kind, source.source_id,
                            source.relative_path, source.file_sha256,
                        )
                        if file_key not in verified_files:
                            self.repository.source_bytes(source)
                            verified_files.add(file_key)
                    diagnostics: list[SearchDiagnostic] = []
                    resolution = row["candidate_resolution"]
                    if row["duplicates"] > 1:
                        resolution = "ambiguous"
                        diagnostics.append(_diagnostic(
                            "DUPLICATE_GAME_ID", "Multiple definitions share this game ID.", "warning"
                        ))
                    if row["warning"]:
                        any_partial = True
                        diagnostics.append(_diagnostic(
                            row["warning"], "Localisation is ambiguous or unsupported.", "warning"
                        ))
                    if fallback == "id":
                        any_partial = True
                        diagnostics.append(_diagnostic(
                            "LOC_MISSING_TRANSLATION", "Result uses the original game ID.", "warning"
                        ))
                    if resolution in {"ambiguous", "partial"} or chosen_status != "resolved":
                        any_partial = True
                    hits.append(SearchHit(
                        sid, row["entity_key"], row["game_id"], row["kind"], display,
                        row["reason"], query.language, used, fallback, resolution,
                        chosen_status, definition, localisation_source, match_source,
                        tuple(diagnostics),
                    ))
                report: list[SearchDiagnostic] = []
                if meta["status"] == "partial":
                    report.append(_diagnostic(
                        "PARTIAL_SNAPSHOT", "Snapshot is incomplete; results may be partial.", "warning"
                    ))
                if truncated:
                    report.append(_diagnostic(
                        "RESULT_LIMIT", "Results were bounded by the requested limit.", "warning"
                    ))
                if not hits and not any_partial:
                    status: _Status = "not_found"
                elif any_partial or truncated:
                    status = "partial"
                else:
                    status = "ok"
                return SearchResponse(
                    1, status, query, context, tuple(hits), tuple(report),
                    truncated, self._fts_available,
                )
            except SnapshotError as exc:
                return self._error(query, exc.code, str(exc), context)
            except (sqlite3.DatabaseError, ValueError, KeyError, TypeError, UnicodeError):
                return self._error(
                    query, "SQLITE_ERROR",
                    "Search projection or its stored provenance is invalid.", context,
                )
