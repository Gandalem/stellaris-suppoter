"""Snapshot-pinned reference graph API shared by CLI and future desktop views."""
from __future__ import annotations

import json
import re
from collections import deque
from dataclasses import asdict, dataclass

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.storage import SnapshotError, SnapshotRepository

MAX_CHECKED_NODES = 256
MAX_SCANNED_EDGES = 1024
MAX_RESPONSE_BYTES = 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")


@dataclass(frozen=True, slots=True)
class ReferenceQuery:
    game_id: str
    kind: str = "technology"
    snapshot_id: str | None = None
    entity_key: str | None = None
    depth: int = 1
    limit: int = 20

    def validate(self):
        if (not isinstance(self.game_id, str) or not self.game_id.strip()
                or self.game_id != self.game_id.strip() or len(self.game_id) > 512
                or any(not c.isprintable() for c in self.game_id)
                or not isinstance(self.kind, str) or self.kind not in {"technology", "event"}
                or type(self.depth) is not int or not 1 <= self.depth <= 16
                or type(self.limit) is not int or not 1 <= self.limit <= 100
                or any(value is not None and (not isinstance(value, str) or not _HEX.fullmatch(value))
                       for value in (self.snapshot_id, self.entity_key))):
            raise SnapshotError("QUERY_INVALID", "Invalid reference query.")


@dataclass(frozen=True, slots=True)
class ReferenceCard:
    """Serializable overlay bookmark; refresh never follows the active pointer."""
    snapshot_id: str
    game_id: str
    kind: str
    entity_key: str
    depth: int
    limit: int

    def to_dict(self):
        return asdict(self)


@dataclass(frozen=True, slots=True)
class ReferenceNode:
    entity_key: str
    game_id: str
    kind: str
    occurrence: int
    depth: int
    source_ref: SourceRef
    coverage_complete: bool
    coverage_reasons: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class ReferenceEdge:
    from_entity_key: str
    occurrence: int
    relation_kind: str
    target_game_id: str
    status: str
    target_entity_key: str | None
    candidate_entity_keys: tuple[str, ...]
    source_ref: SourceRef
    depth: int
    conditions_raw: str | None = None
    candidates_truncated: bool = False


@dataclass(frozen=True, slots=True)
class ReferenceEnvelope:
    schema_version: int
    status: str
    snapshot_id: str | None
    context: dict
    query: ReferenceQuery
    root_entity_key: str | None = None
    candidates: tuple[ReferenceNode, ...] = ()
    nodes: tuple[ReferenceNode, ...] = ()
    edges: tuple[ReferenceEdge, ...] = ()
    cycles: tuple[tuple[str, ...], ...] = ()
    truncated: bool = False
    truncation_reasons: tuple[str, ...] = ()
    diagnostics: tuple[dict, ...] = ()
    abstained: bool = False

    def to_dict(self):
        return asdict(self)


def _cycles(nodes, edges):
    adjacency = {key: [] for key in nodes}
    for edge in edges:
        if edge.status == "resolved" and edge.target_entity_key in adjacency:
            adjacency[edge.from_entity_key].append(edge.target_entity_key)
    colors, cycles = {}, []
    for start in adjacency:
        if colors.get(start):
            continue
        colors[start] = 1
        path, positions = [start], {start: 0}
        stack = [(start, iter(adjacency[start]))]
        while stack:
            current, children = stack[-1]
            child = next(children, None)
            if child is None:
                stack.pop()
                colors[current] = 2
                positions.pop(current)
                path.pop()
            elif colors.get(child) == 1:
                cycle = tuple(path[positions[child]:] + [child])
                if cycle not in cycles:
                    cycles.append(cycle)
            elif not colors.get(child):
                colors[child] = 1
                positions[child] = len(path)
                path.append(child)
                stack.append((child, iter(adjacency[child])))
    return tuple(cycles)


def _bounded(envelope):
    encoder = json.JSONEncoder(ensure_ascii=False, allow_nan=False)
    total = 0
    for part in encoder.iterencode(envelope.to_dict()):
        total += len(part.encode("utf-8"))
        if total > MAX_RESPONSE_BYTES:
            raise SnapshotError("LIMIT_EXCEEDED", "Reference response byte budget exceeded.")
    return envelope


