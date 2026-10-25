"""Verified technology presentation data, separate from raw answer contracts."""

from __future__ import annotations

import re
from collections import OrderedDict
from dataclasses import asdict

from stellaris_supporter.answers import AnswerService
from stellaris_supporter.domain import SourceRef
from stellaris_supporter.localisation import resolve_localisation
from stellaris_supporter.parsing import BlockNode, PairNode, ScalarNode, parse_bytes
from stellaris_supporter.references import ReferenceQuery, ReferenceService
from stellaris_supporter.retrieval import Query
from stellaris_supporter.static_values import StaticCatalog
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.catalogue import FileCatalogue
from stellaris_supporter.storage.identity import storage_json

FIELD_LABELS = {
    "area": "분야",
    "tier": "기술 단계",
    "cost": "기본 연구 비용",
    "prerequisites": "선행 기술",
    "category": "분류",
    "description": "기술 설명",
}
AREAS = {"physics": "물리학", "society": "사회학", "engineering": "공학"}
STATE_TEXT = {
    "unresolved": "값 확인 필요",
    "ambiguous": "값 확인 필요",
    "unsupported": "원문 확인 필요",
    "incomplete": "자료 확인 필요",
    "partial": "일부 구문 · 원문 확인 필요",
    "missing_data": "변수 자료 없음",
    "missing": "값 확인 필요",
}


def list_literals(raw):
    if not isinstance(raw, str) or len(raw.encode()) > 512:
        return None
    parsed = parse_bytes(("x=" + raw).encode())
    if not parsed.ok or len(parsed.document.items) != 1:
        return None
    node = parsed.document.items[0]
    if (
        not isinstance(node, PairNode)
        or not isinstance(node.value, BlockNode)
        or not node.value.closed
    ):
        return None
    result = []
    for item in node.value.items:
        if not isinstance(item, ScalarNode) or item.token_kind not in {"identifier", "string"}:
            return None
        text = item.text
        if item.token_kind == "string":
            text = item.raw_bytes(("x=" + raw).encode()).decode()[1:-1]
        if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", text):
            return None
        result.append(text)
    return result


