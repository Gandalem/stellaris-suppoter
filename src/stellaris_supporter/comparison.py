"""Read-only snapshot comparison, ordered facts and explicit ambiguity."""
from __future__ import annotations

import hashlib
import json
import re
from collections import Counter, defaultdict
from dataclasses import asdict, dataclass

from stellaris_supporter.domain import SourceContext, SourceRef
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import lex_bytes
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.identity import storage_json
from stellaris_supporter.storage.repository import _entry_data

MAX_COMPARE_RECORDS = 200_000
MAX_COMPARE_BYTES = 64 * 1024 * 1024
MAX_DIFF_OUTPUT_BYTES = 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class DiffQuery:
    before_snapshot: str
    after_snapshot: str
    kind: str | None = None
    game_id: str | None = None
    include_source_changes: bool = False
    limit: int = 20
    offset: int = 0
    interest_ids: tuple[str, ...] = ()

    def validate(self):
        if (any(not isinstance(s, str) or not _HEX.fullmatch(s)
                for s in (self.before_snapshot, self.after_snapshot))
                or self.kind is not None and self.kind not in ("technology", "event")
                or type(self.include_source_changes) is not bool
                or type(self.limit) is not int or not 1 <= self.limit <= 100
                or type(self.offset) is not int or not 0 <= self.offset <= 100_000
                or not isinstance(self.interest_ids, tuple) or len(self.interest_ids) > 100):
            raise SnapshotError("QUERY_INVALID", "Invalid comparison query.")
        ids = (*self.interest_ids, *((self.game_id,) if self.game_id is not None else ()))
        if any(not isinstance(s, str) or not s or len(s) > 512 or s != s.strip()
               or any(not c.isprintable() for c in s) for s in ids):
            raise SnapshotError("QUERY_INVALID", "Invalid comparison ID filter.")


@dataclass(frozen=True, slots=True)
class DiffEnvelope:
    schema_version: int
    status: str
    query: DiffQuery
    context: dict
    summary: dict
    results: tuple[dict, ...] = ()
    summary_complete: bool = True
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()
    diagnostics: tuple[dict, ...] = ()
    abstained: bool = False

    def to_dict(self):
        return asdict(self)


class _AnalysisLimit(Exception):
    pass


class _Budget:
    def __init__(self):
        self.records = self.size = 0

    def add(self, item):
        self.records += 1
        self.size += len(storage_json(item, max_bytes=MAX_COMPARE_BYTES))
        if self.records > MAX_COMPARE_RECORDS or self.size > MAX_COMPARE_BYTES:
            raise _AnalysisLimit


def _tokens(raw):
    parsed = lex_bytes(raw)
    if any(d.code == "LIMIT_EXCEEDED" for d in parsed.diagnostics):
        raise SnapshotError("LIMIT_EXCEEDED", "Comparison lexical budget exceeded.")
    return tuple((t.kind, t.text) for t in parsed.tokens if t.kind not in {"whitespace", "comment", "bom"})


def _semantic(node):
    if node.kind == "pair":
        return node.kind, node.key, node.operator, tuple(_semantic(n) for n in node.children)
    if node.kind == "block":
        return node.kind, tuple(_semantic(n) for n in node.children)
    return node.kind, _tokens(node.raw_bytes())


def _location(ref):
    if ref is None:
        return None
    return tuple(ref[key] for key in ("source_kind", "source_id", "relative_path",
                                      "byte_start", "byte_end", "line_start", "line_end"))


def _view(item):
    return {key: item[key] for key in ("entity_key", "game_id", "kind", "display_name", "source_ref", "coverage_complete")}


def _fingerprint(item):
    ref = item["source_ref"]
    return (ref["source_kind"], ref["source_id"], ref["relative_path"], item["fingerprint"])


def _field_delta(before, after):
    left, right = defaultdict(list), defaultdict(list)
    for field in before:
        left[field["name"]].append(field)
    for field in after:
        right[field["name"]].append(field)
    changes = []
    for name in sorted(set(left) | set(right)):
        a, b = left[name], right[name]
        if [(f["operator"], f["semantic"]) for f in a] != [(f["operator"], f["semantic"]) for f in b]:
            def visible(items):
                return [{key: value for key, value in f.items() if key != "semantic"} for f in items]
            changes.append({"section": "fields", "field": name, "before": visible(a), "after": visible(b)})
    if [f["name"] for f in before] != [f["name"] for f in after]:
        changes.append({"section": "field_order", "before": [f["name"] for f in before],
                        "after": [f["name"] for f in after]})
    return changes


