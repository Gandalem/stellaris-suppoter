"""Snapshot-bound one-hop numeric definitions; no evaluation or live-file reads."""

from __future__ import annotations

import hashlib
import json
import re
from collections import OrderedDict
from decimal import Decimal

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.parsing import BlockNode, PairNode, ScalarNode, UnknownNode, parse_bytes
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.identity import storage_json

VERSION = "static-card-values-1"
MAX_PRODUCT = 16 * 1024 * 1024
MAX_CATALOG_BYTES = 32 * 1024 * 1024
MAX_VARIABLES = 100_000
NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")
VARIABLE = re.compile(r"@[A-Za-z_][A-Za-z0-9_.-]*\Z")
HARD = {"LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT", "PARSE_DIAGNOSTIC_LIMIT"}


def supported(path):
    return (path.startswith(("common/technology/", "common/scripted_variables/")) or
            path.lower().endswith(".txt") and path.startswith(("common/component_templates/", "common/component_sets/")))


def numeric(raw, allow_negative=False):
    if not isinstance(raw, str) or len(raw) > 64 or not NUMBER.fullmatch(raw):
        return None
    value = Decimal(raw)
    if not value.is_finite() or (value < 0 and not allow_negative):
        return None
    return format(value.copy_abs() if value.is_zero() else value, ",f")


def scan(data, parsed=None):
    try:
        data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise SnapshotError("SOURCE_CHANGED", "Variable source encoding is invalid.") from exc
    parsed = parsed or parse_bytes(data)
    if any(d.code in HARD for d in parsed.diagnostics):
        raise SnapshotError("LIMIT_EXCEEDED", "Variable source parser budget exhausted.")

    def known(nodes):
        for node in nodes:
            if isinstance(node, UnknownNode):
                return False
            if isinstance(node, PairNode) and isinstance(node.value, BlockNode):
                if not node.value.closed or not known(node.value.items):
                    return False
        return True

    variables = []
    for node in parsed.document.items:
        if (
            isinstance(node, PairNode)
            and node.key_kind == "variable"
            and VARIABLE.fullmatch(node.key_text)
        ):
            span = node.span
            value = node.value
            raw = None
            if isinstance(value, ScalarNode) and value.span.byte_end - value.span.byte_start <= 512:
                raw = value.raw_bytes(data).decode("utf-8")
            variables.append(
                {
                    "name": node.key_text,
                    "raw": raw,
                    "span": [span.byte_start, span.byte_end, span.line_start, span.line_end],
                    "value": None
                    if value is None
                    else [
                        value.span.byte_start,
                        value.span.byte_end,
                        value.span.line_start,
                        value.span.line_end,
                    ],
                    "assign": node.operator_text == "=",
                }
            )
    return {
        "version": VERSION,
        "complete": parsed.ok and known(parsed.document.items),
        "variables": variables,
    }


class StaticProducts:
    def __init__(self, repo):
        self.repo = repo
        self.items = []
        self.pending = {}
        self.incomplete = False

    def ingest(self, source, parsed=None, force=False):
        d = source.descriptor()
        key = (
            VERSION
            + ":file:"
            + hashlib.sha256(storage_json([*d.key, d.file_sha256], max_bytes=8192)).hexdigest()
        )
        product = None
        if not force:
            with self.repo._connection(read_only=True) as conn:
                row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row:
                try:
                    meta = json.loads(row[0])
                    if type(meta["size"]) is not int or not 0 < meta["size"] <= MAX_PRODUCT:
                        raise ValueError("Invalid variable product size")
                    product = json.loads(self.repo.cache.read(meta["sha"], meta["size"]))
                    if product.get("version") != VERSION:
                        product = None
                except (SnapshotError, ValueError, KeyError, TypeError):
                    product = None
        reused = product is not None
        if parsed is not None:
            # A fresh technology AST is shared by both extractors.
            product = scan(source.data, parsed)
            reused = False
        elif product is None:
            product = scan(source.data)
        if len(product["variables"]) > MAX_VARIABLES:
            raise SnapshotError("LIMIT_EXCEEDED", "Variable definition budget exceeded.")
        encoded = storage_json(product, max_bytes=MAX_PRODUCT, max_items=500_000)
        sha = hashlib.sha256(encoded).hexdigest()
        self.repo.cache.put(encoded, sha)
        self.pending[key] = json.dumps({"sha": sha, "size": len(encoded)})
        self.items.append(
            {
                "key": list(d.key),
                "sha": d.file_sha256,
                "size": d.size,
                "product_sha": sha,
                "product_size": len(encoded),
            }
        )
        self.incomplete |= not product["complete"]
        return reused

    def publish(self, conn, sid):
        conn.executemany("INSERT OR REPLACE INTO settings VALUES(?,?)", self.pending.items())
        value = storage_json(
            {"version": VERSION, "files": self.items}, max_bytes=1024 * 1024
        ).decode()
        old = conn.execute(
            "SELECT value FROM settings WHERE key=?", (VERSION + ":" + sid,)
        ).fetchone()
        if old and old[0] != value:
            raise SnapshotError("SOURCE_CHANGED", "Immutable variable manifest differs.")
        conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (VERSION + ":" + sid, value))


