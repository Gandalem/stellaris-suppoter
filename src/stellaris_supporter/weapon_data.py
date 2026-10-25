"""Bounded, lossless weapon file products and immutable snapshot publication."""

from __future__ import annotations

import csv
import hashlib
import io
import json
import re
from bisect import bisect_right
from collections import Counter, OrderedDict

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.parsing import BlockNode, PairNode, ScalarNode, UnknownNode, parse_bytes
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.identity import storage_json

VERSION = "weapon-data-2"
KIND = "component_template"
TABLES = {
    "common/component_templates/weapon_components.csv": "standard",
    "common/component_templates/mutation_weapon_components.csv": "mutation",
}
MAX_PRODUCT = 16 * 1024 * 1024
MAX_CONTEXT = 64 * 1024 * 1024
ID = re.compile(r"[A-Za-z_][A-Za-z0-9_.-]{0,511}\Z")
HARD = {"LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT", "PARSE_DIAGNOSTIC_LIMIT"}


def supported(path):
    return path in TABLES or (
        path.lower().endswith(".txt")
        and path.startswith(("common/component_templates/", "common/component_sets/"))
    )


def span(node):
    s = node.span
    return [s.byte_start, s.byte_end, s.line_start, s.line_end]


def literal(field):
    if not field or field.get("op") != "=" or field.get("kind") != "scalar":
        return None
    raw = field.get("raw")
    if raw is None:
        return None
    if field.get("token") == "string":
        try:
            value = json.loads(raw)
            return value if isinstance(value, str) else None
        except ValueError:
            return None
    return raw


def fields(node, key):
    return [v for v in node.get("items", ()) if v.get("key") == key]


def single(node, key):
    values = fields(node, key)
    return values[0] if len(values) == 1 and values[0].get("op") == "=" else None


def references(node, key):
    values = fields(node, key)
    if not values:
        return [], bool(node.get("complete"))
    result = []
    complete = len(values) == 1 and bool(node.get("complete"))
    for value in values:
        if value.get("op") != "=" or value.get("kind") != "block" or not value.get("closed"):
            complete = False
            continue
        for child in value.get("items", ()):
            name = literal({**child, "op": "="}) if "key" not in child else None
            if name and ID.fullmatch(name):
                result.append((name, child["span"]))
            else:
                complete = False
    return result, complete


def script_product(data, parsed=None):
    try:
        data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise SnapshotError("SOURCE_CHANGED", "Weapon source encoding is invalid.") from exc
    parsed = parsed or parse_bytes(data)
    if any(d.code in HARD for d in parsed.diagnostics):
        raise SnapshotError("LIMIT_EXCEEDED", "Weapon parser budget exceeded.")
    budget = [0]

    def convert(node):
        budget[0] += 256
        if budget[0] > MAX_PRODUCT:
            raise SnapshotError("LIMIT_EXCEEDED", "Weapon product budget exceeded.")
        out = {"span": span(node)}
        if isinstance(node, PairNode):
            out.update(key=node.key_text, op=node.operator_text)
            value = node.value
            out["value_span"] = span(value) if value else None
        else:
            value = node
        if isinstance(value, ScalarNode):
            raw = value.raw_bytes(data)
            out.update(
                kind="scalar", token=value.token_kind, raw=raw.decode() if len(raw) <= 512 else None
            )
            budget[0] += min(len(raw), 512)
        elif isinstance(value, BlockNode):
            out.update(kind="block", closed=value.closed, items=[convert(v) for v in value.items])
        else:
            out.update(kind="unknown", raw=None)
        return out

    roots = []
    unknown_root = False
    for node in parsed.document.items:
        if isinstance(node, PairNode) and node.key_text in {
            "weapon_component_template",
            "component_set",
        }:
            value = convert(node)
            key_field = single(value, "key")
            game_id = literal(key_field)
            valid = (
                node.operator_text == "="
                and isinstance(node.value, BlockNode)
                and node.value.closed
                and game_id is not None
                and ID.fullmatch(game_id)
            )
            if not valid:
                unknown_root = True
                continue

            def known(n):
                return (
                    n.get("kind") != "unknown"
                    and (n.get("closed", True))
                    and all(known(c) for c in n.get("items", ()))
                )

            value.update(
                id=game_id,
                root=node.key_text,
                complete=known(value),
                diagnostics=[
                    d.code
                    for d in parsed.diagnostics
                    if node.span.byte_start <= d.span.byte_start < node.span.byte_end
                ][:16],
            )
            # An unexpanded injection can supply additional fields or requirements.
            if any(c.get("key") == "inline_script" for c in value.get("items", ())):
                value["complete"] = False
            roots.append(value)
        elif (
            isinstance(node, UnknownNode)
            or isinstance(node, PairNode)
            and node.key_text == "inline_script"
        ):
            unknown_root = True
    return {
        "version": VERSION,
        "format": "script",
        "roots": roots,
        "complete": parsed.ok and not unknown_root,
    }