def _relation_signature(links):
    return tuple((r["relation_kind"], r["target_game_id"], r["status"], r["conditions_semantic"]) for r in links)


def _visible_links(links):
    return [{k: v for k, v in r.items() if k != "conditions_semantic"} for r in links]


def _pair_change(before, after, include_source):
    details = _field_delta(before["fields"], after["fields"])
    if before["fingerprint"] != after["fingerprint"] and not details:
        details.append({"section": "definition", "before": before["definition"], "after": after["definition"]})
    if _relation_signature(before["relations"]) != _relation_signature(after["relations"]):
        details.append({"section": "relations", "before": _visible_links(before["relations"]),
                        "after": _visible_links(after["relations"])})
    if (before["localisation_complete"] and after["localisation_complete"]
            and before["display_name"] != after["display_name"]):
        details.append({"section": "localisation", "before": before["display_name"], "after": after["display_name"]})
    if (before["coverage_complete"], before["coverage_reasons"]) != (after["coverage_complete"], after["coverage_reasons"]):
        details.append({"section": "coverage", "before": before["coverage_reasons"], "after": after["coverage_reasons"]})
    changed_source = _location(before["source_ref"]) != _location(after["source_ref"])
    if not details and not (include_source and changed_source):
        return None
    return {"section": "entities", "change_kind": "modified" if details else "source_changed",
            "kind": after["kind"], "game_id": after["game_id"], "before": _view(before), "after": _view(after),
            "details": details}