class ReferenceService:
    """Each call owns its reader; no window toolkit, game process or active-state cache."""

    def __init__(self, repository: SnapshotRepository):
        self.repository = repository

    def refs(self, query: ReferenceQuery) -> ReferenceEnvelope:
        sid, context = None, {}
        validated = False
        try:
            if not isinstance(query, ReferenceQuery):
                raise SnapshotError("QUERY_INVALID", "Expected a ReferenceQuery.")
            query.validate()
            validated = True
            with self.repository.reference_reader(query.snapshot_id) as reader:
                sid, context = reader.snapshot_id, reader.context()
                if not reader.supports(query.kind):
                    return _bounded(ReferenceEnvelope(1, "unsupported", sid, context, query,
                        diagnostics=({"code": "REFERENCE_SCOPE_UNSUPPORTED", "severity": "info",
                                      "message": "Index with --include-events to query event references."},)))
                return _bounded(self._graph(reader, query, context))
        except (SnapshotError, ValueError, TypeError, KeyError, UnicodeError, RecursionError) as exc:
            code = exc.code if isinstance(exc, SnapshotError) else "SOURCE_CHANGED"
            # Failures contain no copied source/context or unbounded rejected input.
            return ReferenceEnvelope(1, "error", sid, {}, query if validated else ReferenceQuery(""),
                diagnostics=({"code": code, "severity": "error",
                              "message": f"Reference request failed: {code}."},), abstained=True)

    def _graph(self, reader, query, context):
        sid = reader.snapshot_id
        roots = reader.candidates(query.kind, query.game_id, query.limit + 1, query.entity_key)
        if not roots:
            return ReferenceEnvelope(1, "not_found", sid, context, query)
        checked, scanned = {}, 0
        reasons, partial = [], False

        def truncate(reason):
            if reason not in reasons:
                reasons.append(reason)

        def check(row, depth):
            nonlocal scanned
            key = row["entity_key"]
            if key not in checked:
                if len(checked) >= MAX_CHECKED_NODES:
                    truncate("node_limit")
                    return None
                proof = reader.verify(row, relation_budget=MAX_SCANNED_EDGES - scanned)
                if proof is None:
                    truncate("scan_limit")
                    return None
                ref, links, complete, coverage = proof
                scanned += len(links)
                node = ReferenceNode(key, row["game_id"], row["kind"], row["occurrence"],
                                     depth, ref, complete, coverage)
                checked[key] = (node, links)
            return checked[key]

        if len(roots) > 1:
            candidates = []
            for row in roots[:query.limit]:
                item = check(row, 0)
                if item:
                    candidates.append(item[0])
            if len(roots) > query.limit:
                truncate("candidate_limit")
            return ReferenceEnvelope(1, "partial", sid, context, query,
                candidates=tuple(candidates), truncated=bool(reasons), truncation_reasons=tuple(reasons),
                diagnostics=({"code": "REFERENCE_ROOT_AMBIGUOUS", "severity": "warning",
                              "message": "Select a definition using its entity_key."},))
        root = check(roots[0], 0)
        if root is None:
            return ReferenceEnvelope(1, "partial", sid, context, query,
                                     truncated=True, truncation_reasons=tuple(reasons))
        root_key = root[0].entity_key
        nodes, edges = {root_key: root[0]}, []
        queue, expanded = deque([(root_key, 0)]), set()
        stop = False
        while queue and not stop:
            key, depth = queue.popleft()
            if key in expanded:
                continue
            expanded.add(key)
            node, links = checked[key]
            partial |= not node.coverage_complete
            if depth >= query.depth:
                if links:
                    truncate("depth_limit")
                continue
            for link in links:
                if len(edges) >= query.limit:
                    truncate("result_limit")
                    stop = True
                    break
                targets = reader.candidates(query.kind, link["target_game_id"], 3)
                target_key, candidate_keys = None, ()
                status = "unresolved" if not targets else "ambiguous" if len(targets) > 1 else "resolved"
                if status == "resolved":
                    target = check(targets[0], depth + 1)
                    if target is None:
                        stop = True
                        break
                    target_key = target[0].entity_key
                    nodes.setdefault(target_key, target[0])
                    queue.append((target_key, depth + 1))
                elif status == "ambiguous":
                    for row in targets[:2]:
                        if check(row, depth + 1) is None:
                            stop = True
                            break
                    if stop:
                        break
                    candidate_keys = tuple(row["entity_key"] for row in targets[:2])
                stored_target, stored_status = link["stored_target"], link["stored_status"]
                if (stored_target is not None and stored_target != target_key
                        or stored_status != "unresolved" and stored_status != status):
                    raise SnapshotError("SOURCE_CHANGED", "Stored resolution differs from snapshot targets.")
                partial |= status != "resolved"
                edges.append(ReferenceEdge(key, link["occurrence"], link["relation_kind"],
                    link["target_game_id"], status, target_key, candidate_keys,
                    link["source_ref"], depth + 1, link["conditions_raw"], len(targets) > 2))
        cycles = _cycles(nodes, edges)
        return ReferenceEnvelope(1, "partial" if partial or reasons else "ok", sid, context, query,
            root_key, nodes=tuple(nodes.values()), edges=tuple(edges), cycles=cycles,
            truncated=bool(reasons), truncation_reasons=tuple(reasons))

    def pin(self, result: ReferenceEnvelope) -> ReferenceCard:
        if result.status not in {"ok", "partial"} or not result.root_entity_key or not result.snapshot_id:
            raise SnapshotError("QUERY_INVALID", "Choose one definition before pinning a card.")
        return ReferenceCard(result.snapshot_id, result.query.game_id, result.query.kind,
                             result.root_entity_key, result.query.depth, result.query.limit)

    def refresh(self, card: ReferenceCard) -> ReferenceEnvelope:
        return self.refs(ReferenceQuery(card.game_id, card.kind, card.snapshot_id,
                                        card.entity_key, card.depth, card.limit))

    def navigate(self, node: ReferenceNode, *, snapshot_id: str, depth=1, limit=20):
        """A clicked graph node starts another graph in the same pinned snapshot."""
        return self.refs(ReferenceQuery(node.game_id, node.kind, snapshot_id,
                                        node.entity_key, depth, limit))

    def source_text(self, source_ref: SourceRef, *, max_bytes=64 * 1024) -> str:
        """Plain text for a source panel, from verified cached bytes only."""
        if type(max_bytes) is not int or not 1 <= max_bytes <= 1024 * 1024:
            raise SnapshotError("QUERY_INVALID", "Invalid source panel byte budget.")
        if source_ref.byte_end - source_ref.byte_start > max_bytes:
            raise SnapshotError("LIMIT_EXCEEDED", "Source panel byte budget exceeded.")
        with self.repository.reference_reader(source_ref.snapshot_id) as reader:
            return reader.read(source_ref).decode("utf-8")
