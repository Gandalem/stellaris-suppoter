"""Non-gating synthetic SQLite read-preflight cost probe (TASK-010 R5).

Print observed timings; never enforce a p95 threshold from noisy CI runners.
No real game paths/files are accessed. The same temporary database grows from
0 to 1,000 to 5,000 provenance diagnostics to compare schema checking costs.
"""

from __future__ import annotations

import json
import sqlite3
import sys
from collections.abc import Callable
from contextlib import closing
from pathlib import Path
from statistics import median
from tempfile import TemporaryDirectory
from time import perf_counter_ns

from stellaris_supporter.storage import SnapshotPolicy, SnapshotRepository
from stellaris_supporter.storage.schema import check_schema, connect


def _median_ms(action: Callable[[], object], *, repetitions: int = 7) -> float:
    action()  # warm execution, excluded from the measured samples
    timings: list[float] = []
    for _ in range(repetitions):
        start = perf_counter_ns()
        action()
        timings.append((perf_counter_ns() - start) / 1_000_000)
    return round(median(timings), 4)


def main() -> None:
    with TemporaryDirectory(prefix="synthetic-snapshot-metrics-") as temporary:
        repo = SnapshotRepository(Path(temporary) / "data")
        snapshot = repo.stage(
            (), SnapshotPolicy("parser-1", "adapter-1", "a" * 64)
        ).snapshot_id
        repo.activate(snapshot)
        with closing(connect(repo.db_path)) as conn:
            earlier = 0
            for count in (0, 1000, 5000):
                if count > earlier:
                    conn.execute("BEGIN IMMEDIATE")
                    try:
                        conn.executemany(
                            "INSERT INTO diagnostics(snapshot_id,ordinal,code,severity,"
                            "message,source_ref_json) VALUES(?,?,?,?,?,?)",
                            (
                                (snapshot, index, "SYNTHETIC_BENCH", "info",
                                 "short synthetic record", None)
                                for index in range(earlier, count)
                            ),
                        )
                        conn.execute("COMMIT")
                    except BaseException:
                        if conn.in_transaction:
                            conn.execute("ROLLBACK")
                        raise
                earlier = count
                page_count = conn.execute("PRAGMA page_count").fetchone()[0]
                page_size = conn.execute("PRAGMA page_size").fetchone()[0]
                measurements = {
                    "kind": "synthetic-sqlite-preflight-non-gating",
                    "python": sys.version.split()[0],
                    "sqlite": sqlite3.sqlite_version,
                    "rows": count,
                    "db_pages": page_count,
                    "db_bytes": page_count * page_size,
                    "full_schema_check_median_ms": _median_ms(
                        lambda: check_schema(conn, full_integrity=True)
                    ),
                    "read_schema_check_median_ms": _median_ms(
                        lambda: check_schema(conn, full_integrity=False)
                    ),
                    "repository_empty_query_median_ms": _median_ms(repo.entities),
                }
                print(json.dumps(measurements, sort_keys=True))


if __name__ == "__main__":
    main()
