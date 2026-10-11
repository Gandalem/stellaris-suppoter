# 데이터 계약 v1

이 문서는 구현 규범입니다. TASK-010에서 SQLite v1 typed schema, 결정적 snapshot identity, 원자적 active pointer 전환 및 SourceRef·원본 캐시 SHA 검증을 구현했습니다. 자동 DB migration과 원본 캐시를 포함한 전체 백업/복구는 아직 미구현이며, 검색·FTS는 TASK-011 범위입니다. 별도 JSON Schema 자동 생성·검증의 완료를 의미하지 않습니다. null(알 수 없음)은 0, false, 빈 목록과 구별합니다. 시간은 UTC ISO 8601입니다.

## 출처

SourceRef: snapshot_id, source_kind, source_id, relative_path, file_sha256, byte_start, byte_end, line_start, line_end.

source_kind는 synthetic|base|mod|official|wiki|community입니다. 웹 출처는 F-015에서 URL·article_id·section·retrieved_at 계약으로 확장하며 가짜 파일 위치를 만들지 않습니다. byte 범위는 원본에서 0-based [start,end), 행은 1-based 양끝 포함입니다. BOM·CRLF를 포함한 원본에 대응해야 합니다. 화면에는 상대 경로만 표시합니다. 과거 스냅샷 인용을 수정된 현재 파일인 것처럼 표시하지 않습니다.

## 스냅샷

Snapshot: id, content_hash, schema_version, parser_version, adapter_version, policy_hash, context_kind, game_version, game_version_source, build_id, branch, dlc_state, mod_state, created_at, checked_at, status, diagnostics.

context_kind는 synthetic|base_install|effective이며 마지막 값은 모드 검증 후에만 사용합니다. game_version은 string|null, 근거는 metadata|user_reported|unknown입니다. build_id를 패치 버전으로 변환하지 않습니다. branch는 stable|beta|unknown입니다. 선택 결과와 별도로 VersionObservation(field, source, raw_value, normalized_value, disposition)을 보존하며, 미지원 metadata branch가 존재하면 user-reported branch로 fallback하지 않고 branch=unknown을 유지합니다. status는 building|ready|partial|failed이며 building은 조회하지 않습니다. partial 활성화는 명시 승인이 필요합니다.

DLC의 installed, owned, enabled는 각각 true|false|null이고 별도 근거를 갖습니다. 각 필드는 value, source, evidence를 가지며 source는 filesystem|platform|launcher|user_reported|unknown입니다. 알려진 true/false 상태를 source=unknown으로 저장하지 않습니다. mod_state는 none_reported|detected_unresolved|resolved|unknown입니다. 설치 폴더만 보고 모드 없음으로 단정하지 않습니다.

content_hash는 상대 경로·원문 해시·출처 종류/ID의 정렬된 목록으로 계산합니다. snapshot_id는 content_hash와 스키마·파서·adapter·정책·분석 문맥의 canonical JSON SHA-256입니다. 시간과 절대 경로는 제외합니다. 직렬화 규칙은 fixture로 고정합니다.

## AST·진단

Node: node_id, kind, span, raw, children. kind는 document|assignment|block|scalar|comment|unknown입니다. assignment는 key, operator, value를 추가합니다. children은 순서 있는 목록이며 중복 키도 별도 occurrence입니다. raw와 span을 보존합니다. 원문 숫자·변수·조건을 임의로 0이나 bool로 바꾸지 않습니다.

Diagnostic: code, severity(info|warning|error), message, source_ref|null, remediation|null. 최소 코드: VERSION_UNKNOWN, SOURCE_CHANGED, PARSE_UNSUPPORTED, PARSE_ERROR, LOC_MISSING, LOC_CYCLE, COLLISION_UNRESOLVED, PARTIAL_INDEX, LIMIT_EXCEEDED, PATH_REJECTED, BASE_ONLY.

## 엔티티·관계·현지화

