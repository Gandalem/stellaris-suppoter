"""Plain text views; no markup interpretation."""
import json

STATUS = {"ok": "조회 완료", "partial": "일부 정보", "not_found": "결과 없음", "unsupported": "지원 범위 밖", "error": "조회 실패"}
LABELS = {"cost": "연구 비용", "tier": "단계", "area": "분야", "prerequisites": "선행 기술", "category": "분류", "weight": "가중치"}


def source_label(ref):
    return f"{ref['relative_path']}:{ref['line_start']}–{ref['line_end']} · SHA256 {ref['file_sha256'][:12]}"


def text_view(data, fields=None):
    if not isinstance(data, dict):
        return str(data)
    lines = [STATUS.get(data.get("status"), data.get("status", ""))]
    if data.get("snapshot_id"):
        lines.append("스냅샷 " + data["snapshot_id"][:12])
    if "summary" in data:
        lines.append(json.dumps(data["summary"], ensure_ascii=False, indent=2))
    for row in data.get("results", ()):
        if "facts" in row:
            lines.extend([row["display_name"], row["game_id"], "스냅샷 " + row["snapshot_id"][:12]])
            for fact in row["facts"]:
                if fields is None or fact["field_name"] in fields:
                    lines.append(f"{LABELS.get(fact['field_name'], fact['field_name'])} {fact['operator']} {fact['raw_expression']}  [{fact['support_status']}]")
            lines.append(source_label(row["definition_source_ref"]))
            for warning in row.get("warnings", ()):
                lines.append(warning["code"])
        else:
            lines.append(f"{row.get('game_id', row.get('section', ''))} · {row.get('change_kind', '')}")
            lines.append(json.dumps(row.get("details", row), ensure_ascii=False, indent=2))
    for edge in data.get("edges", ()):
        lines.append(f"{edge['relation_kind']} → {edge['target_game_id']} [{edge['status']}]")
        if edge.get("conditions_raw"):
            lines.append(edge["conditions_raw"])
        lines.append(source_label(edge["source_ref"]))
    if data.get("cycles"):
        lines.append("순환 관계 있음")
    if data.get("truncated"):
        lines.append("표시 한도에 도달했습니다.")
    for item in data.get("diagnostics", ()):
        lines.append(item["code"])
    return "\n".join(lines)


def collect_sources(data):
    found = []
    def walk(value):
        if isinstance(value, dict):
            if {"snapshot_id", "relative_path", "file_sha256", "byte_start", "byte_end"} <= value.keys():
                if value not in found:
                    found.append(value)
            else:
                for child in value.values():
                    walk(child)
        elif isinstance(value, (tuple, list)):
            for child in value:
                walk(child)
    if isinstance(data, dict) and data.get("card_view"):
        # Keep the displayed value proof reachable even when raw facts fill the source limit.
        walk(data["card_view"]["definition_source_ref"])
        walk(data["card_view"]["fields"]["cost"])
    walk(data)
    return found[:128]


ERROR_MESSAGES = {
    "SNAPSHOT_NOT_READY": "사용할 데이터가 없습니다. 홈에서 색인을 실행하거나 조회할 데이터를 선택해주세요.",
    "NO_ACTIVE_SNAPSHOT": "사용할 데이터가 없습니다. 홈에서 색인을 실행해주세요.",
    "SNAPSHOT_NOT_FOUND": "선택한 데이터를 찾지 못했습니다. 홈에서 목록을 새로고침해주세요.",
    "CACHE_MISSING": "저장된 원문을 찾지 못했습니다. 홈에서 색인을 다시 실행해주세요.",
    "SOURCE_CHANGED": "저장된 정보와 출처가 일치하지 않습니다. 홈에서 색인을 다시 실행해주세요.",
    "SQLITE_BUSY": "데이터가 사용 중입니다. 잠시 후 다시 검색해주세요.",
    "SQLITE_ERROR": "검색 데이터를 읽지 못했습니다.",
    "QUERY_INVALID": "검색 조건을 확인해주세요.",
}


def search_error_text(data):
    import re

    codes = [d.get("code", "") for d in data.get("diagnostics", ())]
    codes = [c for c in codes if isinstance(c, str) and re.fullmatch(r"[A-Z][A-Z0-9_]{0,79}", c)]
    code = codes[0] if codes else "SEARCH_ERROR"
    return ERROR_MESSAGES.get(code, "검색을 완료하지 못했습니다.") + "\n오류 코드: " + code