class DiffService:
    """Immutable inputs; a result can be displayed by CLI or future card views."""
    def __init__(self, repository):
        self.repository = repository

    def compare(self, query: DiffQuery) -> DiffEnvelope:
        valid = False
        self._disk_stores = []
        try:
            if not isinstance(query, DiffQuery):
                raise SnapshotError("QUERY_INVALID", "Expected a DiffQuery.")
            query.validate()
            valid = True
            with self.repository.reference_reader(query.before_snapshot) as before:
                with self.repository.reference_reader(query.after_snapshot) as after:
                    result = self._compare(query, before, after)
            total = 0
            for part in json.JSONEncoder(ensure_ascii=False, allow_nan=False).iterencode(result.to_dict()):
                total += len(part.encode("utf-8"))
                if total > MAX_DIFF_OUTPUT_BYTES:
                    raise SnapshotError("LIMIT_EXCEEDED", "Comparison response byte budget exceeded.")
            return result
        except (SnapshotError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            code = exc.code if isinstance(exc, SnapshotError) else "SOURCE_CHANGED"
            safe = query if valid else DiffQuery("0" * 64, "0" * 64)
            return DiffEnvelope(1, "error", safe, {}, {}, summary_complete=False,
                diagnostics=({"code": code, "severity": "error", "message": f"Comparison failed: {code}."},), abstained=True)
        finally:
            for store in self._disk_stores:
                store.close()

    def _manifest(self, reader, events):
        rows = reader.conn.execute("SELECT source_kind,source_id,relative_path,file_sha256,byte_size "
                                   "FROM source_files WHERE snapshot_id=? "
                                   "ORDER BY source_kind,source_id,relative_path LIMIT 50001", (reader.snapshot_id,)).fetchall()
        if len(rows) > 50_000:
            raise SnapshotError("LIMIT_EXCEEDED", "Comparison manifest exceeded.")
        result = {}
        for row in rows:
            path = row["relative_path"]
            if path.startswith("events/") and not events:
                continue
            if not path.startswith(("common/technology/", "common/scripted_variables/", "common/component_templates/", "common/component_sets/", "events/", "localisation/korean/", "localisation/english/")):
                continue
            item = dict(row)
            reader._verified(row["file_sha256"], row["byte_size"])
            result[(row["source_kind"], row["source_id"], path)] = item
        return result

    def _localisations(self, reader, manifest, budget):
        from stellaris_supporter.storage.catalogue import FileCatalogue
        from stellaris_supporter.storage.disk_comparison import DiskEntries
        store = FileCatalogue.for_snapshot(self.repository, reader.snapshot_id)
        if store is not None:
            self._disk_stores.append(store)
            catalogue = store.catalogue(reader.snapshot_id)
            return catalogue, DiskEntries(catalogue), catalogue.source_complete
        documents, entries = [], defaultdict(list)
        for key, meta in manifest.items():
            if not key[2].startswith("localisation/"):
                continue
            data = reader._verified(meta["file_sha256"], meta["byte_size"])[0]
            reader.charge(len(data))
            context = SourceContext(reader.snapshot_id, *key, meta["file_sha256"])
            doc = parse_localisation(data, context)
            if any(d.code == "LIMIT_EXCEEDED" for d in doc.diagnostics):
                raise SnapshotError("LIMIT_EXCEEDED", "Comparison localisation limit exceeded.")
            stored = reader.conn.execute("SELECT entry_json FROM localisation_entries WHERE snapshot_id=? "
                        "AND source_kind=? AND source_id=? AND relative_path=? ORDER BY byte_start,language,localisation_key,occurrence",
                        (reader.snapshot_id, *key))
            ordered = sorted(doc.entries, key=lambda e: (e.source_ref.byte_start, e.language, e.key, e.occurrence))
            for entry in ordered:
                row = next(stored, None)
                if row is None or json.loads(row[0]) != _entry_data(entry):
                    raise SnapshotError("SOURCE_CHANGED", "Stored translation differs from original source.")
                value = {"language": entry.language, "key": entry.key, "marker": entry.marker,
                         "raw_value": entry.raw_value, "display_value": entry.display_value,
                         "has_unsupported_escape": entry.has_unsupported_escape,
                         "source_ref": entry.source_ref.to_dict()}
                budget.add(value)
                entries[(entry.language, entry.key)].append(value)
            if next(stored, None) is not None:
                raise SnapshotError("SOURCE_CHANGED", "Stored translation has extra entries.")
            documents.append(doc)
        catalog = build_localisation_catalog(tuple(documents))
        if any(d.code in {"LIMIT_EXCEEDED", "LOC_SNAPSHOT_MISMATCH"} for d in catalog.diagnostics):
            raise SnapshotError("LIMIT_EXCEEDED", "Comparison localisation catalog exceeded.")
        return catalog, entries, all(doc.complete for doc in documents)

    def _definitions(self, reader, manifest, catalog, kinds, budget, localisation_complete=True):
        result = defaultdict(list)
        policy = json.loads(reader.snapshot["policy_json"])
        language = policy.get("analysis_context", {}).get("language", "korean")
        for key, meta in manifest.items():
            kind = "technology" if key[2].startswith("common/technology/") else "event" if key[2].startswith("events/") else None
            if kind not in kinds:
                continue
            data = reader._verified(meta["file_sha256"], meta["byte_size"])[0]
            canonical = {}
            if data:
                ref = SourceRef(reader.snapshot_id, *key, meta["file_sha256"], 0, len(data),
                                1, data.count(b"\n", 0, len(data) - 1) + 1)
                canonical = reader._records(ref, kind)
            rows = reader.conn.execute("SELECT entity_key,game_id,kind,occurrence,source_kind,source_id,relative_path,"
                "byte_start,byte_end,resolution,localisation_json FROM entities WHERE snapshot_id=? AND source_kind=? "
                "AND source_id=? AND relative_path=? AND kind=? ORDER BY byte_start,byte_end,entity_key",
                (reader.snapshot_id, *key, kind))
            seen = 0
            for row in rows:
                seen += 1
                ref, links, complete, reasons = reader.verify(dict(row))
                record = canonical[(ref.byte_start, ref.byte_end)]
                base = record.candidate if kind == "event" else record
                semantic = tuple(_semantic(item) for item in base.items)
                fingerprint = hashlib.sha256(storage_json(semantic, max_bytes=MAX_COMPARE_BYTES)).hexdigest()
                fields = [{"name": f.name, "occurrence": f.occurrence, "operator": f.operator,
                           "raw_expression": f.raw_value, "semantic": None if f.value is None else _semantic(f.value),
                           "source_ref": f.source_ref.to_dict(),
                           "value_source_ref": None if f.value is None else f.value.source_ref.to_dict()}
                          for f in base.fields]
                relations = []
                for link in links:
                    targets = reader.candidates(kind, link["target_game_id"], 2)
                    status = "unresolved" if not targets else "ambiguous" if len(targets) > 1 else "resolved"
                    guards = json.loads(link["conditions_raw"]) if link["conditions_raw"] else []
                    guards_sig = tuple((g["name"], _tokens(g["raw"].encode("utf-8"))) for g in guards)
                    relations.append({"relation_kind": link["relation_kind"], "target_game_id": link["target_game_id"],
                        "status": status, "occurrence": link["occurrence"], "source_ref": link["source_ref"].to_dict(),
                        "conditions_raw": link["conditions_raw"], "conditions_semantic": guards_sig})
                name = row["game_id"]
                if kind == "technology":
                    if hasattr(catalog, "resolve"):
                        from stellaris_supporter.localisation.resolver import (
                            TechnologyLocalisedName,
                        )
                        resolved = TechnologyLocalisedName(base, catalog.resolve(base.game_id, language)[0])
                    else:
                        resolved = resolve_technology_name(base, catalog, requested_language=language)
                    if resolved.localisation.truncated:
                        raise SnapshotError("LIMIT_EXCEEDED", "Comparison name resolution exceeded.")
                    if row["localisation_json"] is not None and json.loads(row["localisation_json"]) != resolved.localisation.to_dict():
                        raise SnapshotError("SOURCE_CHANGED", "Stored display name differs from its sources.")
                    name = resolved.localisation.display_value
                item = {"entity_key": row["entity_key"], "kind": kind, "game_id": row["game_id"],
                        "display_name": name, "source_ref": ref.to_dict(), "fields": fields,
                        "relations": relations, "fingerprint": fingerprint, "definition": semantic,
                        "coverage_complete": complete, "coverage_reasons": reasons,
                        "localisation_complete": localisation_complete,
                        "localisation_key": getattr(base, "localisation_key", row["game_id"])}
                budget.add(item)
                result[(kind, row["game_id"])].append(item)
            expected = sum(c.game_id is not None for c in canonical.values())
            if seen != expected:
                raise SnapshotError("SOURCE_CHANGED", "Snapshot definitions omit or add original roots.")
        return result

    def _entity_changes(self, groups_before, groups_after, include_source):
        changes = []
        for kind, game_id in sorted(set(groups_before) | set(groups_after)):
            left, right = list(groups_before.get((kind, game_id), ())), list(groups_after.get((kind, game_id), ()))
            if not left or not right:
                for item in left or right:
                    changes.append({"section": "entities", "change_kind": "removed" if left else "added",
                        "kind": kind, "game_id": game_id, "before": _view(item) if left else None,
                        "after": _view(item) if right else None,
                        "details": [{"section": "fields", "before": item["fields"] if left else None,
                                     "after": item["fields"] if right else None}]})
                continue
            if len(left) == len(right) == 1:
                change = _pair_change(left[0], right[0], include_source)
                if change:
                    changes.append(change)
                continue
            # Equal multisets preserve duplicate counts without inventing identities.
            if Counter(_fingerprint(i) for i in left) == Counter(_fingerprint(i) for i in right):
                a, b = defaultdict(list), defaultdict(list)
                for item in left:
                    a[_fingerprint(item)].append(item)
                for item in right:
                    b[_fingerprint(item)].append(item)
                for fingerprint in a:
                    # Equal semantic definitions share the same relation/name semantics.
                    change = _pair_change(a[fingerprint][0], b[fingerprint][0], False)
                    if change:
                        change["before_candidates"] = [_view(i) for i in a[fingerprint]]
                        change["after_candidates"] = [_view(i) for i in b[fingerprint]]
                        change["before"] = change["after"] = None
                        changes.append(change)
                    elif include_source and sorted(_location(i["source_ref"]) for i in a[fingerprint]) != sorted(_location(i["source_ref"]) for i in b[fingerprint]):
                        changes.append({"section": "entities", "change_kind": "source_changed", "kind": kind,
                            "game_id": game_id, "before_candidates": [_view(i) for i in a[fingerprint]],
                            "after_candidates": [_view(i) for i in b[fingerprint]], "details": []})
                continue
            counts_a, counts_b = Counter(_fingerprint(i) for i in left), Counter(_fingerprint(i) for i in right)
            for fingerprint in counts_a.keys() & counts_b.keys():
                if counts_a[fingerprint] == counts_b[fingerprint] == 1:
                    a = next(i for i in left if _fingerprint(i) == fingerprint)
                    b = next(i for i in right if _fingerprint(i) == fingerprint)
                    change = _pair_change(a, b, include_source)
                    if change:
                        changes.append(change)
                    left.remove(a)
                    right.remove(b)
            if left or right:
                changes.append({"section": "entities", "change_kind": "ambiguous", "kind": kind,
                                "game_id": game_id, "before_candidates": [_view(i) for i in left],
                                "after_candidates": [_view(i) for i in right], "details": []})
        return changes

    def _translation_changes(self, left, right, include_source, keys=None):
        from stellaris_supporter.storage.disk_comparison import DiskEntries, translation_changes
        if isinstance(left, DiskEntries) or isinstance(right, DiskEntries):
            return translation_changes(left, right, include_source, keys)
        changes = []
        for language, key in sorted(set(left) | set(right)):
            if keys is not None and key not in keys:
                continue
            a, b = left.get((language, key), []), right.get((language, key), [])
            def semantic(items):
                return [(i["marker"], i["raw_value"], i["has_unsupported_escape"]) for i in items]
            if semantic(a) == semantic(b):
                if not include_source or [_location(i["source_ref"]) for i in a] == [_location(i["source_ref"]) for i in b]:
                    continue
                change = "source_changed"
            else:
                change = "added" if not a else "removed" if not b else "ambiguous" if len(a) > 1 or len(b) > 1 else "modified"
            changes.append({"section": "localisation", "change_kind": change, "kind": "localisation",
                            "game_id": key, "language": language, "before": a, "after": b, "details": []})
        return changes

    def _compare(self, query, before, after):
        policies = [json.loads(r.snapshot["policy_json"]) for r in (before, after)]
        events = before.supports("event") and after.supports("event")
        comparable = all(before.snapshot[key] == after.snapshot[key]
                         for key in ("parser_version", "adapter_version", "context_kind"))
        kinds = {"technology", "event"} if events else {"technology"}
        diagnostics = []
        if before.supports("event") != after.supports("event"):
            diagnostics.append({"code": "DIFF_SCOPE_DIFFERENT", "severity": "info",
                                "message": "Event collection scopes differ; only common scopes are compared."})
        if policies[0] != policies[1]:
            diagnostics.append({"code": "DIFF_POLICY_DIFFERENT", "severity": "info",
                                "message": "Snapshot policies differ; file and interpretation changes are distinct."})
        if not comparable:
            diagnostics.append({"code": "DIFF_INTERPRETATION_UNSUPPORTED", "severity": "warning",
                                "message": "Parser/adapter versions or source contexts differ; definition comparison is omitted."})
        context = {"before": before.context(), "after": after.context(), "comparison_scope": sorted(kinds),
                   "definition_comparable": comparable,
                   "before_policy": {k: before.snapshot[k] for k in ("parser_version", "adapter_version", "policy_hash")},
                   "after_policy": {k: after.snapshot[k] for k in ("parser_version", "adapter_version", "policy_hash")}}
        if query.kind is not None and query.kind not in kinds:
            return DiffEnvelope(1, "unsupported", query, context, {}, summary_complete=False,
                diagnostics=({"code": "DIFF_SCOPE_UNSUPPORTED", "severity": "info",
                              "message": "The requested kind is not collected on both snapshots."},))
        manifests = self._manifest(before, events), self._manifest(after, events)
        file_changes = []
        file_summary = Counter()
        for key in sorted(set(manifests[0]) | set(manifests[1])):
            a, b = manifests[0].get(key), manifests[1].get(key)
            change = "added" if a is None else "removed" if b is None else "modified" if a["file_sha256"] != b["file_sha256"] else "unchanged"
            file_summary[change] += 1
            if change != "unchanged":
                file_changes.append({"section": "files", "change_kind": change, "kind": "file", "game_id": key[2],
                                     "before": a, "after": b, "details": []})
        wanted = set(query.interest_ids)
        if query.game_id is not None:
            wanted.add(query.game_id)
        changes = [] if wanted or query.kind is not None else file_changes
        budget, complete, reasons = _Budget(), True, []
        a_groups, b_groups = {}, {}
        try:
            cat_a, loc_a, loc_complete_a = self._localisations(before, manifests[0], budget)
            cat_b, loc_b, loc_complete_b = self._localisations(after, manifests[1], budget)
            from stellaris_supporter.storage.disk_comparison import ChangeWindow, DiskEntries
            disk_compare = isinstance(loc_a, DiskEntries) or isinstance(loc_b, DiskEntries)
            if disk_compare:
                changes = ChangeWindow(query.offset + query.limit + 1, changes)
            if comparable:
                a_groups = self._definitions(before, manifests[0], cat_a, kinds, budget, loc_complete_a)
                b_groups = self._definitions(after, manifests[1], cat_b, kinds, budget, loc_complete_b)
            def selected(groups):
                return {key: value for key, value in groups.items()
                        if (query.kind is None or key[0] == query.kind) and (not wanted or key[1] in wanted)}
            left, right = selected(a_groups), selected(b_groups)
            changes.extend(self._entity_changes(left, right, query.include_source_changes))
            local_keys = None
            if wanted or query.kind is not None:
                local_keys = set(wanted)
                for items in (*left.values(), *right.values()):
                    local_keys.update(i["localisation_key"] or i["game_id"] for i in items)
            if disk_compare or loc_complete_a and loc_complete_b:
                changes.extend(self._translation_changes(loc_a, loc_b, query.include_source_changes, local_keys))
            if not loc_complete_a or not loc_complete_b:
                complete = False
                diagnostics.append({"code": "DIFF_PARTIAL_LOCALISATION", "severity": "warning",
                                    "message": "Incomplete translation parsing cannot establish additions/removals."})
            if any(not item["coverage_complete"] for groups in (left, right) for items in groups.values() for item in items):
                diagnostics.append({"code": "DIFF_PARTIAL_DEFINITION", "severity": "warning",
                                    "message": "Some definitions have partial supported coverage."})
        except _AnalysisLimit:
            complete = False
            reasons.append("analysis_limit")
            # Incomplete collection cannot establish that a counterpart was removed/added.
            changes = [] if wanted or query.kind is not None else file_changes
        section_order = {"entities": 0, "localisation": 1, "files": 2}
        change_order = {"modified": 0, "added": 1, "removed": 2, "ambiguous": 3, "source_changed": 4}
        changes.sort(key=lambda item: (section_order[item["section"]], change_order[item["change_kind"]],
                                      item["kind"], item["game_id"], item.get("language", ""),
                                      json.dumps(item.get("before") or item.get("before_candidates"), sort_keys=True, ensure_ascii=False)))
        summary = {"files": {key: file_summary[key] for key in ("added", "modified", "removed", "unchanged")}, "changes": dict(changes.kinds if hasattr(changes, "kinds") else Counter(i["change_kind"] for i in changes)),
                   "sections": dict(changes.sections if hasattr(changes, "sections") else Counter(i["section"] for i in changes)), "total_results": len(changes),
                   "file_scope": "all_common_supported_files"}
        page = tuple(changes[query.offset:query.offset + query.limit])
        if query.offset + len(page) < len(changes):
            reasons.append("result_limit")
        for change in page:
            if change["section"] == "localisation":
                for catalogue in (cat_a, cat_b):
                    if hasattr(catalogue, "source_complete"):
                        catalogue.definitions(change["language"], change["game_id"])
        partial = not complete or not comparable or getattr(changes, "ambiguous", False) or any(i["change_kind"] == "ambiguous" for i in changes)
        partial |= any(d["severity"] == "warning" for d in diagnostics)
        if not comparable:
            complete = False
        return DiffEnvelope(1, "partial" if partial else "ok", query, context, summary, page,
                            complete, bool(reasons), tuple(reasons), tuple(diagnostics))