Entity: entity_key, game_id, kind, snapshot_id, name, description, language_used, fields, conditions, source_refs, resolution, diagnostics. entity_key는 snapshot·파일·노드 occurrence에 연결합니다. game_id만 기본키로 쓰지 않습니다. resolution은 raw_definition|resolved|ambiguous|partial입니다.

fields 각각은 name, raw_value, normalized_value, value_type, source_ref를 갖습니다. 조건은 부모 구조·순서·원문을 보존합니다. 번역 이름/설명도 별도 출처와 fallback 상태를 갖습니다. 미지원 필드는 raw 영역에 남깁니다.

Relation: from_entity_key, relation_kind, target_game_id, target_entity_key|null, source_ref, status(resolved|unresolved|ambiguous), conditions_raw|null. prerequisite, event_reference, script_reference는 정적으로 확인한 관계만 의미하며 실행을 보장하지 않습니다.

LocalisationEntry: key, language, marker(string|null), occurrence, source_ref, value_source_ref, quoted_value_source_ref, column_start, column_end, value_column_start, raw_value(원본 quotes 내부), display_value(정적 lexical escape 처리만), has_unsupported_escape. 원본 bytes는 immutable source와 SourceRef span으로 참조하고 entry마다 중첩 raw 문자열을 복제하지 않습니다. BOM·CRLF 및 멀티바이트 값에도 0-based half-open byte span과 1-based column을 유지합니다. 지원되지 않은 행은 unknown_spans와 diagnostic으로 유지합니다.

LocalisationDocument: entries(ordered), headers, comments, unknown_spans, diagnostics, complete, context. SourceContext의 snapshot/source ID·상대 경로·SHA-256과 원본 bytes 일치 여부를 입구에서 검증합니다. 불일치·디코딩 오류는 원문을 임의 재해석하지 않는 명시적 오류입니다.

LocalisationCatalog: 동일 snapshot의 여러 문서를 순서대로 보존합니다. 같은 (language,key)의 정의가 둘 이상이면 ambiguous이고 어떤 값도 조용히 선택하지 않습니다.

LocalisationResolution: key, language_requested, language_used(string|null), display_value, source_ref(선택한 번역|null), reference_source_refs(확장 참조의 번역 출처 목록), reference_selections(참조 key·실제 선택 언어·SourceRef의 순서 있는 목록), fallback(none|english|id), resolution(resolved|partial|unresolved|ambiguous), diagnostics, visits, scanned_bytes, output_bytes, truncated. fallback은 **요청 언어 → 영어 → 원래 ID** 순서로 결정하며, 누락·중복·순환·동적 scope/formatting·한도 초과를 구별합니다. 검증되지 않은 중복 정의의 우선순위는 추측하지 않으며 `ambiguous`로 남깁니다. 원본 value를 먼저 순방향 탐색해 동적 bracket scope·icon/colour 태그·지원되지 않은 escape를 **보호 영역**으로 분류한 뒤, 그 영역 **밖의** `$KEY$` 형태만 **정적 참조**로 확장합니다. 보호 영역 내부의 `$KEY$`는 치환하거나 참조 선택하지 않고 원문으로 보존하며 동적 표현식을 실행하지 않습니다. `resolved`는 지원한 정적 참조를 완전히 처리했을 때, `partial`은 일부 해석·보존은 됐으나 미지원·오류·자원 한도로 완전한 확정이 불가능할 때, `unresolved`는 요청 언어와 영어 번역이 모두 없어 ID로 대체했을 때, `ambiguous`는 중복 정의의 우선순위를 알 수 없을 때 사용합니다. 누락된 참조·순환은 관련 diagnostic과 부분 결과로 나타냅니다. `truncated`는 자원 한도로 출력을 중단했음을 뜻하며 완전 성공으로 해석하지 않습니다. 

