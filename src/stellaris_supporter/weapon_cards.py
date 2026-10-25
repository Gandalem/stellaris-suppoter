"""Display projection of verified weapon detail; no parsing or combat calculation."""

from __future__ import annotations

from .weapons import LABELS, item_text

FIELDS = {
    "damage": "기본 피해",
    "range": "사거리",
    "accuracy": "명중률",
    "tracking": "추적률",
    "power": "전력",
    "cost": "제작 비용",
    "hull_damage": "선체 피해",
    "armor_damage": "장갑 피해",
    "shield_damage": "보호막 피해",
    "armor_penetration": "장갑 관통",
    "shield_penetration": "보호막 관통",
    "upkeep": "유지비",
    "prerequisites": "요구 기술",
}
DEFAULT_FIELDS = ["damage", "range", "accuracy", "tracking", "power", "cost"]


def project(detail):
    if not detail.get("identity") or not detail.get("available"):
        return None
    summary = detail["summary"]
    return {
        "identity": dict(detail["identity"]),
        "name": summary["name"],
        "size": summary["size_label"],
        "family": (summary.get("family") or {}).get("name", ""),
        "fields": {
            key: {
                "text": item_text(value),
                "status": value.get("status"),
                "label": value.get("label", LABELS.get(key, key)),
            }
            for key, value in detail["fields"].items()
        },
        "resources": [
            {
                "section": r["section"],
                "name": r["name"],
                "text": item_text(r),
                "status": r.get("status"),
            }
            for r in detail.get("resources", [])
        ],
        "resources_more": detail.get("resources_more", False),
        "resources_complete": detail.get("resources_complete", False),
        "resource_scopes": detail.get("resource_scopes", {}),
        "links": [
            {k: row.get(k) for k in ("game_id", "entity_key", "name", "kind", "status")}
            for row in detail.get("links", [])
        ],
        "links_more": detail.get("links_more", False),
        "links_complete": detail.get("links_complete", False),
        "conditions": bool(
            summary.get("conditions") or detail.get("conditions") or detail.get("conditions_more")
        ),
        "effects": bool(
            summary.get("special") or detail.get("effects") or detail.get("effects_more")
        ),
        "partial": detail.get("status") == "partial",
    }


POLICY_NOTICE = "변이 수치 · 적용 규칙 확인 필요"


def policy_keys(view, selected):
    return {
        key
        for key in selected
        if any(
            view["fields"].get(k, {}).get("status") == "policy_required"
            for k in (("range", "min_range") if key == "range" else (key,))
        )
    }


def numeric_detail_lines(detail):
    result = []
    noted = False
    for key, value in detail["fields"].items():
        if value.get("status") == "policy_required":
            if not noted:
                result.append(POLICY_NOTICE)
                noted = True
        else:
            result.append(value.get("label", LABELS[key]) + "  " + item_text(value))
    return result


def field_lines(view, key):
    fields = view["fields"]
    if key == "range":
        values = []
        minimum = fields.get("min_range", {})
        if minimum and minimum.get("status") not in {"missing", "policy_required"}:
            values.append("최소 사거리  " + minimum.get("text", "자료 없음"))
        maximum = fields.get("range", {})
        if maximum.get("status") != "policy_required":
            values.append("최대 사거리  " + maximum.get("text", "자료 없음"))
        return values
    if key in {"cost", "upkeep"}:
        section = "cost" if key == "cost" else "upkeep"
        resources = [r for r in view["resources"] if r["section"] == section]
        values = [
            FIELDS[key] + " · " + r["name"] + "  " + r["text"]
            for r in resources
            if r.get("status") == "resolved"
        ]
        unknown = [r for r in resources if r.get("status") != "resolved"]
        flags = view.get("resource_scopes", {}).get(section, [])
        if flags or unknown:
            state = (
                "중복 선언 확인 필요"
                if "ambiguous" in flags or any(r.get("status") == "ambiguous" for r in unknown)
                else "동적 계산 필요"
                if flags
                else "자료 확인 필요"
            )
            values.append(FIELDS[key] + " · " + state)
        if not values:
            values = [
                FIELDS[key]
                + "  "
                + (
                    "자료 확인 필요"
                    if view["resources_more"] or not view["resources_complete"]
                    else "정의 없음"
                )
            ]
        if view["resources_more"]:
            values.append("추가 자원 항목 있음")
        return values
    if key == "prerequisites":
        values = [
            "요구 기술 · " + (v["name"] or v["game_id"])
            for v in view["links"]
            if v["kind"] == "technology"
        ]
        if not values:
            values = ["요구 기술  " + ("명시 없음" if view["links_complete"] else "자료 확인 필요")]
        if view["links_more"]:
            values.append("추가 연결 있음")
        return values
    value = fields.get(key, {})
    if value.get("status") == "policy_required":
        return []
    return [value.get("label", FIELDS.get(key, key)) + "  " + value.get("text", "자료 없음")]


def summary_text(view, selected):
    lines = [view["name"], view["size"]]
    if policy_keys(view, selected):
        lines.append(POLICY_NOTICE)
    for key in dict.fromkeys(selected):
        lines.extend(field_lines(view, key))
    if view["conditions"]:
        lines.append("추가 조건")
    if view["effects"]:
        lines.append("특수 작용")
    lines.append("기본 게임 파일 기준" + (" · 일부 자료" if view["partial"] else ""))
    return "\n".join(lines)


def preview_text(detail, selected):
    view = project(detail)
    if view is None:
        return None
    keys = list(dict.fromkeys([*DEFAULT_FIELDS, *selected]))
    lines = [summary_text(view, keys)]
    for row in view["links"]:
        label = "요구 기술" if row["kind"] == "technology" else "명시된 상위 부품"
        lines.append(label + " · " + (row["name"] or row["game_id"]))
    if view["links_more"] or not view["links_complete"]:
        lines.append("연결 목록 일부")
    return "\n".join(lines)
