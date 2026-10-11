"""Non-gating synthetic SQL projection benchmark for TASK-011.

Measures the ranked bounded SQL query path, not end-to-end snapshot staging,
cache checks, cold SearchService projection builds or real Stellaris performance.
"""

from __future__ import annotations

import hashlib
import json
import os
import platform
import sqlite3
import sys
import time

from stellaris_supporter.retrieval import Query, SearchService


def measure(size: int) -> dict[str, object]:
    db = sqlite3.connect(":memory:")
    db.row_factory = sqlite3.Row
    db.executescript("""
        CREATE TABLE projection (
            entity_key TEXT PRIMARY KEY,game_id TEXT,kind TEXT,occurrence INTEGER,
            relative_path TEXT,definition_ref TEXT,candidate_resolution TEXT,
            korean TEXT,korean_ref TEXT,english TEXT,english_ref TEXT,
            chosen_resolution TEXT,warning TEXT
        );
        CREATE TABLE names (entity_key TEXT,language TEXT,normalized TEXT,source_ref TEXT);
        CREATE TABLE descriptions (entity_key TEXT,normalized TEXT,source_ref TEXT);
        CREATE TABLE aliases (entity_key TEXT,normalized TEXT,source_ref TEXT);
        CREATE INDEX name_exact ON names(normalized,language,entity_key);
        CREATE INDEX alias_exact ON aliases(normalized,entity_key);
        CREATE INDEX projection_id ON projection(game_id,kind);
    """)
    digest = hashlib.sha256()
    rows = []
    names = []
    descriptions = []
    for i in range(size):
        key = f"demo_{i:05d}"
        ko = f"합금 연구 {i:05d}"
        en = f"Alloy Research {i:05d}"
        digest.update((key + "|" + ko + "|" + en + "\n").encode())
        rows.append((
            key, key, "technology", 1, f"synthetic/{i:05d}.txt",
            "{}", "raw_definition", ko, "{}", en, "{}",
            "resolved", None,
        ))
        names.extend(((key, "korean", ko.casefold(), "{}"),
                      (key, "english", en.casefold(), "{}")))
        descriptions.append((key, f"research in alloy fields {i:05d}", "{}"))
    db.executemany("INSERT INTO projection VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)", rows)
    db.executemany("INSERT INTO names VALUES(?,?,?,?)", names)
    db.executemany("INSERT INTO descriptions VALUES(?,?,?)", descriptions)
    db.commit()
    results: dict[str, dict[str, object]] = {}
    workloads = {
        "id_exact": Query(f"demo_{size - 1:05d}", limit=10),
        "name_exact": Query(f"합금 연구 {size - 1:05d}", limit=10),
        "short_korean": Query("합금", limit=10),
        "prefix": Query("합금 연구", limit=10),
        "description_lexical": Query("alloy fields", limit=10),
    }
    for label, query in workloads.items():
        term = query.text.casefold()
        start = time.perf_counter_ns()
        first = SearchService._sql_matches(db, term, query, False)
        cold_ms = (time.perf_counter_ns() - start) / 1e6
        timings = []
        for _ in range(25):
            start = time.perf_counter_ns()
            warm = SearchService._sql_matches(db, term, query, False)
            timings.append((time.perf_counter_ns() - start) / 1e6)
            assert len(warm) == len(first)
        results[label] = {
            "cold_ms": round(cold_ms, 3),
            "warm_ms": [round(t, 3) for t in timings],
            "warm_p95_ms": round(sorted(timings)[23], 3),
            "returned": len(first),
            "limit": query.limit,
        }
    db.close()
    return {
        "synthetic_rows": size, "corpus_sha256": digest.hexdigest(),
        "python": sys.version.split()[0], "sqlite": sqlite3.sqlite_version,
        "os": platform.platform(), "cpu": platform.processor() or os.cpu_count(),
        "benchmark_scope": "in-memory projection SQL only; not end-to-end",
        "query_runs": 26,
        "results": results,
    }


if __name__ == "__main__":
    for count in (100, 1000, 10000):
        print(json.dumps(measure(count), ensure_ascii=False, sort_keys=True))