TechnologyLocalisedName: 기존 immutable TechnologyCandidate와 별도의 LocalisationResolution을 조합합니다. 기술 정의·필드 SourceRef를 번역 SourceRef로 덮어쓰지 않습니다. 이는 TASK-010 DB persistence schema가 아니라 순수 메모리 연결 계약입니다.

reader 기본 한도: 파일 16 MiB, 행 1 MiB, entry 100,000, 모든 기록(header/comment/unknown 포함) 100,000, diagnostic 1,000. entry prefix의 key·marker·공백은 중복 반복 정규식 대신 단조 증가하는 인덱스로 처리하며, header+comment 또는 entry+comment 같은 복수 기록도 각 append 직전에 기록 한도를 검증합니다. resolver 기본 한도: reference depth 64(지원 설정 최대도 64), visits 4,096, scanned source bytes 8 MiB, expanded UTF-8 output 1 MiB, diagnostics 100. 한도 초과는 LIMIT_EXCEEDED와 partial/complete=false로 표시하며 숨겨진 truncate-success를 만들지 않습니다.

## 질의·답변

Query: text, snapshot_id, kind|null, language, limit. 질의 최대 512문자, limit 1~100, 공백 질의는 오류입니다. active도 명시 snapshot도 없으면 오류입니다.

AnswerEnvelope: schema_version, status, query, context, results, diagnostics, truncated. status는 ok|partial|not_found|unsupported|error입니다. context는 snapshot_id, kind, game_version, checked_at을 갖습니다. results 원소는 entity_key, game_id, kind, display_name, match_reason, facts, source_refs를 갖습니다. facts마다 실제 필드를 포함한 근거가 필요합니다. 결과 없음은 빈 results이며 사실을 생성하지 않습니다.

## 저장 구조

논리 테이블: snapshots, source_files, entities, localisation_entries, relations, search_documents, diagnostics, settings. 모든 관계·조회는 snapshot 경계를 적용합니다. 원문 bytes는 개인 content-addressed cache에 보존하고 DB가 해시를 참조합니다. FTS는 재생성 가능한 보조 색인입니다.

schema_version과 앱 버전은 다릅니다. migration에는 백업·복구가 필요합니다. 더 최신 schema를 발견한 구버전 프로그램은 쓰지 않습니다. 캐시 정리는 참조된 snapshot 원문을 보존해야 합니다.

**TASK-010 SQLite v1 물리 계약 (저장 API, 전체 CLI/검색은 후속):**