class CardInformation:
    def __init__(self, repo, search):
        self.repo, self.search = repo, search
        self.contexts = OrderedDict()
        self.names = OrderedDict()

    def close(self):
        for _, loc in self.contexts.values():
            if loc is not None:
                loc.close()
        self.contexts.clear()

    def context(self, sid):
        if sid not in self.contexts:
            self.contexts[sid] = (
                StaticCatalog(self.repo, sid),
                FileCatalogue.for_snapshot(self.repo, sid),
            )
            while len(self.contexts) > 2:
                _, (_, loc) = self.contexts.popitem(last=False)
                if loc is not None:
                    loc.close()
        self.contexts.move_to_end(sid)
        return self.contexts[sid]

    def name(self, sid, game_id, language):
        key = (sid, game_id, language)
        if key not in self.names:
            response = self.search.search(
                Query(game_id, snapshot_id=sid, language=language, limit=100)
            )
            if response.status == "error":
                raise SnapshotError(
                    response.diagnostics[0].code, "Prerequisite name lookup failed."
                )
            hits = [hit for hit in response.results if hit.game_id == game_id]
            self.names[key] = (
                {
                    "name": hits[0].display_name,
                    "sources": [
                        asdict(ref) for ref in (hits[0].localisation_source_ref,) if ref is not None
                    ]
                    + [
                        asdict(selection) for selection in hits[0].localisation_reference_selections
                    ],
                }
                if len(hits) == 1
                else {"name": game_id, "sources": []}
            )
            while len(self.names) > 1024:
                self.names.popitem(last=False)
        self.names.move_to_end(key)
        return self.names[key]

    def answer(self, payload, language):
        data = asdict(
            AnswerService(self.search, self.repo).answer(
                Query(
                    payload["game_id"],
                    snapshot_id=payload["snapshot_id"],
                    language=language,
                    limit=100,
                ),
                exact_game_id=True,
                entity_key=payload.get("entity_key"),
            )
        )
        if len(data["results"]) != 1 or data["status"] == "error":
            return data
        row = data["results"][0]
        sid = row["snapshot_id"]
        static, loc = self.context(sid)
        groups = {}
        for fact in row["facts"]:
            groups.setdefault(fact["field_name"], []).append(fact)

        def unique(name):
            if data["truncated"]:
                return None
            values = groups.get(name, [])
            return values[0] if len(values) == 1 and values[0]["operator"] == "=" else None

        fields = {}
        for name in ("area", "tier", "category"):
            fact = unique(name)
            value = None
            category_refs = []
            raw = fact["raw_expression"] if fact else None
            if raw is not None and name == "area":
                value = AREAS.get(raw)
            elif raw is not None and name == "tier" and re.fullmatch(r"[0-9]{1,8}", raw):
                value = str(int(raw)) + "단계"
            elif raw is not None and name == "category":
                categories = list_literals(raw)
                if categories is not None and loc is not None:
                    names = []
                    catalog = loc.catalogue(sid)
                    for category in categories:
                        catalog.complete = True
                        resolved = resolve_localisation(catalog, category, language)
                        if resolved.resolution != "resolved" or not catalog.complete:
                            names = []
                            break
                        names.append(resolved.display_value)
                        category_refs.extend(
                            asdict(r)
                            for r in ((resolved.source_ref,) if resolved.source_ref else ())
                            + resolved.reference_source_refs
                        )
                    value = ", ".join(names) if names else None
            fields[name] = {
                "value": value,
                "status": "resolved"
                if value is not None
                else "ambiguous"
                if len(groups.get(name, [])) > 1
                else "unresolved",
                "raw": raw,
                "sources": ([fact["value_source_ref"]] if fact and fact["value_source_ref"] else [])
                + category_refs,
            }
        fact = unique("cost")
        fields["cost"] = (
            static.cost(fact, row["definition_source_ref"])
            if fact
            else {
                "value": None,
                "status": "ambiguous" if len(groups.get("cost", [])) > 1 else "missing",
                "sources": [],
                "raw": None,
                "dependencies": [],
            }
        )
        graph = ReferenceService(self.repo).refs(
            ReferenceQuery(
                row["game_id"], snapshot_id=sid, entity_key=row["entity_key"], depth=1, limit=100
            )
        )
        if graph.status == "error":
            raise SnapshotError(graph.diagnostics[0]["code"], "Prerequisite proof failed.")
        prerequisites = []
        list_limited = False
        for edge in graph.edges:
            if edge.from_entity_key != row["entity_key"]:
                continue
            named = self.name(sid, edge.target_game_id, language)
            prerequisites.append(
                {
                    "game_id": edge.target_game_id,
                    "name": named["name"],
                    "entity_key": edge.target_entity_key,
                    "status": edge.status,
                    "source_ref": asdict(edge.source_ref),
                    "name_sources": named["sources"],
                }
            )
            if (
                len(storage_json(prerequisites, max_bytes=1024 * 1024, max_items=100000))
                > 32 * 1024
            ):
                prerequisites.pop()
                list_limited = True
                break
        description = {"value": None, "raw": None, "status": "unresolved", "sources": []}
        if loc is not None:
            catalog = loc.catalogue(sid)
            # Exact technology description key convention; no fuzzy-key association.
            resolved = resolve_localisation(catalog, row["game_id"] + "_desc", language)
            description = {
                "value": resolved.display_value
                if resolved.resolution == "resolved" and catalog.complete
                else None,
                "raw": resolved.display_value if resolved.source_ref else None,
                "status": resolved.resolution,
                "sources": [
                    asdict(r)
                    for r in ((resolved.source_ref,) if resolved.source_ref else ())
                    + resolved.reference_source_refs
                ],
            }
        if description["raw"] and len(description["raw"].encode("utf-8")) > 8192:
            description["raw"] = (
                description["raw"].encode("utf-8")[:8192].decode("utf-8", errors="ignore") + "…"
            )
            description["value"] = None
            description["status"] = "partial"
        fields["description"] = description
        flags = [
            label
            for name, label in (("is_rare", "희귀"), ("is_dangerous", "위험"))
            if unique(name) and unique(name)["raw_expression"] == "yes"
        ]
        view = {
            "identity": {
                "snapshot_id": sid,
                "entity_key": row["entity_key"],
                "game_id": row["game_id"],
                "language": language,
            },
            "name": row["display_name"],
            "fields": fields,
            "prerequisites": prerequisites,
            "prerequisites_complete": (
                not list_limited
                and not (set(graph.truncation_reasons) - {"depth_limit"})
                and not graph.abstained
                and any(
                    n.entity_key == row["entity_key"] and n.coverage_complete for n in graph.nodes
                )
            ),
            "flags": flags,
            "partial": data["context"]["snapshot_status"] == "partial",
            "definition_source_ref": row["definition_source_ref"],
            "fallback": row["fallback"],
        }

        # Preserve both the field proof and every additional numeric/localisation proof.
        def verify(value):
            if isinstance(value, dict):
                if {"snapshot_id", "byte_start", "file_sha256"} <= value.keys():
                    ref = SourceRef(**value)
                    if ref.snapshot_id != sid:
                        raise SnapshotError(
                            "SOURCE_CHANGED", "Card proof belongs to another snapshot."
                        )
                    self.repo.citation_bytes(ref)
                else:
                    for child in value.values():
                        verify(child)
            elif isinstance(value, (tuple, list)):
                for child in value:
                    verify(child)

        verify(view)
        storage_json(view, max_bytes=64 * 1024, max_items=100000)
        data["card_view"] = view
        return data


def field_text(view, name):
    field = view["fields"].get(name, {})
    return (
        field.get("value")
        if field.get("value") is not None
        else STATE_TEXT.get(field.get("status"), "원문 확인 필요")
    )


def readable_detail(view):
    lines = [view["name"], "기본 게임 파일 기준", ""]
    for name in ("area", "tier", "category", "cost"):
        lines.append(FIELD_LABELS[name] + "  " + field_text(view, name))
    lines.extend(["", "선행 기술 (전체 연구 조건·보유 상태 판정은 포함하지 않음)"])
    lines.extend(item["name"] for item in view["prerequisites"])
    if not view["prerequisites"]:
        lines.append("없음" if view["prerequisites_complete"] else "자료 확인 필요")
    if not view["prerequisites_complete"]:
        lines.append("일부 목록만 표시합니다.")
    if view["fields"]["description"].get("value"):
        lines.extend(["", "기술 설명", view["fields"]["description"]["value"]])
    if view["partial"]:
        lines.extend(["", "일부 자료를 기준으로 표시합니다."])
    return "\n".join(lines)
