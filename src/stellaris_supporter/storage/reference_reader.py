"""Bounded SQLite reader for one immutable reference request."""
from __future__ import annotations

import hashlib
import json

from stellaris_supporter.domain import SourceContext, SourceRef, adapt_technologies
from stellaris_supporter.domain.event_references import (
    EXTRACTOR_VERSION,
    MAX_DEFINITION_REFERENCES,
    extract_event_records,
)
from stellaris_supporter.domain.generic import adapt_domain
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.storage.identity import SnapshotError, storage_json
from stellaris_supporter.storage.repository import (
    MAX_JSON_BYTES,
    _VerifiedCitationReader,
)

MAX_REQUEST_SOURCE_BYTES = 64 * 1024 * 1024
_HARD_CODES = {"LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT", "PARSE_DIAGNOSTIC_LIMIT"}


class ReferenceReader(_VerifiedCitationReader):
    def __init__(self, repository, conn, sid):
        super().__init__(repository, conn, sid)
        self.work_bytes = 0
        self._canonical_key = None
        self._canonical = {}
        self.snapshot = dict(repository._ensure_ready(conn, sid))

    def charge(self, count):
        self.work_bytes += count
        if self.work_bytes > MAX_REQUEST_SOURCE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Reference source/parse budget exhausted.")

    def _verified(self, digest, size):
        if (digest, size) not in self._blobs:
            self.charge(size)
        return super()._verified(digest, size)

    def context(self):
        return {key: self.snapshot[key] for key in (
            "snapshot_id", "status", "checked_at", "game_version", "game_version_source",
            "branch", "context_kind", "mod_state",
        )}

    def supports(self, kind):
        if kind == "technology":
            return True
        policy = json.loads(self.snapshot["policy_json"])
        return policy.get("analysis_context", {}).get("event_references") == EXTRACTOR_VERSION

    def candidates(self, kind, game_id, limit=2, entity_key=None):
        sql = ("SELECT entity_key,game_id,kind,occurrence,source_kind,source_id,relative_path,"
               "byte_start,byte_end,resolution FROM entities "
               "WHERE snapshot_id=? AND kind=? AND game_id=?")
        args = [self.snapshot_id, kind, game_id]
        if entity_key is not None:
            sql += " AND entity_key=?"
            args.append(entity_key)
        sql += " ORDER BY source_kind,source_id,relative_path,byte_start,byte_end,entity_key LIMIT ?"
        args.append(limit)
        return [dict(row) for row in self.conn.execute(sql, args)]

    def _source(self, ref):
        self.read(ref)
        row = self.conn.execute(
            "SELECT byte_size FROM source_files WHERE snapshot_id=? AND source_kind=? "
            "AND source_id=? AND relative_path=?",
            (self.snapshot_id, ref.source_kind, ref.source_id, ref.relative_path),
        ).fetchone()
        return self._verified(ref.file_sha256, row[0])[0]

    def _records(self, ref, kind):
        key = (ref.source_kind, ref.source_id, ref.relative_path, ref.file_sha256, kind)
        if key == self._canonical_key:
            return self._canonical
        source = self._source(ref)
        # Event adapter also canonicalizes the supplied ParseResult once.
        self.charge(len(source) * (2 if kind == "event" else 1))
        parsed = parse_bytes(source)
        if any(d.code in _HARD_CODES for d in parsed.diagnostics):
            raise SnapshotError("LIMIT_EXCEEDED", "Reference parser budget exhausted.")
        context = SourceContext(self.snapshot_id, ref.source_kind, ref.source_id,
                                ref.relative_path, ref.file_sha256)
        if kind == "technology":
            result = adapt_technologies(parsed, source, context)
            records = result.candidates
        else:
            result = adapt_domain(parsed, source, context, "event")
            if result.blocked:
                raise SnapshotError("LIMIT_EXCEEDED", "Event adapter budget exhausted.")
            records = extract_event_records(result.candidates, parsed, source, context)
        if any(d.code in _HARD_CODES for d in result.diagnostics):
            raise SnapshotError("LIMIT_EXCEEDED", "Reference adapter budget exhausted.")
        self._canonical = {(c.source_ref.byte_start, c.source_ref.byte_end): c for c in records}
        self._canonical_key = key
        return self._canonical

    def verify(self, row, *, relation_budget=None):
        stored = self.conn.execute(
            "SELECT CASE WHEN length(CAST(candidate_json AS BLOB)) <= ? THEN candidate_json END "
            "AS candidate_json,length(CAST(candidate_json AS BLOB)) AS size "
            "FROM entities WHERE snapshot_id=? AND entity_key=?",
            (MAX_JSON_BYTES, self.snapshot_id, row["entity_key"]),
        ).fetchone()
        if stored is None or stored["size"] > MAX_JSON_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Candidate byte budget exceeded.")
        previous = self.conn.execute(
            "SELECT count(*) FROM entities WHERE snapshot_id=? AND kind=? AND game_id=? "
            "AND (source_kind,source_id,relative_path,byte_start,byte_end) < (?,?,?,?,?)",
            (self.snapshot_id, row["kind"], row["game_id"], row["source_kind"], row["source_id"],
             row["relative_path"], row["byte_start"], row["byte_end"]),
        ).fetchone()[0]
        if row["occurrence"] != previous + 1:
            raise SnapshotError("SOURCE_CHANGED", "Definition occurrence differs from source order.")
        payload = json.loads(stored["candidate_json"])
        ref = SourceRef(**payload["source_ref"])
        if (ref.snapshot_id != self.snapshot_id
                or any(getattr(ref, key) != row[key] for key in (
                    "source_kind", "source_id", "relative_path", "byte_start", "byte_end"))):
            raise SnapshotError("SOURCE_CHANGED", "Definition differs from its entity row.")
        if ref.byte_end - ref.byte_start > MAX_JSON_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Definition byte budget exceeded.")
        expected_key = hashlib.sha256(storage_json({
            "kind": row["kind"], "game_id": row["game_id"],
            "source": ref.to_dict(), "occurrence": row["occurrence"],
        }, max_bytes=MAX_JSON_BYTES)).hexdigest()
        if expected_key != row["entity_key"]:
            raise SnapshotError("SOURCE_CHANGED", "Entity identity differs from definition.")
        record = self._records(ref, row["kind"]).get((ref.byte_start, ref.byte_end))
        if (record is None or record.game_id != row["game_id"]
                or record.resolution != row["resolution"]
                or record.to_dict(include_raw=False) != payload):
            raise SnapshotError("SOURCE_CHANGED", "Stored definition differs from original AST.")
        if len(record.prerequisites) > MAX_DEFINITION_REFERENCES:
            raise SnapshotError("LIMIT_EXCEEDED", "Definition relation budget exceeded.")
        if relation_budget is not None and len(record.prerequisites) > relation_budget:
            return None
        rows = self.conn.execute(
            "SELECT occurrence,relation_kind,target_game_id,target_entity_key,status,"
            "CASE WHEN length(CAST(source_ref_json AS BLOB))<=? THEN source_ref_json END AS source_ref_json,"
            "length(CAST(source_ref_json AS BLOB)) AS ref_size,"
            "CASE WHEN length(CAST(conditions_raw AS BLOB))<=? THEN conditions_raw END AS conditions_raw,"
            "coalesce(length(CAST(conditions_raw AS BLOB)),0) AS conditions_size FROM relations "
            "WHERE snapshot_id=? AND from_entity_key=? ORDER BY occurrence LIMIT ?",
            (MAX_JSON_BYTES, MAX_JSON_BYTES, self.snapshot_id, row["entity_key"],
             MAX_DEFINITION_REFERENCES + 1),
        )
        links, relation_bytes = [], 0
        relation_kind = "prerequisite" if row["kind"] == "technology" else "event_reference"
        for ordinal, original in enumerate(record.prerequisites, 1):
            relation = next(rows, None)
            if relation is None:
                raise SnapshotError("SOURCE_CHANGED", "Reference rows omit a source token.")
            relation_bytes += relation["ref_size"] + relation["conditions_size"]
            if relation_bytes > MAX_JSON_BYTES:
                raise SnapshotError("LIMIT_EXCEEDED", "Definition relation byte budget exceeded.")
            conditions = getattr(original, "conditions_raw", None)
            if (relation["occurrence"] != ordinal or relation["relation_kind"] != relation_kind
                    or relation["target_game_id"] != original.target_game_id
                    or json.loads(relation["source_ref_json"]) != original.source_ref.to_dict()
                    or relation["conditions_raw"] != conditions):
                raise SnapshotError("SOURCE_CHANGED", "Reference differs from parent AST token/order.")
            self.read(original.source_ref)
            links.append({"occurrence": ordinal, "relation_kind": relation_kind,
                          "target_game_id": original.target_game_id,
                          "source_ref": original.source_ref,
                          "conditions_raw": conditions,
                          "stored_target": relation["target_entity_key"],
                          "stored_status": relation["status"]})
        if next(rows, None) is not None:
            raise SnapshotError("SOURCE_CHANGED", "Reference rows exceed the source definition.")
        if row["kind"] == "event":
            relevant = tuple(d.code for d in record.candidate.diagnostics
                             if d.severity != "info" and d.code != "DOMAIN_UNRESOLVED_LOCALISATION_KEY")
            complete = record.coverage_complete and not relevant
            reasons = (*record.coverage_reasons, *dict.fromkeys(relevant))
        else:
            complete = record.resolution == "raw_definition"
            reasons = ()
        return ref, tuple(links), complete, reasons