- `SnapshotPolicy`는 schema_version, parser_version, adapter_version, policy_hash(SHA-256), context_kind, analysis_context, game_version|null, game_version_source, build_id|null, branch, dlc_state, mod_state를 별도 typed 값으로 받습니다. 순수 identity 계산은 schema 변경에도 다른 ID를 생성할 수 있지만 현 Repository의 쓰기 지원 버전은 오직 v1입니다.
- 경로는 두 OS의 slash를 `/`로 통일하되 **대소문자 원형을 보존**합니다. 상대 경로는 정규화된 NFC만 수락하고 절대 경로, `..`, 빈 구성요소, OS 예약 이름, case-insensitive 충돌을 거부합니다. 다른 출처를 묵시적으로 하나로 합치지 않습니다.
- canonical JSON은 UTF-8, `ensure_ascii=False`, 키 정렬, 공백 없는 구분자, 비유한 부동소수·임의 객체 거부입니다. 파일 identity 목록을 `(source_kind,source_id,relative_path)`로 정렬한 다음 각 항목의 `source_kind`, `source_id`, `relative_path`, `file_sha256`에 SHA-256을 적용해 content_hash를 생성합니다. snapshot ID는 content_hash와 정책/스키마/문맥 필드의 canonical JSON SHA-256입니다. 수집 시각·개인 절대 경로·임시 디렉터리·탐색 순서는 포함하지 않습니다. `created_at`은 저장 메타데이터일 뿐 ID의 구성요소가 아닙니다.
- 물리 테이블은 `snapshots`, `source_files`, `entities`, `localisation_entries`, `relations`, `search_documents`, `diagnostics`, `settings`입니다. `(snapshot_id,entity_key)` 및 복합 source FK를 쓰고 `game_id`는 중복 가능한 인덱스 열입니다. 기술 candidate/field/source_refs의 bounded JSON과 별도 localisation result JSON을 유지합니다. 해당 값의 `null`, `false`, `0`, `[]`는 구별됩니다. 원문은 레코드마다 복제하지 않고 파일 SHA-256 cache를 참조합니다. `search_documents`는 TASK-011을 위한 빈 저장 경계로, FTS와 순위는 아직 없습니다.
- 별도 settings key `active_snapshot`이 선택 포인터입니다. 스냅샷 빌드 상태는 `building|ready|partial|failed`로 보존하며 `active`는 상태를 뜻하지 않습니다. `stage`는 building 기록을 먼저 남긴 뒤 원본·SourceRef·FK·cache를 검증해 ready/partial로 전환합니다. 스냅샷이 이미 존재하면 덮어쓰지 않고 명시적 재선택만 허용합니다. building/failed는 명시 snapshot 조회에도 제외합니다. 재시작 후 잔존 building의 failed 전환은 **다른 writer가 없음을 확인한 뒤** 명시적 복구 API로 수행합니다.
- `activate`는 `BEGIN IMMEDIATE` 트랜잭션 안에서 source manifest/live source 재검사, cache 원문·SHA 검사, FK 검사, partial 승인/취소 확인을 통과한 후에만 active 포인터를 변경하고 commit합니다. 외래 키는 모든 연결에서 ON, busy timeout 250ms, WAL+FULL 동기화입니다. DB commit 전 캐시 파일을 임시 파일→검증→원자적 파일 교체로 영속화하고 다시 검증합니다. SQLite와 파일시스템의 원자성을 동일하다고 주장하지 않으며, 과거 active가 참조하는 cache는 제거하지 않습니다.
- real/live 파일에는 명시 game_root와 안전한 경로 및 다시 읽기 경계가 필요하며, 활성화 때 현재 원문 검증용 manifest도 요구합니다. synthetic immutable bytes만 있는 경우 캐시 SHA 검사로 재현성을 확인합니다. `allow_partial`로도 경로 탈출·SHA 위조·캐시 오류를 우회하지 못합니다.
- 기본 제한: 파일 50,000개, 각 16MiB, 총 512MiB, 기술 후보+현지화 레코드 100,000개, 진단 10,000개, 각 JSON 직렬화 1MiB, 유한 writer 대기 250ms. 실제 메모리 사용량 측정에 대한 별도 보장은 아닙니다.
- DB `PRAGMA user_version=1`과 settings schema_version=1을 함께 확인하고 read-only 연결로 **먼저 검증**한 후 기존 DB에 접근합니다. 알 수 없는 과거/미래 버전·손상된 DB를 새 빈 DB로 간주하지 않고 거부합니다. 자동 migration은 구현하지 않았습니다. SQLite backup API는 DB 단독의 일관된 백업을 만들며, 실제 복구에는 같은 snapshot의 cache blob도 함께 보존해야 합니다.



**PR #19 R1~R4 보완 — live 원본·손실 없는 JSON·해시 일관성:**

