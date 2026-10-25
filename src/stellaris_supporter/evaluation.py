"""Reproducible authored retrieval gold, 10k service benchmark and opt-in suite runner.

Results never rewrite the ledger. Manual/platform evals stay pending.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import platform
import sqlite3
import subprocess
import sys
import tempfile
import time
import unicodedata
from collections import Counter
from pathlib import Path

from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.config import Limits, Settings
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import SnapshotRepository

VERSION = "desktop-gold-1"


def create_corpus(root, count=64):
    paths = {}
    for start in range(0, count, 100):
        paths[f"common/technology/demo_{start:05}.txt"] = "\n".join(
            f"demo_{i:05} = {{ cost = {100+i} tier = 1 area = physics }}" for i in range(start, min(start+100, count))).encode()
    # Distinct definitions of the same ID: never arbitrarily collapse them.
    paths["common/technology/duplicate.txt"] = b"demo_00000 = { cost = 999 }"
    ko = ["l_korean:"]
    en = ["l_english:"]
    for i in range(count):
        ko.append(f' demo_{i:05}:0 "우주 항법 {i:05}"')
        en.append(f' demo_{i:05}:0 "Space Navigation {i:05}"')
    paths["localisation/korean/demo_l_korean.yml"] = ("\n".join(ko)+"\n").encode("utf-8-sig")
    paths["localisation/english/demo_l_english.yml"] = ("\n".join(en)+"\n").encode("utf-8-sig")
    digest = hashlib.sha256()
    for name, raw in sorted(paths.items()):
        target = root / name
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(raw)
        digest.update(name.encode()+b"\0"+raw+b"\0")
    return digest.hexdigest()


def gold_cases():
    cases = []
    for i in range(8):
        ident = f"demo_{i:05}"
        for group, text, language, expected in (
            ("id", ident, "korean", [ident]),
            ("korean", f"우주 항법 {i:05}", "korean", [ident]),
            ("english", f"Space Navigation {i:05}", "english", [ident]),
            ("normalization", unicodedata.normalize("NFD", f"  우주   항법 {i:05}  "), "korean", [ident]),
            ("missing", f"absent_{i:05}", "korean", []),
            ("short", "우주" if i % 2 == 0 else "항법", "korean", [f"demo_{j:05}" for j in range(64)]),
        ):
            cases.append({"group": group, "text": text, "language": language, "expected": expected,
                          "duplicates": 2 if group == "id" and i == 0 else None})
    # Independent collision/normalization obligations, in addition to 48 balanced questions.
    cases.extend([
        {"group": "collision", "text": "demo_00000", "language": "english", "expected": ["demo_00000"], "duplicates": 2},
        {"group": "collision", "text": "우주 항법 00000", "language": "korean", "expected": ["demo_00000"], "duplicates": 2},
        {"group": "normalization", "text": "  SPACE   NAVIGATION 00003 ", "language": "english", "expected": ["demo_00003"], "duplicates": None},
    ])
    return cases


def retrieval_gold(repo):
    service = SearchService(repo)
    records = []
    try:
        for case in gold_cases():
            result = service.search(Query(case["text"], language=case["language"]))
            ids = [hit.game_id for hit in result.results[:5]]
            expected = case["expected"]
            correct = (bool(set(ids) & set(expected)) if expected else not result.results)
            exact = not expected or bool(ids) and ids[0] in expected
            duplicates = case["duplicates"]
            if duplicates is not None:
                correct = correct and sum(h.game_id == expected[0] for h in result.results) == duplicates
            records.append({**case, "actual_top5": ids, "status": result.status,
                            "passed": correct and result.status not in {"error", "unsupported"}, "exact": exact})
    finally:
        service.close()
    answerable = [r for r in records if r["expected"]]
    missing = [r for r in records if not r["expected"]]
    exacts = [r for r in answerable if r["group"] != "short"]
    return {"version": VERSION, "case_hash": hashlib.sha256(json.dumps(gold_cases(), sort_keys=True, ensure_ascii=False).encode()).hexdigest(),
            "groups": dict(Counter(r["group"] for r in records)), "count": len(records),
            "recall_at_5": sum(r["passed"] for r in answerable)/len(answerable),
            "exact_first": sum(r["exact"] for r in exacts)/len(exacts),
            "correct_abstention": sum(r["passed"] for r in missing)/len(missing),
            "passed": all(r["passed"] for r in records), "records": records}


def p95(values):
    return sorted(values)[max(0, math.ceil(len(values)*.95)-1)]


def memory_info():
    if sys.platform != "win32":
        try:
            import resource
            return {"peak_working_set_bytes": resource.getrusage(resource.RUSAGE_SELF).ru_maxrss * (1 if sys.platform == "darwin" else 1024)}
        except ImportError:
            return {"peak_working_set_bytes": None}
    import ctypes
    from ctypes import wintypes as w
    class Memory(ctypes.Structure):
        _fields_ = [("cb", w.DWORD), ("faults", w.DWORD)] + [(name, ctypes.c_size_t) for name in
                    ("peak", "working", "pool_peak", "pool", "nonpool_peak", "nonpool", "page", "page_peak")]
    class Host(ctypes.Structure):
        _fields_ = [("length", w.DWORD), ("load", w.DWORD)] + [(name, ctypes.c_ulonglong) for name in
                    ("total", "available", "page_total", "page_available", "virtual_total", "virtual_available", "extended")]
    kernel = ctypes.WinDLL("kernel32")
    psapi = ctypes.WinDLL("psapi")
    kernel.GetCurrentProcess.restype = w.HANDLE
    psapi.GetProcessMemoryInfo.argtypes = [w.HANDLE, ctypes.c_void_p, w.DWORD]
    data = Memory()
    data.cb = ctypes.sizeof(data)
    host = Host()
    host.length = ctypes.sizeof(host)
    kernel.GlobalMemoryStatusEx(ctypes.byref(host))
    ok = psapi.GetProcessMemoryInfo(kernel.GetCurrentProcess(), ctypes.byref(data), data.cb)
    return {"peak_working_set_bytes": data.peak if ok else None, "host_ram_bytes": host.total or None}


def benchmark(repo):
    cold, warm = [], []
    for i in range(5):
        service = SearchService(repo)
        try:
            start = time.perf_counter_ns()
            result = service.search(Query(f"demo_{i:05}"))
            cold.append((time.perf_counter_ns()-start)/1e6)
            if not result.results:
                raise RuntimeError("Cold benchmark query failed")
        finally:
            service.close()
    service = SearchService(repo)
    try:
        service.search(Query("demo_00001"))
        for i in range(30):
            start = time.perf_counter_ns()
            result = service.search(Query(f"demo_{i:05}"))
            warm.append((time.perf_counter_ns()-start)/1e6)
            if not result.results:
                raise RuntimeError("Warm benchmark query failed")
    finally:
        service.close()
    return {"cold_definition": "new SearchService/projection; OS filesystem cache not purged", "cold_ms": cold,
            "warm_ms": warm, "cold_p95_ms": p95(cold), "warm_p95_ms": p95(warm),
            "memory": memory_info(), "warm_target_ms": 500, "warm_target_met": p95(warm) <= 500}


SUITES = {
    "E-002": "test_synthetic_corpus.py", "E-003": "test_config.py", "E-004": "test_doctor.py",
    "E-005": "test_inventory.py", "E-006": "test_inventory.py", "E-007": "test_versioning.py", "E-008": "test_versioning.py",
    "E-009": "test_lexer.py", "E-010": "test_lexer.py", "E-011": "test_parser.py", "E-012": "test_parser.py", "E-013": "test_parser.py",
    "E-014": "test_technology_adapter.py", "E-015": "test_localisation.py", "E-016": "test_localisation.py", "E-017": "test_localisation_review_regressions.py",
    "E-018": "test_storage_snapshots.py", "E-019": "test_storage_snapshots.py",
    "E-020": "test_retrieval.py", "E-021": "test_retrieval.py", "E-022": "test_retrieval.py",
    "E-023": "test_answers.py", "E-024": "test_answers.py", "E-025": "test_answers.py", "E-026": "test_cli_vertical.py",
    "E-027": "test_domain_e027_matrix.py", "E-028": "test_references.py", "E-029": "test_references_cli.py",
    "E-030": "test_incremental_diff.py", "E-031": "test_incremental_diff.py",
    "E-032": "test_desktop.py", "E-033": "test_desktop.py",
}


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--benchmark", action="store_true")
    parser.add_argument("--suite", action="store_true", help="Execute mapped authored v0.1 tests; never certify manual platform cases")
    parser.add_argument("--work-dir", type=Path)
    args = parser.parse_args(argv)
    started = time.time()
    results = {"schema_version": 1, "version": VERSION, "environment": {
        "os": platform.platform(), "python": platform.python_version(), "sqlite": sqlite3.sqlite_version,
        "cpu": platform.processor(), "logical_cpu_count": __import__("os").cpu_count()},
        "evaluations": {f"E-{i:03}": "not_run" for i in range(1, 37)}}
    with tempfile.TemporaryDirectory(prefix="evaluation-", dir=args.work_dir) as folder:
        base = Path(folder)
        count = 10000 if args.benchmark else 64
        results["corpus_hash"] = create_corpus(base / "game", count)
        settings = Settings(base / "config.toml", base / "game", base / "private", "korean", False, Limits())
        repo = SnapshotRepository(settings.data_dir, game_root=settings.game_root)
        start = time.perf_counter()
        index_technologies(repo, settings)
        results["index_seconds"] = time.perf_counter()-start
        results["entity_count"] = count+1
        # Gold expectations are fixed to 64 roots; a separate corpus avoids changing short-query gold.
        if args.benchmark:
            results["benchmark"] = benchmark(repo)
            results["evaluations"]["E-035"] = "pass"
            gold_root = base / "gold-game"
            results["gold_corpus_hash"] = create_corpus(gold_root, 64)
            settings = Settings(base / "gold.toml", gold_root, base / "gold-private", "korean", False, Limits())
            repo = SnapshotRepository(settings.data_dir, game_root=gold_root)
            index_technologies(repo, settings)
        results["retrieval"] = retrieval_gold(repo)
        results["evaluations"]["E-034"] = "pass" if results["retrieval"]["passed"] else "fail"
    if args.suite:
        root = Path(__file__).resolve().parents[2]
        files = sorted({"tests/"+name for name in SUITES.values()})
        # pytest exit 0 alone can include skips: retain skipped counts and avoid platform certifications.
        with tempfile.TemporaryDirectory(prefix="suite-", dir=args.work_dir) as suite_dir:
            proc = subprocess.run([sys.executable, "-m", "pytest", "-q", "--basetemp", str(Path(suite_dir)/"pytest"), *files], cwd=root, capture_output=True, text=True)
        results["suite"] = {"files": files, "exit_code": proc.returncode, "summary": proc.stdout.splitlines()[-1:]}
        for ident in SUITES:
            results["evaluations"][ident] = ("not_run" if "skipped" in proc.stdout else "pass") if proc.returncode == 0 else "fail"
    results["seconds"] = time.time()-started
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(results, ensure_ascii=False, indent=2)+"\n", encoding="utf-8")
    return 0 if results["retrieval"]["passed"] and (not args.suite or results["suite"]["exit_code"] == 0) else 1


if __name__ == "__main__":
    raise SystemExit(main())