def csv_product(data):
    try:
        data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise SnapshotError("SOURCE_CHANGED", "Weapon table encoding is invalid.") from exc
    line_starts = [0] + [m.end() for m in re.finditer(b"\n", data)]

    def position(start, end):
        return [
            start,
            end,
            bisect_right(line_starts, start),
            bisect_right(line_starts, max(start, end - 1)),
        ]

    rows = []
    header = None
    complete = True
    i = 3 if data.startswith(b"\xef\xbb\xbf") else 0
    total = 0
    while i < len(data):
        if data[i : i + 1] == b"#":
            end = data.find(b"\n", i)
            i = len(data) if end < 0 else end + 1
            continue
        start = cell_start = i
        cells = []
        quoted = False
        while i < len(data):
            byte = data[i]
            if byte == 34:
                if quoted and data[i : i + 2] == b'""':
                    i += 2
                    continue
                quoted = not quoted
            if not quoted and byte in (59, 10, 13):
                cells.append(position(cell_start, i))
                if len(cells) > 128:
                    raise SnapshotError("LIMIT_EXCEEDED", "Weapon CSV column budget exceeded.")
                if byte != 59:
                    break
                cell_start = i + 1
            if i - cell_start > 64 * 1024:
                raise SnapshotError("LIMIT_EXCEEDED", "Weapon CSV cell budget exceeded.")
            i += 1
        if i >= len(data):
            cells.append(position(cell_start, i))
        end = i
        if data[i : i + 2] == b"\r\n":
            i += 2
        elif i < len(data):
            i += 1
        if not data[start:end].strip():
            continue
        total += 1
        if total > 100001:
            raise SnapshotError("LIMIT_EXCEEDED", "Weapon CSV row budget exceeded.")
        try:
            values = next(
                csv.reader(io.StringIO(data[start:end].decode()), delimiter=";", strict=True)
            )
        except (csv.Error, StopIteration):
            complete = False
            continue
        if not any(value.strip() for value in values):
            continue
        if quoted or len(values) != len(cells):
            complete = False
            continue
        if header is None:
            header = {"values": values, "cells": cells, "span": position(start, end)}
            if len(set(values)) != len(values) or not values or values[0] != "key":
                complete = False
        else:
            if len(values) != len(header["values"]) or not ID.fullmatch(values[0]):
                complete = False
                continue
            # Reserve before retaining a potentially expanded cell/span product.
            if (
                sum(len(v.encode()) for v in values)
                + len(cells) * 64
                + sum(r["bytes"] for r in rows[-1:])
                > MAX_PRODUCT
            ):
                raise SnapshotError("LIMIT_EXCEEDED", "Weapon CSV product budget exceeded.")
            cost = sum(len(v.encode()) for v in values) + len(cells) * 64
            accumulated = cost + (rows[-1]["bytes"] if rows else 0)
            if accumulated > MAX_PRODUCT:
                raise SnapshotError("LIMIT_EXCEEDED", "Weapon CSV product budget exceeded.")
            rows.append(
                {
                    "id": values[0],
                    "values": values,
                    "cells": cells,
                    "span": position(start, end),
                    "bytes": accumulated,
                }
            )
    return {
        "version": VERSION,
        "format": "csv",
        "header": header,
        "rows": rows,
        "complete": complete and header is not None,
    }


def product(data, path, parsed=None):
    return csv_product(data) if path in TABLES else script_product(data, parsed)


