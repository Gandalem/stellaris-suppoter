"""Snapshot-pinned weapon search, grouping, static values and field-level provenance."""

from __future__ import annotations

import json
import re
from collections import OrderedDict
from decimal import Decimal, localcontext

from stellaris_supporter.domain import SourceRef
from stellaris_supporter.localisation import resolve_localisation
from stellaris_supporter.retrieval import normalize_search
from stellaris_supporter.static_values import StaticCatalog
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.catalogue import FileCatalogue
from stellaris_supporter.storage.identity import storage_json
from stellaris_supporter.weapon_data import (
    ID,
    KIND,
    TABLES,
    VERSION,
    WeaponContext,
    fields,
    literal,
    references,
    single,
)

LABELS = {
    "damage": "기본 피해",
    "range": "최대 사거리",
    "min_range": "최소 사거리",
    "accuracy": "기본 명중률",
    "tracking": "기본 추적률",
    "power": "전력 영향",
    "hull_damage": "선체 피해",
    "armor_damage": "장갑 피해",
    "shield_damage": "보호막 피해",
    "armor_penetration": "장갑 관통",
    "shield_penetration": "보호막 관통",
    "cooldown": "발사 간격 원문",
    "min_windup": "최소 준비 시간 원문",
    "max_windup": "최대 준비 시간 원문",
}
STATES = {
    "missing": "정의 없음",
    "ambiguous": "값 확인 필요",
    "unsupported": "원문 확인 필요",
    "incomplete": "자료 확인 필요",
    "missing_data": "자료 없음",
    "policy_required": "결합 규칙 확인 필요",
}
SIZES = {
    "point_defence": "거점 방어",
    "small": "소형",
    "medium": "중형",
    "large": "대형",
    "extra_large": "초대형",
    "titanic": "타이탄",
    "torpedo": "어뢰",
    "planet_killer": "행성 파괴",
    "aux": "보조",
}
TAGS = {
    "weapon_type_energy": "에너지",
    "weapon_type_kinetic": "실탄",
    "weapon_type_explosive": "폭발",
    "weapon_type_point_defense": "거점 방어",
}
CONDITIONS = {
    "potential": "설계 목록 표시 조건",
    "possible": "부품 호환 조건",
    "slot_restriction": "슬롯 제한",
    "size_restriction": "함선 크기 제한",
    "class_restriction": "함선 종류 제한",
    "show_tech_unlock_if": "기술 화면 표시 조건",
    "allow": "사용 조건",
    "restriction": "추가 제한",
}
RESOURCE_CONTROLS = frozenset(
    {
        "mult",
        "multiplier",
        "trigger",
        "inline_script",
        "if",
        "else_if",
        "else",
        "modifier",
        "potential",
    }
)
RESOURCE_RULE = "weapon-resource-scope-2"

NUMBER = re.compile(r"[+-]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)\Z")


def decimal(raw, signed=False):
    if not isinstance(raw, str) or len(raw) > 64 or not NUMBER.fullmatch(raw):
        return None
    value = Decimal(raw)
    return value if value.is_finite() and (signed or value >= 0) else None


def display_number(value):
    return format(value.copy_abs() if value.is_zero() else value, ",f")


def item_text(value):
    return (
        value.get("value")
        if value.get("value") is not None
        else STATES.get(value.get("status"), "원문 확인 필요")
    )


