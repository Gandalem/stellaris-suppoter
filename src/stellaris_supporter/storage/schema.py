"""SQLite v1 schema; foreign-key-bound immutable snapshot rows.

Only this module knows the database DDL. Full migration is intentionally not
attempted: older/newer or malformed schema is rejected, never silently reset.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

from stellaris_supporter.storage.identity import SCHEMA_VERSION, SnapshotError

TABLES = frozenset({
    "snapshots", "source_files", "entities", "localisation_entries",
    "relations", "search_documents", "diagnostics", "settings",
})

DDL = """
CREATE TABLE IF NOT EXISTS snapshots (
    snapshot_id TEXT PRIMARY KEY,
    content_hash TEXT NOT NULL,
    schema_version INTEGER NOT NULL CHECK(schema_version = 1),
    parser_version TEXT NOT NULL,
    adapter_version TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    context_kind TEXT NOT NULL,
    policy_json TEXT NOT NULL,
    game_version TEXT,
    game_version_source TEXT NOT NULL,
    build_id TEXT,
    branch TEXT NOT NULL,
    dlc_state_json TEXT NOT NULL,
    mod_state TEXT NOT NULL,
    created_at TEXT NOT NULL,
    checked_at TEXT,
    status TEXT NOT NULL CHECK(status IN ('building','ready','partial','failed')),
    security_ok INTEGER NOT NULL CHECK(security_ok IN (0,1)),
    diagnostics_json TEXT NOT NULL DEFAULT '[]'
);
CREATE TABLE IF NOT EXISTS source_files (
    snapshot_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    file_sha256 TEXT NOT NULL,
    byte_size INTEGER NOT NULL CHECK(byte_size >= 0),
    cache_sha256 TEXT NOT NULL CHECK(cache_sha256 = file_sha256),
    live_required INTEGER NOT NULL CHECK(live_required IN (0,1)),
    live_relative_path TEXT,
    live_root_sha256 TEXT,
    CHECK (
        (live_required = 0 AND live_relative_path IS NULL AND live_root_sha256 IS NULL)
        OR
        (live_required = 1 AND live_relative_path IS NOT NULL
         AND live_root_sha256 IS NOT NULL)
    ),
    PRIMARY KEY(snapshot_id,source_kind,source_id,relative_path),
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_sources_hash ON source_files(cache_sha256);
CREATE TABLE IF NOT EXISTS entities (
    snapshot_id TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    game_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    occurrence INTEGER NOT NULL CHECK(occurrence >= 1),
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    byte_start INTEGER NOT NULL CHECK(byte_start >= 0),
    byte_end INTEGER NOT NULL CHECK(byte_end >= byte_start),
    resolution TEXT NOT NULL CHECK(resolution IN ('raw_definition','resolved','partial','ambiguous')),
    candidate_json TEXT NOT NULL,
    localisation_json TEXT,
    PRIMARY KEY(snapshot_id,entity_key),
    UNIQUE(snapshot_id,source_kind,source_id,relative_path,byte_start,byte_end,kind,occurrence),
    FOREIGN KEY(snapshot_id,source_kind,source_id,relative_path)
      REFERENCES source_files(snapshot_id,source_kind,source_id,relative_path)
);
CREATE INDEX IF NOT EXISTS idx_entities_game ON entities(snapshot_id,kind,game_id,entity_key);
CREATE TABLE IF NOT EXISTS localisation_entries (
    snapshot_id TEXT NOT NULL,
    source_kind TEXT NOT NULL,
    source_id TEXT NOT NULL,
    relative_path TEXT NOT NULL,
    language TEXT NOT NULL,
    localisation_key TEXT NOT NULL,
    occurrence INTEGER NOT NULL CHECK(occurrence >= 1),
    marker TEXT,
    raw_value TEXT NOT NULL,
    display_value TEXT NOT NULL,
    has_unsupported_escape INTEGER NOT NULL CHECK(has_unsupported_escape IN (0,1)),
    byte_start INTEGER NOT NULL CHECK(byte_start >= 0),
    byte_end INTEGER NOT NULL CHECK(byte_end >= byte_start),
    entry_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id,source_kind,source_id,relative_path,language,localisation_key,occurrence),
    FOREIGN KEY(snapshot_id,source_kind,source_id,relative_path)
      REFERENCES source_files(snapshot_id,source_kind,source_id,relative_path)
);
CREATE INDEX IF NOT EXISTS idx_loc_lookup ON localisation_entries(snapshot_id,language,localisation_key);
CREATE TABLE IF NOT EXISTS relations (
    snapshot_id TEXT NOT NULL,
    from_entity_key TEXT NOT NULL,
    occurrence INTEGER NOT NULL CHECK(occurrence >= 1),
    relation_kind TEXT NOT NULL,
    target_game_id TEXT NOT NULL,
    target_entity_key TEXT,
    status TEXT NOT NULL CHECK(status IN ('resolved','unresolved','ambiguous')),
    source_ref_json TEXT NOT NULL,
    conditions_raw TEXT,
    PRIMARY KEY(snapshot_id,from_entity_key,occurrence),
    FOREIGN KEY(snapshot_id,from_entity_key) REFERENCES entities(snapshot_id,entity_key),
    FOREIGN KEY(snapshot_id,target_entity_key) REFERENCES entities(snapshot_id,entity_key)
);
CREATE TABLE IF NOT EXISTS search_documents (
    snapshot_id TEXT NOT NULL,
    entity_key TEXT NOT NULL,
    document_kind TEXT NOT NULL,
    content_json TEXT NOT NULL,
    PRIMARY KEY(snapshot_id,entity_key,document_kind),
    FOREIGN KEY(snapshot_id,entity_key) REFERENCES entities(snapshot_id,entity_key)
);
CREATE TABLE IF NOT EXISTS diagnostics (
    snapshot_id TEXT NOT NULL,
    ordinal INTEGER NOT NULL CHECK(ordinal >= 0),
    code TEXT NOT NULL,
    severity TEXT NOT NULL CHECK(severity IN ('info','warning','error')),
    message TEXT NOT NULL,
    source_ref_json TEXT,
    PRIMARY KEY(snapshot_id,ordinal),
    FOREIGN KEY(snapshot_id) REFERENCES snapshots(snapshot_id) ON DELETE CASCADE
);
CREATE TABLE IF NOT EXISTS settings (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
"""

REQUIRED_COLUMNS = {
    "snapshots": {"snapshot_id", "status", "security_ok", "policy_json"},
    "source_files": {"snapshot_id", "source_kind", "source_id", "relative_path", "file_sha256", "cache_sha256", "live_required",
                     "live_relative_path", "live_root_sha256"},
    "entities": {"snapshot_id", "entity_key", "candidate_json", "localisation_json"},
    "localisation_entries": {"snapshot_id", "localisation_key", "occurrence", "entry_json"},
    "relations": {"snapshot_id", "from_entity_key", "target_entity_key"},
    "search_documents": {"snapshot_id", "entity_key"},
    "diagnostics": {"snapshot_id", "code"},
    "settings": {"key", "value"},
}


def connect(db_path: Path, *, read_only: bool = False, timeout: float = 0.25) -> sqlite3.Connection:
    try:
        if read_only:
            connection = sqlite3.connect(
                db_path.as_uri() + "?mode=ro", uri=True, isolation_level=None, timeout=timeout
            )
        else:
            connection = sqlite3.connect(db_path, isolation_level=None, timeout=timeout)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 250")
        if not read_only:
            connection.execute("PRAGMA journal_mode = WAL")
            connection.execute("PRAGMA synchronous = FULL")
        return connection
    except sqlite3.DatabaseError as exc:
        if "locked" in str(exc).lower() or "busy" in str(exc).lower():
            raise SnapshotError("SQLITE_BUSY", "Another SQLite writer holds the database.") from exc
        raise SnapshotError("SQLITE_ERROR", "Could not open the snapshot database.") from exc


def check_schema(connection: sqlite3.Connection) -> None:
    try:
        version = connection.execute("PRAGMA user_version").fetchone()[0]
        if version != SCHEMA_VERSION:
            raise SnapshotError(
                "SCHEMA_VERSION_UNSUPPORTED",
                "Database schema version is not supported; migration is not automatic.",
            )
        tables = {
            row[0] for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            )
        }
        if not TABLES <= tables:
            raise SnapshotError("SCHEMA_ERROR", "Database has missing schema tables.")
        for table, required in REQUIRED_COLUMNS.items():
            # Table name is a constant from our own whitelist, never user input.
            columns = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            if not required <= columns:
                raise SnapshotError("SCHEMA_ERROR", "Database table layout is incomplete.")
        schema_row = connection.execute(
            "SELECT value FROM settings WHERE key='schema_version'"
        ).fetchone()
        if schema_row is None or schema_row[0] != str(SCHEMA_VERSION):
            raise SnapshotError("SCHEMA_VERSION_UNSUPPORTED", "Schema metadata does not match.")
        if connection.execute("PRAGMA foreign_keys").fetchone()[0] != 1:
            raise SnapshotError("SCHEMA_ERROR", "Foreign keys are disabled.")
        if connection.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            raise SnapshotError("SCHEMA_ERROR", "Database integrity check failed.")
    except sqlite3.DatabaseError as exc:
        raise SnapshotError("SCHEMA_ERROR", "Database schema or integrity is invalid.") from exc


def initialise_schema(connection: sqlite3.Connection, *, new_db: bool) -> None:
    if not new_db:
        check_schema(connection)
        return
    try:
        connection.execute("BEGIN IMMEDIATE")
        for ddl in DDL.split(";"):
            if ddl.strip():
                connection.execute(ddl)
        connection.execute(f"PRAGMA user_version = {SCHEMA_VERSION}")
        connection.execute(
            "INSERT INTO settings(key,value) VALUES('schema_version',?)",
            (str(SCHEMA_VERSION),),
        )
        connection.execute("COMMIT")
        check_schema(connection)
    except (sqlite3.DatabaseError, SnapshotError) as exc:
        if connection.in_transaction:
            connection.execute("ROLLBACK")
        raise SnapshotError("SCHEMA_ERROR", "Failed to initialise snapshot schema.") from exc