class WeaponProducts:
    def __init__(self, repo):
        self.repo = repo
        self.files = []
        self.pending = {}
        self.products = []
        self.incomplete = False

    def ingest(self, source, force=False):
        d = source.descriptor()
        key = (
            VERSION
            + ":file:"
            + hashlib.sha256(storage_json([*d.key, d.file_sha256], max_bytes=8192)).hexdigest()
        )
        value = None
        if not force:
            with self.repo._connection(read_only=True) as conn:
                row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
            if row:
                try:
                    meta = json.loads(row[0])
                    if not 0 < meta["size"] <= MAX_PRODUCT:
                        raise ValueError("Invalid product budget")
                    value = json.loads(self.repo.cache.read(meta["sha"], meta["size"]))
                    if value["version"] != VERSION:
                        value = None
                except (ValueError, KeyError, TypeError):
                    value = None
        reused = value is not None
        parsed = None
        if value is None:
            parsed = None if d.relative_path in TABLES else parse_bytes(source.data)
            value = product(source.data, d.relative_path, parsed)
        raw = storage_json(value, max_bytes=MAX_PRODUCT, max_items=500000)
        sha = hashlib.sha256(raw).hexdigest()
        self.repo.cache.put(raw, sha)
        self.pending[key] = json.dumps({"sha": sha, "size": len(raw)})
        self.files.append(
            {
                "key": list(d.key),
                "sha": d.file_sha256,
                "size": d.size,
                "product_sha": sha,
                "product_size": len(raw),
            }
        )
        if sum(f["product_size"] for f in self.files) > MAX_CONTEXT:
            raise SnapshotError("LIMIT_EXCEEDED", "Weapon catalog product budget exceeded.")
        self.products.append(value)
        self.incomplete |= not value["complete"]
        return reused, parsed

    def publish(self, conn, sid):
        value = storage_json(
            {"version": VERSION, "files": self.files}, max_bytes=1024 * 1024
        ).decode()
        old = conn.execute(
            "SELECT value FROM settings WHERE key=?", (VERSION + ":" + sid,)
        ).fetchone()
        if old and old[0] != value:
            raise SnapshotError("SOURCE_CHANGED", "Weapon snapshot manifest changed.")
        conn.executemany("INSERT OR REPLACE INTO settings VALUES(?,?)", self.pending.items())
        conn.execute("INSERT OR REPLACE INTO settings VALUES(?,?)", (VERSION + ":" + sid, value))
        counts = Counter()
        entries = []
        for meta, contents in zip(self.files, self.products, strict=True):
            for index, node in enumerate(contents.get("roots", ())):
                if node["root"] != "weapon_component_template":
                    continue
                counts[node["id"]] += 1
                ref = SourceRef(sid, *meta["key"], meta["sha"], *node["span"]).to_dict()
                identity = {
                    "kind": KIND,
                    "game_id": node["id"],
                    "source": ref,
                    "occurrence": counts[node["id"]],
                }
                entity = hashlib.sha256(storage_json(identity, max_bytes=1024 * 1024)).hexdigest()
                payload = {
                    "version": VERSION,
                    "file_key": meta["key"],
                    "root_index": index,
                    "source_ref": ref,
                    "subtype": "weapon",
                }
                entries.append((entity, node, payload, counts[node["id"]]))
        by_id = {}
        for entity, node, _, _ in entries:
            by_id.setdefault(node["id"], []).append(entity)
        for entity, node, payload, occurrence in entries:
            ref = payload["source_ref"]
            values = (
                sid,
                entity,
                node["id"],
                KIND,
                occurrence,
                ref["source_kind"],
                ref["source_id"],
                ref["relative_path"],
                ref["byte_start"],
                ref["byte_end"],
                "raw_definition" if node["complete"] else "partial",
                storage_json(payload, max_bytes=1024 * 1024).decode(),
            )
            old = conn.execute(
                "SELECT candidate_json FROM entities WHERE snapshot_id=? AND entity_key=?",
                (sid, entity),
            ).fetchone()
            if old and json.loads(old[0]) != payload:
                raise SnapshotError("SOURCE_CHANGED", "Weapon entity changed.")
            conn.execute(
                "INSERT OR IGNORE INTO entities(snapshot_id,entity_key,game_id,kind,occurrence,source_kind,source_id,relative_path,byte_start,byte_end,resolution,candidate_json,localisation_json) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,NULL)",
                values,
            )
        for entity, node, payload, occurrence in entries:
            ref = payload["source_ref"]
            requirements, _ = references(node, "prerequisites")
            if len(requirements) > 1000:
                raise SnapshotError("LIMIT_EXCEEDED", "Weapon relation budget exceeded.")
            upgrade = single(node, "upgrades_to")
            links = [
                (game_id, "weapon_requires_technology", token) for game_id, token in requirements
            ]
            if literal(upgrade) and ID.fullmatch(literal(upgrade)):
                links.append((literal(upgrade), "weapon_upgrade", upgrade["value_span"]))
            for ordinal, (target, relation, token) in enumerate(links, 1):
                if relation == "weapon_requires_technology":
                    targets = [
                        r[0]
                        for r in conn.execute(
                            "SELECT entity_key FROM entities WHERE snapshot_id=? AND kind='technology' AND game_id=? LIMIT 2",
                            (sid, target),
                        )
                    ]
                else:
                    targets = by_id.get(target, [])
                status = (
                    "resolved" if len(targets) == 1 else "ambiguous" if targets else "unresolved"
                )
                proof = {
                    **ref,
                    **dict(
                        zip(
                            ("byte_start", "byte_end", "line_start", "line_end"), token, strict=True
                        )
                    ),
                }
                row = (
                    sid,
                    entity,
                    ordinal,
                    relation,
                    target,
                    targets[0] if len(targets) == 1 else None,
                    status,
                    json.dumps(proof),
                    None,
                )
                saved = conn.execute(
                    "SELECT * FROM relations WHERE snapshot_id=? AND from_entity_key=? AND occurrence=?",
                    (sid, entity, ordinal),
                ).fetchone()
                if saved and tuple(saved) != row:
                    raise SnapshotError("SOURCE_CHANGED", "Weapon relation changed.")
                conn.execute("INSERT OR IGNORE INTO relations VALUES(?,?,?,?,?,?,?,?,?)", row)