class StaticCatalog:
    def __init__(self, repo, sid):
        self.repo, self.sid = repo, sid
        self.sources = {s.key: s for s in repo.source_manifest(sid) if supported(s.relative_path)}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.lookups = set()
        with repo._connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (VERSION + ":" + sid,)
            ).fetchone()
        with repo._connection(read_only=True) as conn:
            policy = conn.execute(
                "SELECT policy_json FROM snapshots WHERE snapshot_id=?", (sid,)
            ).fetchone()
        if (
            row is None
            and policy
            and json.loads(policy[0]).get("analysis_context", {}).get("card_values") == VERSION
        ):
            raise SnapshotError("CACHE_MISSING", "Snapshot variable manifest is absent.")
        self.legacy = row is None
        self.files = {}
        if row:
            if len(row[0].encode()) > 1024 * 1024:
                raise SnapshotError("LIMIT_EXCEEDED", "Variable manifest is too large.")
            manifest = json.loads(row[0])
            if manifest["version"] != VERSION:
                raise SnapshotError("SOURCE_CHANGED", "Variable manifest policy differs.")
            for item in manifest["files"]:
                key = tuple(item["key"])
                d = self.sources.get(key)
                if (
                    key in self.files
                    or d is None
                    or (item["sha"], item["size"]) != (d.file_sha256, d.size)
                ):
                    raise SnapshotError("SOURCE_CHANGED", "Variable manifest source differs.")
                if (
                    type(item["product_size"]) is not int
                    or not 0 < item["product_size"] <= MAX_PRODUCT
                ):
                    raise SnapshotError("LIMIT_EXCEEDED", "Variable product size is invalid.")
                self.files[key] = item
            if set(self.files) != set(self.sources):
                raise SnapshotError("SOURCE_CHANGED", "Variable manifest membership differs.")
        self.globals = {}
        self.global_complete = not self.legacy
        count = size = 0
        for key in self.files:
            if key[2].startswith("common/scripted_variables/"):
                product = self.load(key)
                size += self.files[key]["product_size"]
                count += len(product["variables"])
                if size > MAX_CATALOG_BYTES or count > MAX_VARIABLES:
                    raise SnapshotError(
                        "LIMIT_EXCEEDED", "Global variable catalog budget exceeded."
                    )
                self.global_complete &= product["complete"]
                for item in product["variables"]:
                    self.globals.setdefault(item["name"], []).append((key, item))

    def load(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key][0]
        d = self.sources[key]
        raw = self.repo.cache.read(d.file_sha256, d.size)
        meta = self.files.get(key)
        product = scan(raw)
        if meta:
            cached = self.repo.cache.read(meta["product_sha"], meta["product_size"])
            if json.loads(cached) != product:
                raise SnapshotError("SOURCE_CHANGED", "Variable product differs from original AST.")
        size = len(storage_json(product, max_bytes=MAX_PRODUCT, max_items=500_000))
        self.cache[key] = (product, size)
        self.cache_bytes += size
        while self.cache_bytes > MAX_CATALOG_BYTES and len(self.cache) > 1:
            _, (_, old_size) = self.cache.popitem(last=False)
            self.cache_bytes -= old_size
        return product

    def ref(self, key, span):
        d = self.sources[key]
        return SourceRef(self.sid, *key, d.file_sha256, *span).to_dict()

    def cost(self, fact, definition, allow_negative=False):
        raw = fact.get("raw_expression")
        source = fact.get("value_source_ref")
        result = {
            "value": None,
            "status": "unresolved",
            "raw": raw,
            "sources": [source] if source else [],
            "dependencies": [],
        }
        if fact.get("operator") != "=" or raw is None:
            return result
        value = numeric(raw, allow_negative)
        if value is not None:
            return {**result, "value": value, "status": "resolved"}
        if not VARIABLE.fullmatch(raw):
            return {
                **result,
                "status": "unsupported",
                "reason": "숫자 또는 한 단계 변수 참조 범위 밖입니다.",
            }
        key = (definition["source_kind"], definition["source_id"], definition["relative_path"])
        result["dependencies"] = [["local", *key, raw], ["global", raw]]
        self.lookups.add((key, raw))
        if self.legacy:
            return {
                **result,
                "status": "missing_data",
                "reason": "이 데이터에는 변수 정의 범위가 저장되지 않았습니다.",
            }
        local = self.load(key)
        local_candidates = [(key, item) for item in local["variables"] if item["name"] == raw]
        candidates = local_candidates + self.globals.get(raw, [])
        if not self.global_complete or not local["complete"]:
            return {
                **result,
                "status": "incomplete",
                "reason": "변수 범위를 완전히 읽지 못해 단일 정의로 확정할 수 없습니다.",
            }
        if len(candidates) != 1:
            return {
                **result,
                "status": "ambiguous" if candidates else "unresolved",
                "reason": "변수 후보가 여러 개입니다." if candidates else "변수 정의가 없습니다.",
                "candidate_count": len(candidates),
                "sources": result["sources"]
                + [self.ref(k, item["span"]) for k, item in candidates[:32]],
            }
        candidate_key, item = candidates[0]
        if candidate_key == key and item["span"][1] > definition["byte_start"]:
            return {
                **result,
                "status": "unsupported",
                "reason": "로컬 변수가 기술 정의보다 뒤에 선언됐습니다.",
                "sources": result["sources"] + [self.ref(candidate_key, item["span"])],
            }
        refs = [self.ref(candidate_key, item["span"])]
        if item["value"]:
            refs.append(self.ref(candidate_key, item["value"]))
        result["sources"] += refs
        value = numeric(item["raw"], allow_negative) if item["assign"] else None
        return {
            **result,
            "value": value,
            "status": "resolved" if value is not None else "unsupported",
        }
