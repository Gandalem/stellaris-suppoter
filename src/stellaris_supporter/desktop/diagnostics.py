"""Bounded local error metadata; excludes query text, game data and absolute paths."""
from __future__ import annotations

import json
import os
import sqlite3
import threading
import traceback
from datetime import UTC, datetime

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.cache import _ensure_directory

MAX_BYTES = 256 * 1024
_LOCK = threading.Lock()


def record_error(directory, stage, error, context=None):
    """Best effort diagnostic recording must never replace the original error."""
    try:
        chain = []
        item = error
        while item is not None and len(chain) < 4:
            entry = {"type": type(item).__name__}
            if isinstance(item, (SnapshotError, sqlite3.Error)):
                entry["message"] = str(item)[:500]
            if isinstance(item, SnapshotError):
                entry["code"] = item.code
            if isinstance(item, sqlite3.Error):
                entry["sqlite_code"] = getattr(item, "sqlite_errorcode", None)
                entry["sqlite_name"] = getattr(item, "sqlite_errorname", None)
            chain.append(entry)
            item = item.__cause__
        frames = [{"file": os.path.basename(frame.filename), "line": frame.lineno,
                   "function": frame.name}
                  for frame in traceback.extract_tb(error.__traceback__)[-16:]]
        event = {"time": datetime.now(UTC).isoformat(), "pid": os.getpid(),
                 "thread": threading.get_ident(), "stage": stage,
                 "sqlite_version": sqlite3.sqlite_version, "errors": chain, "frames": frames,
                 "storage": context}
        raw = (json.dumps(event, ensure_ascii=False) + "\n").encode("utf-8")
        folder = directory / "diagnostics"
        path = folder / "errors.jsonl"
        previous = folder / "errors.previous.jsonl"
        with _LOCK:
            _ensure_directory(folder)
            _check_components(path)
            _check_components(previous)
            if path.exists() and path.stat().st_size + len(raw) > MAX_BYTES:
                os.replace(path, previous)
            flags = os.O_WRONLY | os.O_APPEND | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0)
            fd = os.open(path, flags, 0o600)
            with os.fdopen(fd, "ab") as stream:
                stream.write(raw)
    except (OSError, ValueError, TypeError, SnapshotError):
        pass