class WeaponContext:
    def __init__(self, repo, sid, cancel=None):
        self.repo, self.sid = repo, sid
        repo.answer_snapshot_context(sid)
        self.sources = {s.key: s for s in repo.source_manifest(sid) if supported(s.relative_path)}
        self.cache = OrderedDict()
        self.cache_bytes = 0
        self.files = {}
        self.definitions = []
        self.groups = {}
        self.tables = {}
        self.numeric_rows = {}
        self.complete = True
        with repo._connection(read_only=True) as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key=?", (VERSION + ":" + sid,)
            ).fetchone()
            policy = conn.execute(
                "SELECT policy_json FROM snapshots WHERE snapshot_id=?", (sid,)
            ).fetchone()
        self.available = row is not None
        if row is None:
            if json.loads(policy[0]).get("analysis_context", {}).get("weapons") == VERSION:
                raise SnapshotError("CACHE_MISSING", "Weapon manifest is missing.")
            return
        if len(row[0].encode()) > 1024 * 1024:
            raise SnapshotError("LIMIT_EXCEEDED", "Weapon manifest budget exceeded.")
        manifest = json.loads(row[0])
        if manifest["version"] != VERSION:
            raise SnapshotError("SOURCE_CHANGED", "Weapon policy changed.")
        for meta in manifest["files"]:
            key = tuple(meta["key"])
            source = self.sources.get(key)
            if (
                key in self.files
                or source is None
                or (meta["sha"], meta["size"]) != (source.file_sha256, source.size)
            ):
                raise SnapshotError("SOURCE_CHANGED", "Weapon source membership differs.")
            if not 0 < meta["product_size"] <= MAX_PRODUCT:
                raise SnapshotError("LIMIT_EXCEEDED", "Weapon product size invalid.")
            self.files[key] = meta
        if sum(meta["product_size"] for meta in self.files.values()) > MAX_CONTEXT:
            raise SnapshotError("LIMIT_EXCEEDED", "Weapon catalog budget exceeded.")
        if set(self.files) != set(self.sources):
            raise SnapshotError("SOURCE_CHANGED", "Weapon manifest omits source files.")
        counts = Counter()
        index_bytes = 0
        for key in self.files:
            if cancel:
                cancel()
            contents = self.load(key)
            self.complete &= contents["complete"]
            if contents["format"] == "csv":
                self.tables[key] = contents
                for row in contents["rows"]:
                    self.numeric_rows.setdefault(row["id"], []).append((key, contents, row))
            for index, node in enumerate(contents.get("roots", ())):
                requirements, links_complete = references(node, "prerequisites")
                tags, tags_complete = references(node, "tags")
                set_field = single(node, "component_set")
                item = {
                    "file_key": key,
                    "index": index,
                    "id": node["id"],
                    "span": node["span"],
                    "complete": node["complete"],
                    "requirements": requirements,
                    "links_complete": links_complete,
                    "tags": [name for name, _ in tags],
                    "tags_complete": tags_complete,
                    "size": literal(single(node, "size")) or "",
                    "group_id": literal(set_field),
                    "group_span": set_field["span"] if set_field else None,
                    "conditions": any(
                        fields(node, key)
                        for key in (
                            "potential",
                            "possible",
                            "slot_restriction",
                            "size_restriction",
                            "class_restriction",
                            "show_tech_unlock_if",
                            "allow",
                            "restriction",
                        )
                    ),
                    "special": any(
                        fields(node, key)
                        for key in (
                            "on_hit",
                            "chain_damage",
                            "collateral_damage",
                            "scripted_action",
                        )
                    ),
                    "space_fauna": literal(single(node, "is_space_fauna_component_set")) == "yes",
                }
                index_bytes += len(storage_json(item, max_bytes=8192))
                if index_bytes > MAX_PRODUCT:
                    raise SnapshotError(
                        "LIMIT_EXCEEDED", "Weapon definition index budget exceeded."
                    )
                if node["root"] == "component_set":
                    self.groups.setdefault(node["id"], []).append(item)
                else:
                    counts[node["id"]] += 1
                    ref = self.ref(key, node["span"])
                    identity = {
                        "kind": KIND,
                        "game_id": node["id"],
                        "source": ref,
                        "occurrence": counts[node["id"]],
                    }
                    item["entity_key"] = hashlib.sha256(
                        storage_json(identity, max_bytes=1024 * 1024)
                    ).hexdigest()
                    item["occurrence"] = counts[node["id"]]
                    self.definitions.append(item)
        self.by_entity = {v["entity_key"]: v for v in self.definitions}
        self.by_id = {}
        for item in self.definitions:
            self.by_id.setdefault(item["id"], []).append(item)
        # Canonical rows must agree with independently reconstructed original products.
        with repo._connection(read_only=True) as conn:
            if conn.execute(
                "SELECT 1 FROM entities WHERE snapshot_id=? AND kind NOT IN ('technology','event','component_template') LIMIT 1",
                (sid,),
            ).fetchone():
                raise SnapshotError("SOURCE_CHANGED", "Unexpected entity kind in weapon snapshot.")
            rows = conn.execute(
                "SELECT * FROM entities WHERE snapshot_id=? AND kind=? ORDER BY entity_key",
                (sid, KIND),
            ).fetchall()
            if len(rows) != len(self.definitions):
                raise SnapshotError("SOURCE_CHANGED", "Weapon entity membership differs.")
            for row in rows:
                item = self.by_entity.get(row["entity_key"])
                if item is None:
                    raise SnapshotError("SOURCE_CHANGED", "Unknown weapon identity.")
                expected = {
                    "version": VERSION,
                    "file_key": list(item["file_key"]),
                    "root_index": item["index"],
                    "source_ref": self.ref(item["file_key"], item["span"]),
                    "subtype": "weapon",
                }
                source_ref = expected["source_ref"]
                expected_resolution = "raw_definition" if item["complete"] else "partial"
                if (
                    json.loads(row["candidate_json"]) != expected
                    or row["game_id"] != item["id"]
                    or row["occurrence"] != item["occurrence"]
                    or row["resolution"] != expected_resolution
                    or any(
                        row[k] != source_ref[k]
                        for k in (
                            "source_kind",
                            "source_id",
                            "relative_path",
                            "byte_start",
                            "byte_end",
                        )
                    )
                ):
                    raise SnapshotError("SOURCE_CHANGED", "Weapon entity proof differs.")

    def ref(self, key, position):
        source = self.sources[key]
        return SourceRef(self.sid, *key, source.file_sha256, *position).to_dict()

    def load(self, key):
        if key in self.cache:
            self.cache.move_to_end(key)
            return self.cache[key][0]
        source = self.sources[key]
        meta = self.files[key]
        original = self.repo.cache.read(source.file_sha256, source.size)
        value = product(original, source.relative_path)
        saved = json.loads(self.repo.cache.read(meta["product_sha"], meta["product_size"]))
        if saved != value:
            raise SnapshotError("SOURCE_CHANGED", "Weapon product differs from original source.")
        size = meta["product_size"]
        self.cache[key] = (value, size)
        self.cache_bytes += size
        while self.cache_bytes > 32 * 1024 * 1024 and len(self.cache) > 1:
            _, (_, old_size) = self.cache.popitem(last=False)
            self.cache_bytes -= old_size
        return value

    def node(self, item):
        return self.load(tuple(item["file_key"]))["roots"][item["index"]]