class WeaponService:
    def __init__(self, repo, card_information):
        self.repo, self.card_information = repo, card_information
        self.contexts = OrderedDict()
        self.names = OrderedDict()

    def close(self):
        for _, loc, _ in self.contexts.values():
            if loc is not None:
                loc.close()
        self.contexts.clear()
        self.names.clear()

    def context(self, sid):
        if not isinstance(sid, str) or not re.fullmatch(r"[a-f0-9]{64}", sid):
            raise SnapshotError("QUERY_INVALID", "A snapshot is required for weapon queries.")
        if sid not in self.contexts:
            context = WeaponContext(self.repo, sid)
            self.contexts[sid] = (
                context,
                FileCatalogue.for_snapshot(self.repo, sid),
                StaticCatalog(self.repo, sid),
            )
            while len(self.contexts) > 2:
                _, (_, loc, _) = self.contexts.popitem(last=False)
                if loc is not None:
                    loc.close()
        self.contexts.move_to_end(sid)
        return self.contexts[sid]

    def name(self, sid, key, language):
        if language not in {"korean", "english"}:
            raise SnapshotError("QUERY_INVALID", "Unsupported weapon language.")
        lookup = (sid, key, language)
        if lookup not in self.names:
            _, loc, _ = self.context(sid)
            value = {"name": key, "sources": [], "fallback": "id"}
            if loc is not None:
                catalog = loc.catalogue(sid)
                result = resolve_localisation(catalog, key, language)
                if result.source_ref:
                    refs = [result.source_ref, *result.reference_source_refs]
                    value = {
                        "name": result.display_value
                        if len(result.display_value.encode()) <= 2048
                        else key,
                        "sources": [r.to_dict() for r in refs],
                        "fallback": result.fallback,
                    }
            self.names[lookup] = value
            while len(self.names) > 4096:
                self.names.popitem(last=False)
        self.names.move_to_end(lookup)
        return self.names[lookup]

    def family(self, ctx, item, language):
        group_id = item["group_id"]
        candidates = ctx.groups.get(group_id, [])
        if len(candidates) != 1:
            return None
        group = candidates[0]
        named = self.name(ctx.sid, group_id, language)
        return {
            "id": group_id,
            "name": named["name"],
            "sources": [
                ctx.ref(item["file_key"], item["group_span"]),
                ctx.ref(group["file_key"], group["span"]),
                *named["sources"],
            ],
            "space_fauna": group["space_fauna"],
        }

    def summary(self, ctx, item, language):
        named = self.name(ctx.sid, item["id"], language)
        size = item["size"]
        family = self.family(ctx, item, language)
        conditions = item["conditions"]
        special = item["special"]
        special_sources = []
        rows = ctx.numeric_rows.get(item["id"], [])
        if len(rows) == 1 and all(table["complete"] for table in ctx.tables.values()):
            key, table, row = rows[0]
            columns = table["header"]["values"]
            if TABLES[key[2]] == "standard" and "size_damage_factor" in columns:
                index = columns.index("size_damage_factor")
                factor = decimal(row["values"][index])
                if factor is not None and factor > 0:
                    special = True
                    special_sources.append(ctx.ref(key, row["cells"][index]))
        return {
            "entity_key": item["entity_key"],
            "game_id": item["id"],
            "snapshot_id": ctx.sid,
            "kind": KIND,
            "name": named["name"],
            "duplicate": len(ctx.by_id.get(item["id"], [])) > 1,
            "size": size,
            "size_label": SIZES.get(size, size or "크기 원문 확인"),
            "family": family,
            "conditions": conditions,
            "special": special,
            "special_sources": special_sources,
            "source_ref": ctx.ref(item["file_key"], item["span"]),
            "name_sources": named["sources"],
        }

    def search(self, p, language):
        sid = p["snapshot_id"]
        ctx, _, _ = self.context(sid)
        text = p.get("text", "")
        limit, offset = p.get("limit", 20), p.get("offset", 0)
        if (
            not isinstance(text, str)
            or len(text) > 512
            or type(limit) is not int
            or not 1 <= limit <= 100
            or type(offset) is not int
            or offset < 0
            or offset > 100000
        ):
            raise SnapshotError("QUERY_INVALID", "Weapon query budget invalid.")
        for key in ("technology_id", "group_id"):
            if p.get(key) is not None and (not isinstance(p[key], str) or not ID.fullmatch(p[key])):
                raise SnapshotError("QUERY_INVALID", "Invalid weapon identifier filter.")
        size = p.get("size", "")
        tag = p.get("tag", "")
        if size and size not in SIZES or tag and tag not in TAGS:
            raise SnapshotError("QUERY_INVALID", "Weapon filter invalid.")
        query = normalize_search(text)
        matches = []
        complete = ctx.complete
        if p.get("technology_id"):
            with self.repo._connection(read_only=True) as conn:
                tech_count = len(
                    conn.execute(
                        "SELECT entity_key FROM entities WHERE snapshot_id=? AND kind='technology' AND game_id=? LIMIT 2",
                        (sid, p["technology_id"]),
                    ).fetchall()
                )
            complete &= tech_count == 1
        for item in ctx.definitions:
            requirements, coverage = item["requirements"], item["links_complete"]
            if p.get("technology_id"):
                complete &= coverage
                if p["technology_id"] not in [v[0] for v in requirements]:
                    continue
            if size and item["size"] != size:
                continue
            if tag:
                complete &= item["tags_complete"]
                if tag not in item["tags"]:
                    continue
            value = self.summary(ctx, item, language)
            if p.get("group_id") and (
                not value["family"] or value["family"]["id"] != p["group_id"]
            ):
                continue
            if (
                query
                and query not in normalize_search(item["id"])
                and query not in normalize_search(value["name"])
            ):
                continue
            matches.append(value)
        groups = {}
        for value in matches:
            key = (
                ("family", value["family"]["id"])
                if p.get("grouped", True) and value["family"]
                else ("weapon", value["entity_key"])
            )
            if key not in groups:
                if key[0] == "family":
                    groups[key] = {
                        "type": "family",
                        "group_id": key[1],
                        "name": value["family"]["name"],
                        "count": 0,
                        "conditions": False,
                        "special": False,
                        "space_fauna": value["family"]["space_fauna"],
                        "sources": value["family"]["sources"],
                    }
                else:
                    groups[key] = {"type": "weapon", **value}
            if key[0] == "family":
                groups[key]["count"] += 1
                groups[key]["conditions"] |= value["conditions"]
                groups[key]["special"] |= value["special"]
        order = {key: index for index, key in enumerate(SIZES)}
        items = sorted(
            groups.values(),
            key=lambda v: (
                order.get(v.get("size"), 99) if p.get("group_id") else 0,
                normalize_search(v["name"]),
                order.get(v.get("size"), 99),
                v.get("game_id", v.get("group_id", "")),
                v.get("entity_key", ""),
            ),
        )
        selected = items[offset : offset + limit]
        self.verify_sources(selected, sid)
        response = {
            "status": "partial" if not complete else "ok",
            "snapshot_id": sid,
            "available": ctx.available,
            "items": selected,
            "total": len(items) if complete else None,
            "truncated": offset + limit < len(items),
            "offset": offset,
            "limit": limit,
            "query": dict(p),
            "coverage_complete": complete,
        }
        while len(storage_json(response, max_bytes=1024 * 1024, max_items=100000)) > 60 * 1024:
            response["items"].pop()
            response["truncated"] = True
        return response

    def verify_sources(self, value, sid):
        if isinstance(value, dict):
            if {"snapshot_id", "byte_start", "file_sha256"} <= value.keys():
                ref = SourceRef(**value)
                if ref.snapshot_id != sid:
                    raise SnapshotError("SOURCE_CHANGED", "Mixed weapon proof snapshot.")
                self.repo.citation_bytes(ref)
            else:
                for child in value.values():
                    self.verify_sources(child, sid)
        elif isinstance(value, (list, tuple)):
            for child in value:
                self.verify_sources(child, sid)

    def rule_sources(self, ctx, marker):
        refs = []
        for key, source in ctx.sources.items():
            if not key[2].endswith("000_documentation.txt"):
                continue
            raw = self.repo.cache.read(source.file_sha256, source.size)
            offset = 0
            for line_no, line in enumerate(raw.splitlines(keepends=True), 1):
                if marker.encode() in line:
                    refs.append(ctx.ref(key, [offset, offset + len(line), line_no, line_no]))
                    break
                offset += len(line)
        return refs

    def txt_field(self, node, name):
        if name in {"min_damage", "max_damage"}:
            damage = single(node, "damage")
            if damage and damage.get("kind") == "scalar":
                return damage
            return single(damage or {}, "min" if name == "min_damage" else "max")
        if name == "range":
            aliases = fields(node, "range") + fields(node, "max_range")
            return aliases[0] if len(aliases) == 1 and aliases[0].get("op") == "=" else None
        return single(node, name)

    def number(self, ctx, item, name):
        node = ctx.node(item)
        field = self.txt_field(node, name)
        result = {
            "value": None,
            "status": "missing",
            "raw": None,
            "sources": [],
            "origin": None,
            "number": None,
        }
        if fields(node, "inline_script"):
            return {
                **result,
                "status": "incomplete",
                "sources": [ctx.ref(item["file_key"], item["span"])],
                "reason": "정의에 펼치지 않은 구문이 있습니다.",
            }
        candidates = ctx.numeric_rows.get(item["id"], [])
        tables_complete = bool(ctx.tables) and all(t["complete"] for t in ctx.tables.values())
        if len(candidates) > 1:
            return {
                **result,
                "status": "ambiguous",
                "reason": "같은 부품 ID의 수치 행이 여러 개입니다.",
                "sources": [ctx.ref(k, r["span"]) for k, _, r in candidates[:16]],
            }
        if not tables_complete and name not in {"min_range"}:
            return {
                **result,
                "status": "incomplete",
                "reason": "수치 표의 전체 범위를 확인하지 못했습니다.",
            }
        if candidates:
            key, table, row = candidates[0]
            header = table["header"]
            if name in header["values"]:
                index = header["values"].index(name)
                raw = row["values"][index]
                cell_span = row["cells"][index]
                refs = [
                    ctx.ref(key, cell_span if cell_span[0] < cell_span[1] else row["span"]),
                    ctx.ref(key, header["cells"][index]),
                    ctx.ref(key, row["cells"][0]),
                ]
                if field:
                    refs.append(ctx.ref(item["file_key"], field["value_span"] or field["span"]))
                result.update(
                    raw=raw,
                    sources=refs,
                    origin=TABLES[key[2]],
                    cell_span=cell_span,
                    proof_labels=[name + " 값", name + " 열 이름", "부품 key"]
                    + (["TXT 선언"] if field else []),
                    column=name,
                )
                # Mutation table cells remain declared values until their own merge policy is registered.
                if TABLES[key[2]] != "standard":
                    return {
                        **result,
                        "status": "policy_required",
                        "declared": raw,
                        "reason": "변이 표의 선언값입니다. 적용 결과로 합성하지 않습니다.",
                    }
                value = decimal(raw, signed=name == "power")
                if value is None:
                    return {**result, "status": "unsupported" if raw else "missing"}
                return {
                    **result,
                    "status": "resolved",
                    "value": display_number(value),
                    "number": str(value),
                }
        if field is None:
            names = (
                ["damage"]
                if name in {"min_damage", "max_damage"}
                else ["range", "max_range"]
                if name == "range"
                else [name]
            )
            ambiguous = (
                any(len(fields(node, key)) > 1 for key in names)
                or name == "range"
                and sum(len(fields(node, key)) for key in names) > 1
            )
            return {**result, "status": "ambiguous" if ambiguous else "missing"}
        return self.resolve_txt(ctx, item, field, signed=name == "power")

    def resolve_txt(self, ctx, item, field, signed=False):
        raw = field.get("raw")
        sources = [ctx.ref(item["file_key"], field["value_span"] or field["span"])]
        result = {
            "value": None,
            "status": "unsupported",
            "raw": raw,
            "sources": sources,
            "origin": "TXT",
            "number": None,
        }
        if field.get("op") != "=" or field.get("kind") != "scalar":
            return result
        value = decimal(raw, signed)
        if value is not None:
            return {
                **result,
                "value": display_number(value),
                "number": str(value),
                "status": "resolved",
            }
        if raw and raw.startswith("@"):
            _, _, static = self.context(ctx.sid)
            fact = {"operator": "=", "raw_expression": raw, "value_source_ref": sources[0]}
            resolved = static.cost(
                fact, ctx.ref(item["file_key"], item["span"]), allow_negative=signed
            )
            result.update(resolved)
            if result.get("value") is not None:
                result["number"] = str(Decimal(result["value"].replace(",", "")))
            return result
        return result

    def resource_values(self, ctx, item, language):
        """Keep economic control syntax separate from resource declarations."""
        roots = fields(ctx.node(item), "resources")
        scopes = {section: [] for section in ("cost", "upkeep")}

        def flag(section, code):
            if code not in scopes[section]:
                scopes[section].append(code)

        if len(roots) > 1:
            return [], False, {section: ["ambiguous"] for section in scopes}
        if not roots:
            return [], True, scopes
        root = roots[0]
        inherited = [f["key"] for f in root.get("items", ()) if f.get("key") in RESOURCE_CONTROLS]
        if any(
            f.get("key") not in RESOURCE_CONTROLS | {"category", "cost", "upkeep"}
            for f in root.get("items", ())
        ):
            inherited.append("incomplete")
        if root.get("kind") != "block" or root.get("op") != "=" or not root.get("closed"):
            inherited.append("incomplete")
        result = []
        complete = True
        for section in scopes:
            blocks = fields(root, section)
            if len(blocks) > 1:
                flag(section, "ambiguous")
            for key in inherited:
                flag(section, key)
            remaining = 100
            for block in blocks:
                if (
                    block.get("kind") != "block"
                    or block.get("op") != "="
                    or not block.get("closed")
                ):
                    flag(section, "incomplete")
                controls = [f for f in block.get("items", ()) if f.get("key") in RESOURCE_CONTROLS]
                for control in controls:
                    flag(section, control["key"])
                # Each cost/upkeep block has its own scope; a sibling condition must not alter a direct value.
                block_flags = set(inherited) | {f["key"] for f in controls}
                if any(
                    not f.get("key") or not ID.fullmatch(f["key"]) for f in block.get("items", ())
                ):
                    flag(section, "incomplete")
                    block_flags.add("incomplete")
                if not block.get("closed") or block.get("op") != "=":
                    block_flags.add("incomplete")
                items = block.get("items", ())
                if len(items) > remaining:
                    flag(section, "truncated")
                for field in items[:remaining]:
                    key = field.get("key")
                    if key in RESOURCE_CONTROLS:
                        continue
                    if not key or not ID.fullmatch(key):
                        flag(section, "incomplete")
                        continue
                    duplicates = fields(block, key)
                    value = self.resolve_txt(ctx, item, field)
                    if len(duplicates) > 1 or len(blocks) > 1:
                        value.update(
                            value=None,
                            number=None,
                            status="ambiguous",
                            reason="자원 선언이 중복돼 있습니다.",
                        )
                    elif block_flags:
                        value.update(
                            value=None,
                            number=None,
                            status="incomplete",
                            reason="자원에 조건·배율 또는 펼치지 않은 구문이 있습니다.",
                        )
                    if block_flags or len(blocks) > 1:
                        scope_ref = ctx.ref(item["file_key"], root["span"])
                        if scope_ref not in value["sources"]:
                            value["sources"].append(scope_ref)
                    named = self.name(ctx.sid, key, language)
                    result.append(
                        {
                            "section": section,
                            "resource_id": key,
                            "name": named["name"],
                            **value,
                            "name_sources": named["sources"],
                        }
                    )
                remaining = max(0, remaining - len(items))
                if not remaining:
                    if block is not blocks[-1]:
                        flag(section, "truncated")
                    break
            complete &= not scopes[section]
        return result, bool(complete), scopes

    def verify_links(self, ctx, item):
        node = ctx.node(item)
        requirements, complete = references(node, "prerequisites")
        links = [
            (target, "weapon_requires_technology", position) for target, position in requirements
        ]
        field = single(node, "upgrades_to")
        if literal(field) and ID.fullmatch(literal(field)):
            links.append((literal(field), "weapon_upgrade", field["value_span"]))
        result = []
        with self.repo._connection(read_only=True) as conn:
            rows = conn.execute(
                "SELECT * FROM relations WHERE snapshot_id=? AND from_entity_key=? ORDER BY occurrence",
                (ctx.sid, item["entity_key"]),
            ).fetchall()
            if len(rows) != len(links):
                raise SnapshotError("SOURCE_CHANGED", "Weapon links differ from original.")
            for ordinal, ((game_id, kind, position), row) in enumerate(
                zip(links, rows, strict=True), 1
            ):
                proof = ctx.ref(item["file_key"], position)
                target_kind = "technology" if kind == "weapon_requires_technology" else KIND
                targets = [
                    r[0]
                    for r in conn.execute(
                        "SELECT entity_key FROM entities WHERE snapshot_id=? AND kind=? AND game_id=? LIMIT 2",
                        (ctx.sid, target_kind, game_id),
                    )
                ]
                status = (
                    "resolved" if len(targets) == 1 else "ambiguous" if targets else "unresolved"
                )
                target = targets[0] if len(targets) == 1 else None
                if (
                    row["occurrence"] != ordinal
                    or row["relation_kind"] != kind
                    or row["target_game_id"] != game_id
                    or row["target_entity_key"] != target
                    or row["status"] != status
                    or json.loads(row["source_ref_json"]) != proof
                    or row["conditions_raw"] is not None
                ):
                    raise SnapshotError("SOURCE_CHANGED", "Weapon relation proof changed.")
                result.append(
                    {
                        "game_id": game_id,
                        "entity_key": target,
                        "kind": target_kind,
                        "status": status,
                        "source_ref": proof,
                    }
                )
        return result, complete

    def detail(self, p, language):
        sid = p["snapshot_id"]
        if p.get("entity_key") is not None and (
            not isinstance(p["entity_key"], str)
            or not re.fullmatch(r"[a-f0-9]{64}", p["entity_key"])
        ):
            raise SnapshotError("QUERY_INVALID", "Invalid weapon entity key.")
        ctx, loc, _ = self.context(sid)
        if not ctx.available:
            return {"status": "missing_data", "available": False, "snapshot_id": sid}
        candidates = (
            [ctx.by_entity[p["entity_key"]]]
            if p.get("entity_key") in ctx.by_entity
            else []
            if p.get("entity_key")
            else ctx.by_id.get(p.get("game_id"), [])
        )
        if len(candidates) != 1:
            return {
                "status": "ambiguous" if candidates else "not_found",
                "snapshot_id": sid,
                "items": [self.summary(ctx, v, language) for v in candidates[:100]],
            }
        item = candidates[0]
        node = ctx.node(item)
        values = {
            name: self.number(ctx, item, name)
            for name in [
                "min_damage",
                "max_damage",
                "range",
                "min_range",
                "accuracy",
                "tracking",
                "power",
                "hull_damage",
                "armor_damage",
                "shield_damage",
                "armor_penetration",
                "shield_penetration",
                "cooldown",
                "min_windup",
                "max_windup",
            ]
        }
        low, high = values.pop("min_damage"), values.pop("max_damage")
        damage = {
            "value": None,
            "status": "unsupported",
            "raw": [low["raw"], high["raw"]],
            "sources": low["sources"] + high["sources"],
            "proof_labels": low.get("proof_labels", ["최소 피해 원문"] * len(low["sources"]))
            + high.get("proof_labels", ["최대 피해 원문"] * len(high["sources"])),
        }
        if (
            low["number"] is not None
            and high["number"] is not None
            and Decimal(low["number"]) <= Decimal(high["number"])
        ):
            damage.update(
                value=low["value"]
                if low["number"] == high["number"]
                else low["value"] + "–" + high["value"],
                status="resolved",
            )
        elif low["number"] is None or high["number"] is None:
            damage["status"] = low["status"] if low["number"] is None else high["status"]
        values = {"damage": damage, **values}
        if (
            values["range"]["number"] is not None
            and values["min_range"]["number"] is not None
            and Decimal(values["min_range"]["number"]) > Decimal(values["range"]["number"])
        ):
            for key in ("range", "min_range"):
                values[key].update(
                    value=None, status="unsupported", reason="최소 사거리가 최대 사거리보다 큽니다."
                )
        for key in ("accuracy", "tracking", "armor_penetration", "shield_penetration"):
            value = values[key]
            if value["number"] is not None:
                with localcontext() as decimal_context:
                    decimal_context.prec = 80
                    value["value"] = display_number(Decimal(value["number"]) * 100) + "%"
                    value["unit_rule"] = "비율 × 100 → 백분율"
        for key in ("hull_damage", "armor_damage", "shield_damage"):
            if values[key]["value"] is not None:
                values[key]["value"] = "×" + values[key]["value"]
        power = values["power"]
        power_rules = self.rule_sources(ctx, "-X costs power")
        if power["number"] is not None and power_rules:
            number = Decimal(power["number"])
            power["label"] = (
                "소비 전력" if number < 0 else "공급 전력" if number > 0 else "전력 변화"
            )
            power["value"] = display_number(number.copy_abs())
            power["proof_labels"] = power.get(
                "proof_labels", ["전력 원문"] * len(power["sources"])
            ) + ["소비/공급 부호 규칙"] * len(power_rules)
            power["sources"] += power_rules
        resources, resources_complete, resource_scopes = self.resource_values(ctx, item, language)
        conditions = [
            {"name": label, "field": key, "source_ref": ctx.ref(item["file_key"], field["span"])}
            for key, label in CONDITIONS.items()
            for field in fields(node, key)
        ]
        effects = [
            {"name": key, "source_ref": ctx.ref(item["file_key"], field["span"])}
            for key in (
                "on_hit",
                "chain_damage",
                "collateral_damage",
                "scripted_action",
                "size_damage_factor",
            )
            for field in fields(node, key)
        ]
        size_factor = self.number(ctx, item, "size_damage_factor")
        if size_factor.get("number") is not None and Decimal(size_factor["number"]) != 0:
            effects.append({"name": "대상 크기 의존 피해", "source_ref": size_factor["sources"][0]})
        links, links_complete = self.verify_links(ctx, item)
        all_links = links
        section = p.get("section")
        offset = p.get("offset", 0)
        limit = p.get("limit", 20)
        if (
            type(offset) is not int
            or offset < 0
            or offset > 100000
            or type(limit) is not int
            or not 1 <= limit <= 100
        ):
            raise SnapshotError("QUERY_INVALID", "Weapon detail page budget invalid.")
        links = links[offset : offset + limit] if section == "links" else links[:20]
        for link in links:
            if link["kind"] == "technology":
                named = self.card_information.name(sid, link["game_id"], language)
            else:
                named = self.name(sid, link["game_id"], language)
            link["name"] = named["name"]
            link["name_sources"] = named["sources"]
        description = None
        description_sources = []
        description_key = literal(single(node, "description"))
        if loc is not None and description_key and ID.fullmatch(description_key):
            catalog = loc.catalogue(sid)
            resolved = resolve_localisation(catalog, description_key, language)
            if resolved.resolution == "resolved" and resolved.source_ref:
                description = resolved.display_value[:2048]
                description_sources = [
                    ctx.ref(item["file_key"], single(node, "description")["value_span"]),
                    *[r.to_dict() for r in [resolved.source_ref, *resolved.reference_source_refs]],
                ]
        view = {
            "status": "partial" if not ctx.complete or not node["complete"] else "ok",
            "available": True,
            "identity": {
                "snapshot_id": sid,
                "entity_key": item["entity_key"],
                "game_id": item["id"],
                "kind": KIND,
                "language": language,
            },
            "summary": self.summary(ctx, item, language),
            "fields": values,
            "resources": resources,
            "resources_complete": resources_complete,
            "resource_scopes": resource_scopes,
            "resource_policy": RESOURCE_RULE,
            "conditions": conditions[:20],
            "conditions_more": len(conditions) > 20,
            "effects": effects[:20],
            "effects_more": len(effects) > 20,
            "links": links,
            "links_complete": links_complete,
            "links_more": len(all_links) > len(links),
            "description": description,
            "description_sources": description_sources,
            "diagnostics": node.get("diagnostics", []),
            "source_ref": ctx.ref(item["file_key"], item["span"]),
            "policy": VERSION,
        }
        if section == "field":
            field_key = p.get("field")
            if field_key not in values:
                raise SnapshotError("QUERY_INVALID", "Unknown weapon field.")
            value = values[field_key]
            sources = value["sources"]
            view = {
                "status": view["status"],
                "identity": view["identity"],
                "section": "field",
                "field": field_key,
                "items": sources[offset : offset + limit],
                "labels": value.get("proof_labels", ["원문"] * len(sources))[
                    offset : offset + limit
                ],
                "total": len(sources),
                "offset": offset,
                "limit": limit,
                "more": offset + limit < len(sources),
            }
        elif section:
            sections = {
                "links": links,
                "resources": resources,
                "conditions": conditions,
                "effects": effects,
            }
            if section not in sections:
                raise SnapshotError("QUERY_INVALID", "Unknown weapon section.")
            entries = (
                sections[section]
                if section == "links"
                else sections[section][offset : offset + limit]
            )
            total = len(all_links) if section == "links" else len(sections[section])
            view = {
                "status": view["status"],
                "identity": view["identity"],
                "section": section,
                "items": entries,
                "total": total,
                "offset": offset,
                "limit": limit,
                "more": offset + len(entries) < total,
            }
        else:
            view["resources"] = resources[:20]
            view["resources_more"] = len(resources) > 20
        if not section:
            for field_key, value in values.items():
                value["field_key"] = field_key
                if len(value["sources"]) > 8:
                    value["sources"] = value["sources"][:8]
                    value["proof_more"] = True
        self.verify_sources(view, sid)
        # Long sections travel as individually addressed proofs, never injected source text.
        # Reduce only bounded sections; never discard valid core information for a long list.
        while len(storage_json(view, max_bytes=1024 * 1024, max_items=100000)) > 60 * 1024:
            if section:
                if not view["items"]:
                    raise SnapshotError("LIMIT_EXCEEDED", "One proof exceeds the view budget.")
                view["items"].pop()
                view["more"] = True
            else:
                key = next(
                    (key for key in ("links", "resources", "conditions", "effects") if view[key]),
                    None,
                )
                if key is None:
                    large = next(
                        (value for value in view["fields"].values() if len(value["sources"]) > 1),
                        None,
                    )
                    if large is None:
                        raise SnapshotError(
                            "LIMIT_EXCEEDED", "Core weapon proof exceeds the view budget."
                        )
                    large["sources"].pop()
                    large["proof_more"] = True
                else:
                    view[key].pop()
                    view[key + "_more"] = True
        storage_json(view, max_bytes=64 * 1024, max_items=100000)
        return view
