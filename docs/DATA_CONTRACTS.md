# 데이터 계약 v1

이 문서는 구현 규범입니다. 실제 타입·DB migration·JSON Schema는 TASK-010에서 만듭니다. null(알 수 없음)은 0, false, 빈 목록과 구별합니다. 시간은 UTC ISO 8601입니다.

## 출처

SourceRef: snapshot_id, source_kind, source_id, relative_path, file_sha256, byte_start, byte_end, line_start, line_end.

source_kind는 synthetic|base|mod|official|wiki|community입니다. 웹 출처는 F-015에서 URL·article_id·section·retrieved_at 계약으로 확장하며 가짜 파일 위치를 만들지 않습니다. byte 범위는 원본에서 0-based [start,end), 행은 1-based 양끝 포함입니다. BOM·CRLF를 포함한 원본에 대응해야 합니다. 화면에는 상대 경로만 표시합니다. 과거 스냅샷 인용을 수정된 현재 파일인 것처럼 표시하지 않습니다.

## 스냅샷

Snapshot: id, content_hash, schema_version, parser_version, adapter_version, policy_hash, context_kind, game_version, game_version_source, build_id, branch, dlc_state, mod_state, created_at, checked_at, status, diagnostics.

context_kind는 synthetic|base_install|effective이며 마지막 값은 모드 검증 후에만 사용합니다. game_version은 string|null, 근거는 metadata|user_reported|unknown입니다. build_id를 패치 버전으로 변환하지 않습니다. branch는 stable|beta|unknown입니다. status는 building|ready|partial|failed이며 building은 조회하지 않습니다. partial 활성화는 명시 승인이 필요합니다.

DLC의 installed, owned, enabled는 각각 true|false|null이고 별도 근거를 갖습니다. mod_state는 none_reported|detected_unresolved|resolved|unknown입니다. 설치 폴더만 보고 모드 없음으로 단정하지 않습니다.

content_hash는 상대 경로·원문 해시·출처 종류/ID의 정렬된 목록으로 계산합니다. snapshot_id는 content_hash와 스키마·파서·adapter·정책·분석 문맥의 canonical JSON SHA-256입니다. 시간과 절대 경로는 제외합니다. 직렬화 규칙은 fixture로 고정합니다.

## AST·진단

Node: node_id, kind, span, raw, children. kind는 document|assignment|block|scalar|comment|unknown입니다. assignment는 key, operator, value를 추가합니다. children은 순서 있는 목록이며 중복 키도 별도 occurrence입니다. raw와 span을 보존합니다. 원문 숫자·변수·조건을 임의로 0이나 bool로 바꾸지 않습니다.

Diagnostic: code, severity(info|warning|error), message, source_ref|null, remediation|null. 최소 코드: VERSION_UNKNOWN, SOURCE_CHANGED, PARSE_UNSUPPORTED, PARSE_ERROR, LOC_MISSING, LOC_CYCLE, COLLISION_UNRESOLVED, PARTIAL_INDEX, LIMIT_EXCEEDED, PATH_REJECTED, BASE_ONLY.

## 엔티티·관계·현지화

Entity: entity_key, game_id, kind, snapshot_id, name, description, language_used, fields, conditions, source_refs, resolution, diagnostics. entity_key는 snapshot·파일·노드 occurrence에 연결합니다. game_id만 기본키로 쓰지 않습니다. resolution은 raw_definition|resolved|ambiguous|partial입니다.

fields 각각은 name, raw_value, normalized_value, value_type, source_ref를 갖습니다. 조건은 부모 구조·순서·원문을 보존합니다. 번역 이름/설명도 별도 출처와 fallback 상태를 갖습니다. 미지원 필드는 raw 영역에 남깁니다.

Relation: from_entity_key, relation_kind, target_game_id, target_entity_key|null, source_ref, status(resolved|unresolved|ambiguous), conditions_raw|null. prerequisite, event_reference, script_reference는 정적으로 확인한 관계만 의미하며 실행을 보장하지 않습니다.

LocalisationEntry: key, language, raw_value, display_value, source_ref, references, resolution. 중복을 보존합니다. fallback은 요청 언어 → 영어 → ID입니다. 정적 치환은 깊이/순환 제한을 두고 동적 표현식은 실행하지 않습니다.

## 질의·답변

Query: text, snapshot_id, kind|null, language, limit. 질의 최대 512문자, limit 1~100, 공백 질의는 오류입니다. active도 명시 snapshot도 없으면 오류입니다.

AnswerEnvelope: schema_version, status, query, context, results, diagnostics, truncated. status는 ok|partial|not_found|unsupported|error입니다. context는 snapshot_id, kind, game_version, checked_at을 갖습니다. results 원소는 entity_key, game_id, kind, display_name, match_reason, facts, source_refs를 갖습니다. facts마다 실제 필드를 포함한 근거가 필요합니다. 결과 없음은 빈 results이며 사실을 생성하지 않습니다.

## 저장 구조

논리 테이블: snapshots, source_files, entities, localisation_entries, relations, search_documents, diagnostics, settings. 모든 관계·조회는 snapshot 경계를 적용합니다. 원문 bytes는 개인 content-addressed cache에 보존하고 DB가 해시를 참조합니다. FTS는 재생성 가능한 보조 색인입니다.

schema_version과 앱 버전은 다릅니다. migration에는 백업·복구가 필요합니다. 더 최신 schema를 발견한 구버전 프로그램은 쓰지 않습니다. 캐시 정리는 참조된 snapshot 원문을 보존해야 합니다.
