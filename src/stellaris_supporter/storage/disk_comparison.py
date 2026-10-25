"""Streaming translation comparison over immutable per-file products."""

from __future__ import annotations

import itertools
import json
from collections import Counter

from stellaris_supporter.storage import SnapshotError

MAX_SCAN_ROWS = 2_000_000
MAX_SCAN_BYTES = 256 * 1024 * 1024
MAX_WINDOW_BYTES = 8 * 1024 * 1024


def change_key(item):
    sections = {"entities": 0, "localisation": 1, "files": 2}
    kinds = {"modified": 0, "added": 1, "removed": 2, "ambiguous": 3, "source_changed": 4}
    return (
        sections[item["section"]],
        kinds[item["change_kind"]],
        item["kind"],
        item["game_id"],
        item.get("language", ""),
        json.dumps(
            item.get("before") or item.get("before_candidates"), sort_keys=True, ensure_ascii=False
        ),
    )


class ChangeWindow:
    def __init__(self, limit, initial=()):
        self.limit = limit
        self.items = []
        self.count = 0
        self.kinds = Counter()
        self.sections = Counter()
        self.ambiguous = False
        self.extend(initial)

    def extend(self, values):
        for value in values:
            self.count += 1
            self.kinds[value["change_kind"]] += 1
            self.sections[value["section"]] += 1
            self.ambiguous |= value["change_kind"] == "ambiguous"
            if len(self.items) >= self.limit and change_key(value) >= change_key(self.items[-1]):
                continue
            self.items.append(value)
            self.items.sort(key=change_key)
            if len(self.items) > self.limit:
                self.items.pop()
            if (
                sum(len(json.dumps(v, ensure_ascii=False).encode()) for v in self.items)
                > MAX_WINDOW_BYTES
            ):
                raise SnapshotError("LIMIT_EXCEEDED", "Comparison page window exceeds byte limit.")

    def sort(self, **kwargs):
        self.items.sort(**kwargs)

    def __len__(self):
        return self.count

    def __iter__(self):
        return iter(self.items)

    def __getitem__(self, key):
        return self.items[key]


class DiskEntries:
    def __init__(self, catalogue):
        self.catalogue = catalogue
        self.complete = catalogue.source_complete
        manifest = catalogue.store.conn.execute(
            "SELECT file_id,product_hash FROM snapshot_files WHERE sid=?", (catalogue.snapshot_id,)
        ).fetchall()
        for row in manifest:
            catalogue.store.verify_file(row[0], row[1])

    def groups(self, keys=None):
        catalog = self.catalogue
        sql = "SELECT e.*,f.source_kind,f.source_id,f.path,f.sha FROM entries e JOIN snapshot_files m USING(file_id) JOIN file_versions f USING(file_id) WHERE m.sid=?"
        args = [catalog.snapshot_id]
        if keys is not None:
            keys = sorted(keys)
            if not keys:
                return
            if len(keys) > 10000:
                raise SnapshotError("LIMIT_EXCEEDED", "Comparison key filter exceeds budget.")
            sql += " AND e.key IN (" + ",".join("?" for _ in keys) + ")"
            args += keys
        sql += " ORDER BY e.language,e.key,f.source_kind,f.source_id,f.path,e.occurrence"
        cursor = catalog.store.conn.execute(sql, args)
        count = size = 0
        for key, rows in itertools.groupby(cursor, key=lambda r: (r["language"], r["key"])):
            group = []
            for row in rows:
                count += 1
                size += len(row["raw"].encode()) + len(row["display"].encode())
                if count > MAX_SCAN_ROWS or size > MAX_SCAN_BYTES or len(group) >= 4096:
                    raise SnapshotError(
                        "LIMIT_EXCEEDED", "Streaming translation comparison exceeded its budget."
                    )
                ref = {
                    "snapshot_id": catalog.snapshot_id,
                    "source_kind": row["source_kind"],
                    "source_id": row["source_id"],
                    "relative_path": row["path"],
                    "file_sha256": row["sha"],
                    "byte_start": row["start"],
                    "byte_end": row["end"],
                    "line_start": row["line"],
                    "line_end": row["line"],
                }
                group.append(
                    {
                        "language": row["language"],
                        "key": row["key"],
                        "marker": row["marker"],
                        "raw_value": row["raw"],
                        "display_value": row["display"],
                        "has_unsupported_escape": bool(row["unsupported"]),
                        "source_ref": ref,
                    }
                )
            yield key, group


def translation_changes(left, right, include_source, keys=None):
    def groups(value):
        return iter(
            value.groups(keys)
            if isinstance(value, DiskEntries)
            else ((key, value[key]) for key in sorted(value) if keys is None or key[1] in keys)
        )

    a, b = groups(left), groups(right)
    x, y = next(a, None), next(b, None)
    complete = getattr(left, "complete", True) and getattr(right, "complete", True)
    while x is not None or y is not None:
        key = min(x[0] if x else y[0], y[0] if y else x[0])
        before = x[1] if x and x[0] == key else []
        after = y[1] if y and y[0] == key else []
        if x and x[0] == key:
            x = next(a, None)
        if y and y[0] == key:
            y = next(b, None)

        def semantic(values):
            return [(v["marker"], v["raw_value"], v["has_unsupported_escape"]) for v in values]

        def location(values):
            return [
                tuple(
                    v["source_ref"][k]
                    for k in (
                        "source_kind",
                        "source_id",
                        "relative_path",
                        "byte_start",
                        "byte_end",
                        "line_start",
                        "line_end",
                    )
                )
                for v in values
            ]

        if semantic(before) == semantic(after):
            if not include_source or location(before) == location(after):
                continue
            kind = "source_changed"
        elif not before or not after:
            if not complete:
                continue
            kind = "added" if not before else "removed"
        else:
            kind = "ambiguous" if len(before) > 1 or len(after) > 1 else "modified"
        yield {
            "section": "localisation",
            "change_kind": kind,
            "kind": "localisation",
            "game_id": key[1],
            "language": key[0],
            "before": before,
            "after": after,
            "details": [],
            "coverage_complete": complete,
        }
