"""Content-bound, optional persistent search projection. Canonical rows remain authoritative."""

from __future__ import annotations

import hashlib
import json
import os
import sqlite3
import tempfile
from pathlib import Path

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.cache import _ensure_directory, _read_verified_file

VERSION = "search-projection-3"
MAX_BYTES = 128 * 1024 * 1024


def fingerprint(repo, sid, enable_fts):
    value = hashlib.sha256((VERSION + sid + str(enable_fts) + sqlite3.sqlite_version).encode())
    for kind in ("entities", "localisation"):
        for row in repo.iter_search_rows(sid, kind):
            value.update(
                json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()
            )
    with repo._connection(read_only=True) as conn:
        for row in conn.execute(
            "SELECT entity_key,document_kind,content_json FROM search_documents WHERE snapshot_id=? ORDER BY entity_key,document_kind",
            (sid,),
        ):
            value.update(json.dumps(tuple(row), ensure_ascii=False).encode())
    return value.hexdigest()


def load(repo, key):
    with repo._connection(read_only=True) as conn:
        row = conn.execute(
            "SELECT value FROM settings WHERE key=?", (VERSION + ":" + key,)
        ).fetchone()
    if not row:
        return None
    path = repo.data_dir / "search-projections" / (key + ".sqlite3")
    try:
        meta = json.loads(row[0])
        if not 0 < meta["size"] <= MAX_BYTES:
            return None
        _check_components(path)
        _read_verified_file(path, expected_hash=meta["sha"], expected_size=meta["size"])
        index = sqlite3.connect(
            path.as_uri() + "?mode=ro&immutable=1", uri=True, isolation_level=None
        )
        index.row_factory = sqlite3.Row
        index.execute("PRAGMA trusted_schema=OFF")
        if index.execute("PRAGMA quick_check").fetchone()[0] != "ok":
            index.close()
            return None
        return index, bool(meta["fts"])
    except (OSError, ValueError, KeyError, TypeError, sqlite3.DatabaseError, SnapshotError):
        return None


def save(repo, key, index, fts):
    directory = repo.data_dir / "search-projections"
    _ensure_directory(directory)
    path = directory / (key + ".sqlite3")
    _check_components(path)
    fd, temp = tempfile.mkstemp(prefix="projection-", suffix=".sqlite3", dir=directory)
    os.close(fd)
    try:
        output = sqlite3.connect(temp)
        try:
            index.backup(output)
        finally:
            output.close()
        size = Path(temp).stat().st_size
        if size > MAX_BYTES:
            return
        sha = hashlib.sha256(Path(temp).read_bytes()).hexdigest()
        _check_components(path)
        os.replace(temp, path)
        with repo._connection() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings VALUES(?,?)",
                (VERSION + ":" + key, json.dumps({"size": size, "sha": sha, "fts": fts})),
            )
    finally:
        Path(temp).unlink(missing_ok=True)
