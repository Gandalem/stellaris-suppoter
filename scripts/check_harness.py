"""Validate documentation ledgers. Does not run or certify product tests."""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlsplit

STATES = {
    "F": {"planned", "in_progress", "blocked", "verified"},
    "TASK": {"todo", "doing", "blocked", "done"},
    "E": {"not_run", "pass", "fail", "blocked"},
}


def validate(root: Path) -> tuple[list[str], dict[str, int]]:
    root = root.resolve()
    errors: list[str] = []

    def file_ref(value: object, owner: str) -> None:
        if not isinstance(value, str) or not value or "\\" in value:
            errors.append(f"{owner}: invalid relative file reference")
            return
        target = (root / value).resolve()
        if not target.is_relative_to(root) or not target.is_file():
            errors.append(f"{owner}: missing or unsafe file: {value}")

    def load(path: str) -> object:
        try:
            return json.loads((root / path).read_text(encoding="utf-8"))
        except (OSError, UnicodeError, json.JSONDecodeError) as exc:
            errors.append(f"{path}: {exc}")
            return {}

    def rows(path: str, key: str) -> list:
        obj = load(path)
        if not isinstance(obj, dict) or obj.get("schema_version") != 1:
            errors.append(f"{path}: expected schema_version 1 object")
            return []
        value = obj.get(key)
        if not isinstance(value, list) or not value:
            errors.append(f"{path}: expected nonempty {key} array")
            return []
        return value

    def strings(obj: dict, key: str, owner: str, required: bool = False) -> list[str]:
        value = obj.get(key)
        if not isinstance(value, list) or any(not isinstance(x, str) or not x for x in value):
            errors.append(f"{owner}: {key} must be an array of nonempty strings")
            return []
        if required and not value:
            errors.append(f"{owner}: {key} must not be empty")
        if len(value) != len(set(value)):
            errors.append(f"{owner}: duplicate {key}")
        return value

    def index(items: list, prefix: str) -> dict[str, dict]:
        result = {}
        for obj in items:
            if not isinstance(obj, dict):
                errors.append(f"{prefix}: expected object")
                continue
            ident = obj.get("id")
            if not isinstance(ident, str) or not re.fullmatch(rf"{prefix}-\d{{3}}", ident):
                errors.append(f"{prefix}: invalid id")
                continue
            if ident in result:
                errors.append(f"duplicate id: {ident}")
            result[ident] = obj
            if obj.get("status") not in STATES[prefix]:
                errors.append(f"{ident}: invalid status")
            if not isinstance(obj.get("title"), str) or not obj["title"].strip():
                errors.append(f"{ident}: title required")
            evidence = strings(obj, "evidence", ident)
            for ref in evidence:
                file_ref(ref, ident)
            if obj.get("status") in {"done", "verified", "pass"} and not evidence:
                errors.append(f"{ident}: completion requires evidence")
            if obj.get("status") == "blocked" and not obj.get("blocker"):
                errors.append(f"{ident}: blocked requires blocker")
        return result

    features = index(rows("harness/features.json", "features"), "F")
    tasks = index(rows("harness/tasks.json", "tasks"), "TASK")
    cases = []
    try:
        for number, line in enumerate((root / "harness/evals.jsonl").read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                try:
                    cases.append(json.loads(line))
                except json.JSONDecodeError:
                    errors.append(f"evals.jsonl:{number}: invalid JSON")
    except (OSError, UnicodeError) as exc:
        errors.append(f"harness/evals.jsonl: {exc}")
    if not cases:
        errors.append("evals.jsonl: must not be empty")
    evals = index(cases, "E")

    for fid, obj in features.items():
        for ref in strings(obj, "docs", fid, True):
            file_ref(ref, fid)
    for tid, obj in tasks.items():
        for ref in strings(obj, "docs", tid, True):
            file_ref(ref, tid)
        for key, targets in (("feature_ids", features), ("eval_ids", evals), ("depends_on", tasks)):
            for ref in strings(obj, key, tid, key != "depends_on"):
                if ref not in targets:
                    errors.append(f"{tid}: unknown {key} reference {ref}")
        strings(obj, "acceptance", tid, True)
        if obj.get("status") in {"doing", "done"}:
            for dep in obj.get("depends_on", []):
                if isinstance(dep, str) and tasks.get(dep, {}).get("status") != "done":
                    errors.append(f"{tid}: unfinished dependency {dep}")
        if obj.get("status") == "done":
            for eid in obj.get("eval_ids", []):
                if isinstance(eid, str) and evals.get(eid, {}).get("status") != "pass":
                    errors.append(f"{tid}: evaluation not passed {eid}")
    for eid, obj in evals.items():
        for fid in strings(obj, "feature_ids", eid, True):
            if fid not in features:
                errors.append(f"{eid}: unknown feature {fid}")
        strings(obj, "expected", eid, True)
        for key in ("fixture", "input"):
            if not isinstance(obj.get(key), str) or not obj[key].strip():
                errors.append(f"{eid}: {key} required")
        if not any(eid in t.get("eval_ids", []) for t in tasks.values()):
            errors.append(f"{eid}: no linked task")

    visiting: set[str] = set()
    visited: set[str] = set()

    def visit(tid: str) -> None:
        if tid in visiting:
            errors.append(f"dependency cycle: {tid}")
            return
        if tid in visited:
            return
        visiting.add(tid)
        deps = tasks[tid].get("depends_on", [])
        if isinstance(deps, list):
            for dep in deps:
                if isinstance(dep, str) and dep in tasks:
                    visit(dep)
        visiting.remove(tid)
        visited.add(tid)

    for tid in tasks:
        visit(tid)
    for fid, obj in features.items():
        ft = [t for t in tasks.values() if fid in t.get("feature_ids", [])]
        fe = [e for e in evals.values() if fid in e.get("feature_ids", [])]
        if not ft or not fe:
            errors.append(f"{fid}: needs tasks and evaluations")
        if obj.get("status") == "verified" and (any(t.get("status") != "done" for t in ft) or any(e.get("status") != "pass" for e in fe)):
            errors.append(f"{fid}: verified without completed tasks/evaluations")

    state = load("harness/state.json")
    if not isinstance(state, dict) or state.get("schema_version") != 1:
        errors.append("state: expected schema_version 1 object")
        state = {}
    active = state.get("active_task")
    doing = [tid for tid, t in tasks.items() if t.get("status") == "doing"]
    if len(doing) > 1 or doing != ([active] if active is not None else []):
        errors.append("state: active_task must match the single doing task")
    nxt = state.get("next_task")
    if nxt is None:
        actionable = [t for t in tasks.values() if t.get("status") in {"todo", "doing"} and all(tasks.get(d, {}).get("status") == "done" for d in t.get("depends_on", []) if isinstance(d, str))]
        if actionable:
            errors.append("state: next_task missing while actionable tasks exist")
    elif not isinstance(nxt, str) or nxt not in tasks:
        errors.append("state: next_task must name a known task")
    elif tasks[nxt].get("status") not in {"todo", "doing"} or any(tasks.get(d, {}).get("status") != "done" for d in tasks[nxt].get("depends_on", []) if isinstance(d, str)):
        errors.append("state: next_task is not actionable")
    file_ref(state.get("last_session"), "state")

    # Only file targets are checked; external URLs and heading anchors are not fetched.
    markdown = []
    for folder in ("docs", "harness", ".github"):
        markdown.extend((root / folder).rglob("*.md"))
    markdown.extend(root.glob("*.md"))
    for path in markdown:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            errors.append(f"{path.name}: {exc}")
            continue
        for match in re.finditer(r"\[[^\]\n]*\]\(([^)\s]+)(?:\s+[^)]*)?\)", text):
            url = match.group(1).strip("<>")
            parsed = urlsplit(url)
            if parsed.scheme or parsed.netloc or not parsed.path:
                continue
            target = (path.parent / unquote(parsed.path)).resolve()
            if not target.is_relative_to(root) or not target.is_file():
                errors.append(f"{path.relative_to(root)}: broken/unsafe link {url}")
    return errors, {"features": len(features), "tasks": len(tasks), "evaluations": len(evals)}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path(__file__).resolve().parents[1])
    args = parser.parse_args()
    try:
        errors, counts = validate(args.root)
    except (TypeError, ValueError, RecursionError) as exc:
        print(f"ERROR: malformed or excessively deep harness: {exc}", file=sys.stderr)
        return 1
    for error in errors:
        print(f"ERROR: {error}", file=sys.stderr)
    print(json.dumps({"harness_valid": not errors, **counts, "product_tests_executed": False}, sort_keys=True))
    return 1 if errors else 0


if __name__ == "__main__":
    raise SystemExit(main())