- **서로 다른 두 경로 계약:** SourceRef의 `(source_kind, source_id, relative_path)`는 공개 가능한 **논리적 provenance**이고, `live_path`는 별도의 **실제 입력 파일**입니다. 논리 상대 경로가 game_root의 실제 경로와 같다고 가정하지 않습니다. base/mod별 source_id의 namespace는 그대로 유지하고, 모든 live 입력은 명시한 단일 game_root 내부의 실제 root-relative 경로여야 합니다. 그 밖의 모드 루트·링크·reparse·탈출 경로는 아직 지원하지 않으며 실패합니다.
- Staging 때 SQLite `source_files.live_relative_path`와 `live_root_sha256`를 **개인 DB 안에만** 기록합니다. 활성화 입력의 source key/bytes/SHA뿐 아니라 같은 game_root 바인딩과 동일한 root-relative 물리 파일을 검사한 뒤, **해당 파일**의 현재 SHA를 다시 확인합니다. 서로 다른 파일의 bytes가 같더라도 검증 대상을 바꿀 수 없습니다. 이 개인용 루트 fingerprint 및 실제 경로는 snapshot identity, 공개 E evidence, 로그의 원문 절대 경로에 포함하지 않습니다. 기존 v1의 구 물리 스키마에 대한 자동 migration은 제공하지 않으며 스키마 preflight에서 명시적으로 거부합니다.
- **JSON 용도 분리:** 파일 경로/metadata/policy 및 snapshot ID 계산의 canonical JSON은 Unicode NFC를 **요구하되 수정하지 않습니다**. 기술·현지화의 raw/display record를 저장하는 JSON은 codepoint를 있는 그대로 보존하며 NFC로 변환하거나 비-NFC를 거부하지 않습니다. 저장 JSON도 기존 record **1MiB**, 깊이 **280**, 항목 방문 **100,000**의 한도 내에서만 직렬화하며, 원본 바이트의 출처는 SHA-256 캐시와 SourceRef span입니다.
- **정책 자원 한도:** `SnapshotPolicy` 전체 identity JSON은 UTF-8 **1MiB(1,048,576 bytes)**, 중첩 **32**, JSON 노드/key 방문 수 **10,000**의 제한을 적용합니다. snapshot ID hash에 추가되는 `content_hash` envelope에는 최대 **128 bytes** 추가 한도를 명시합니다. 입력의 거대한 문자열은 byte-budget 이전에 글자 수 하한으로 조기 거부하며 최종 JSON은 제한된 streaming encoder로 검사합니다. 실패는 `LIMIT_EXCEEDED`; 새 building row나 active 갱신을 만들지 않습니다.
- **원문 pointer 일관성:** `source_files.cache_sha256=file_sha256`은 v1 테이블 CHECK 조건이고, `source_bytes()`가 읽을 때도 SourceRef hash = file SHA = cache SHA를 확인합니다. 실제 cache bytes는 다시 SHA 검증하며 불일치 시 `SOURCE_CHANGED`/무결성 오류로 fail-closed합니다. 원문 조회 오류 때문에 이전 active를 임의 변경하지 않습니다.
- **SQLite read-only 검사:** 최초 DB 열기·쓰기·백업에서는 전체 `PRAGMA quick_check`를 유지하지만 반복 read-only 조회마다 전체 페이지 검사를 재실행하지 않고 schema/version/FK preflight를 수행합니다. 비용 측정은 합성 DB의 비차단 benchmark로 관측하고, 실게임 검색 warm p95 검증으로 주장하지 않습니다.


**TASK-011 R1–R3 SearchHit 증거 계약 (원본 SQLite v1 불변):** SearchHit의 기존 definition_source_ref, localisation_source_ref 및 match_source_ref는 유지하고, localisation_reference_source_refs와 localisation_reference_selections (key, language_used, source_ref), match_reference_source_refs, match_reference_selections를 append-only typed field로 추가합니다. 참조는 root와 개별 종속 출처를 구별하고 동일 snapshot·원문 cache 및 저장된 entry key/language/span과 일치해야 합니다. 원문에 존재하지만 resolver가 dynamic/partial/ambiguous라고 판단한 표현은 검증된 정적 이름으로 올리지 않고, 안전한 영어 이름 또는 ID fallback을 사용합니다. VerifiedAlias는 명시 등록만 허용하며 출처가 동일 엔티티의 정의 또는 고유하게 연결된 localisation entry여야 합니다. **같은 source 파일에 문자열만 존재한다는 사실은 별칭 증거가 아닙니다.** 저장 schema/migration은 변경하지 않습니다.
