"""Snapshot-neutral, SHA-bound file products in the existing private blob cache."""
from __future__ import annotations

import hashlib
import json
from dataclasses import fields, is_dataclass

from stellaris_supporter.domain import generic
from stellaris_supporter.domain import technology as tech
from stellaris_supporter.domain.event_references import EventReferenceRecord, StaticReference
from stellaris_supporter.localisation import reader as loc
from stellaris_supporter.storage.identity import SnapshotError, storage_json
from stellaris_supporter.storage.repository import _immediate

_VERSION = "file-products-1"
_NEUTRAL = "0" * 64
MAX_PRODUCT_BYTES = 16 * 1024 * 1024
_CLASSES = {cls.__name__: cls for cls in (
    tech.SourceContext, tech.SourceRef, tech.RawNodeRef, tech.TechnologyField,
    tech.TechnologyPrerequisite, tech.TechnologyDiagnostic, tech.TechnologyCandidate,
    tech.TechnologyAdaptResult, generic.DomainField, generic.DomainDiagnostic,
    generic.DomainCandidate, generic.DomainAdaptResult, EventReferenceRecord, StaticReference,
    loc.LocalisationDiagnostic, loc.LocalisationComment, loc.LocalisationHeader,
    loc.LocalisationEntry, loc.LocalisationDocument,
)}


def file_key(source):
    return source.source_kind, source.source_id, source.relative_path


def classify_files(previous, current):
    """Keyed manifests; timestamps and snapshot-dependent keys are irrelevant."""
    before = {file_key(s): s.file_sha256 for s in previous}
    after = {s.descriptor().key: s.descriptor().file_sha256 for s in current}
    return {name: tuple(sorted(key for key in set(before) | set(after) if predicate(key)))
            for name, predicate in (
                ("added", lambda key: key not in before),
                ("removed", lambda key: key not in after),
                ("modified", lambda key: key in before and key in after and before[key] != after[key]),
                ("unchanged", lambda key: key in before and key in after and before[key] == after[key]),
            )}


def _guard_refs(value, sid):
    if isinstance(value, dict):
        if "snapshot_id" in value and "file_sha256" in value:
            return {**value, "snapshot_id": sid}
        return {key: _guard_refs(item, sid) for key, item in value.items()}
    if isinstance(value, list):
        return [_guard_refs(item, sid) for item in value]
    return value


def _pack(value):
    if is_dataclass(value):
        content = {f.name: _pack(getattr(value, f.name)) for f in fields(value) if f.name != "_source"}
        if isinstance(value, (tech.SourceRef, tech.SourceContext)):
            content["snapshot_id"] = _NEUTRAL
        if isinstance(value, StaticReference) and value.conditions_raw is not None:
            content["conditions_raw"] = json.dumps(
                _guard_refs(json.loads(value.conditions_raw), _NEUTRAL),
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
        return {"$type": type(value).__name__, "fields": content}
    if isinstance(value, tuple):
        return [_pack(item) for item in value]
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError("Unsupported cached product type")


def _unpack(value, source, context, budget):
    budget[0] += 1
    if budget[0] > 300_000:
        raise ValueError("Cached product item budget exceeded")
    if isinstance(value, list):
        return tuple(_unpack(item, source, context, budget) for item in value)
    if isinstance(value, dict):
        if set(value) != {"$type", "fields"} or value["$type"] not in _CLASSES:
            raise ValueError("Unknown cached type")
        cls = _CLASSES[value["$type"]]
        names = {f.name for f in fields(cls) if f.name != "_source"}
        if not isinstance(value["fields"], dict) or set(value["fields"]) != names:
            raise ValueError("Cached field contract differs")
        args = {name: _unpack(item, source, context, budget)
                for name, item in value["fields"].items()}
        if cls in {tech.SourceRef, tech.SourceContext}:
            if args["snapshot_id"] != _NEUTRAL or any(args[name] != getattr(context, name)
                for name in ("source_kind", "source_id", "relative_path", "file_sha256")):
                raise ValueError("Cached source binding differs")
            args["snapshot_id"] = context.snapshot_id
            if cls is tech.SourceRef and (
                    type(args["byte_start"]) is not int or type(args["byte_end"]) is not int
                    or not 0 <= args["byte_start"] <= args["byte_end"] <= len(source)):
                raise ValueError("Cached source offsets differ")
        if cls is StaticReference and args["conditions_raw"] is not None:
            args["conditions_raw"] = json.dumps(
                _guard_refs(json.loads(args["conditions_raw"]), context.snapshot_id),
                ensure_ascii=False, sort_keys=True, separators=(",", ":"),
            )
        if "_source" in {f.name for f in fields(cls)}:
            args["_source"] = source
        return cls(**args)
    if value is None or type(value) in {str, int, bool}:
        return value
    raise ValueError("Invalid cached product value")


class FileProducts:
    """Only content-addressed JSON is decoded; no pickle/imported cache code."""

    def __init__(self, repository, policy):
        self.repository = repository
        policy_digest = hashlib.sha256(storage_json(policy.identity_fields(), max_bytes=1024 * 1024)).hexdigest()
        self.prefix = f"{_VERSION}:{policy_digest}:"
        self.pending = {}
        with repository._connection(read_only=True) as conn:
            rows = conn.execute("SELECT key,value FROM settings WHERE key LIKE ? LIMIT 50001",
                                (self.prefix + "%",)).fetchall()
        self.pointers = dict(rows) if len(rows) <= 50_000 else {}

    def _key(self, source):
        identity = [*file_key(source), source.descriptor().file_sha256]
        return self.prefix + hashlib.sha256(storage_json(identity, max_bytes=8192)).hexdigest()

    def get(self, source, context):
        pointer = self.pointers.get(self._key(source))
        if pointer is None:
            return None
        try:
            meta = json.loads(pointer)
            data = self.repository.cache.read(meta["sha256"], meta["size"])
            value = json.loads(data)
            if value["version"] != _VERSION or value["key"] != self._key(source):
                return None
            product = _unpack(value["product"], source.data, context, [0])
            expected = (tech.TechnologyAdaptResult if source.relative_path.startswith("common/technology/")
                        else tuple if source.relative_path.startswith("events/") else loc.LocalisationDocument)
            if not isinstance(product, expected):
                return None
            if expected is tuple and (len(product) != 2 or not isinstance(product[0], generic.DomainAdaptResult)
                                      or not all(isinstance(r, EventReferenceRecord) for r in product[1])):
                return None
            return product
        except (SnapshotError, ValueError, TypeError, KeyError, RecursionError, UnicodeError):
            # Missing/stale/damaged optional products fall back to original source parsing.
            return None

    def put(self, source, product):
        try:
            key = self._key(source)
            encoded = storage_json({"version": _VERSION, "key": key, "product": _pack(product)},
                                   max_bytes=MAX_PRODUCT_BYTES, max_items=500_000)
            digest = hashlib.sha256(encoded).hexdigest()
            self.repository.cache.put(encoded, digest)
            self.pending[key] = json.dumps({"sha256": digest, "size": len(encoded)})
        except (SnapshotError, ValueError, TypeError, RecursionError):
            # Indexing remains available when an optional product is too large to cache.
            return

    def flush(self):
        if self.pending:
            with self.repository._connection() as conn, _immediate(conn):
                conn.executemany("INSERT INTO settings(key,value) VALUES(?,?) "
                                 "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                                 self.pending.items())
            self.pending.clear()
