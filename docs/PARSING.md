# 정적 파싱·현지화

목표는 엔진 복제가 아니라 원문을 보존하는 정적 탐색입니다. 현재 설치 파일을 제공받지 않았고 관련 Wiki 본문도 이번 조사에서 확보하지 못했습니다([출처](SOURCES.md)). 아래는 조사 후보와 구현할 지원 범위이며 최신 게임에서 모두 확인된 사실이 아닙니다.

## 데이터 경로 조사 후보

| 범주 | 경로 후보 | 최소 추출 |
|---|---|---|
| 기술 | common/technology/ | ID, 선행 참조, 비용·가중치 원문, 조건 |
| 함선 부품 | common/component_templates/ | ID/key, 수치 표현식, 제한 |
| 건물·지구·직업 | common/buildings/, common/districts/, common/pop_jobs/ | ID, 비용·생산·유지비 표현식 |
| 특성 | common/traits/ | ID, modifier·조건 |
| 정부·시빅·기원 | common/governments/ 및 실제 하위 경로 | ID, 타입·조건·DLC 표현식 |
| 전통·승천 | common/traditions/, common/ascension_perks/ | ID, 선행·효과 |
| 이벤트·보조 script | events/, common/scripted_triggers/, common/scripted_effects/ | namespace, ID, 참조, 조건·효과 원문 |
| 번역 | localisation/ 및 실제 언어별 구조 | key, 언어, 값, 위치 |

inventory에서 실재 경로를 먼저 확인합니다. 경로가 없으면 게임에 그 기능이 없다는 뜻이 아니라 해당 위치에서 못 찾았다는 뜻입니다. mapping과 지원 범위를 registry로 관리하며 기억에 의존해 폴더 이름을 고정하지 않습니다.

## lexer·AST

첫 지원은 공백/줄바꿈, # 주석, 중괄호, = 할당, > < >= <= 비교, quoted string과 escape, 숫자·identifier·변수 참조 원문입니다. 긴 연산자를 먼저 분리하고 문자열 안의 brace/#를 구조나 주석으로 처리하지 않습니다.

블록의 assignment와 bare scalar 혼합, 중복 키, namespace, 파일 변수는 순서 있는 노드로 보존합니다. typed block·매크로형 표현식·새 연산자 등 미지원 구조는 unknown 노드와 진단으로 남깁니다. 입력을 코드로 실행하지 않습니다.

UTF-8/BOM을 우선 지원합니다. decoding 실패를 replacement 문자나 임의 인코딩 추측으로 숨기지 않습니다. lexer byte span은 0-based half-open, line/column은 1-based이며 end는 exclusive입니다. CRLF는 한 번의 줄바꿈으로 계산합니다. 선두 UTF-8 BOM은 별도 token으로 보존하되 다음 실제 문자는 line 1/column 1에서 시작합니다. 위치는 문자별 map을 선할당하지 않고 token 순회 중 line/column cursor로 계산합니다. lexer 기본 자원 한도는 입력 16 MiB와 token 100,000개이며 byte 한도는 UTF-8 검증 전에, token 한도는 다음 Token/SourceSpan 생성 전에 적용합니다. 한도 초과는 LIMIT_EXCEEDED로 실패하며 입력을 잘라 성공 처리하지 않습니다. 문자열 미종결·brace 누락·예상 밖 EOF는 오류이며 조용한 성공이 아닙니다. ordered AST는 duplicate pair와 mixed scalar/pair 순서를 보존하고 unknown syntax를 raw span + explicit diagnostic으로 남깁니다. parser 기본 자원 한도는 depth 128, node 100,000개, diagnostic 1,000개이며 현재 recursive implementation의 configurable max_depth는 128 이하만 허용합니다. depth/node 한도 초과는 explicit parser diagnostic으로 중단하거나 해당 raw region을 bounded unknown node로 보존합니다.

## 도메인 adapter

TASK-008의 기술 수직 슬라이스는 합성 fixture에서 구현됐습니다. ordered AST의 ParseResult와 원문 출처를 입력으로 받아 기술 ID, 중복 필드, 표현식, 조건 구조, 제한된 선행 참조 및 진단을 보존합니다. 이는 실제 게임 파일 호환성이나 다른 도메인 adapter의 완료를 뜻하지 않습니다. 이후 범주마다 합성 fixture, ID 식별법, 필드·조건·출처 보존, 중복 충돌, 참조 추출, unknown 동작을 테스트한 뒤 지원 목록에 추가합니다. AST 자체는 수정하지 않습니다.

potential, allow, prerequisites, weight, modifier 등의 이름만 보고 전체 게임 의미를 확정하지 않습니다. 읽은 숫자와 현재 제국에 적용되는 값은 다릅니다. 가중치는 후보군·조건·추첨 규칙 없이는 등장 확률이 아닙니다.

중복 ID는 모두 보존합니다. 파일 목록의 마지막 값이 실제 적용값이라고 가정하지 않습니다. 효과적인 정의 선택은 로드 규칙을 검증하는 F-017의 책임입니다.

## 현지화

TASK-009 전용 localisation reader는 일반 YAML parser를 사용하지 않습니다. UTF-8 strict/BOM, CRLF/LF, 언어 header, key, 선택적 숫자 marker, quoted value, lexical `\"`/`\\` escape, comment, 순서·중복 정의와 원본 byte span을 보존합니다. marker는 문자열 metadata이며 게임 패치 버전이 아닙니다. 잘못된 header, 미종결 값, 미지원 문법, 인코딩 오류는 정상 항목으로 만들지 않고 unknown span과 diagnostic으로 남깁니다.

resolver는 **요청 언어 → 영어 → 원래 ID** fallback을 적용하고 실제 사용한 언어 및 번역 SourceRef를 기록합니다. 검증되지 않은 중복 정의 우선순위는 `ambiguous`로 표시하고 마지막 값을 임의 선택하지 않습니다. **`$KEY$` 형태의 정적 참조만** 안전하게 확장하며, 참조별 key·선택 언어·SourceRef를 별도로 보존합니다. 누락 참조, 자기 참조, 다중 key 순환은 명시적 diagnostic과 `partial` 상태로 표시합니다.

미지원 동적 scope(`[Root.GetName]`, `[Root.$KEY$]`), 아이콘(`£`)·색상(`§`) 태그 및 미지원 escape(`\$KEY$` 등)는 정적 참조를 찾기 **전에** 보호 영역으로 분류합니다. 해당 영역 안의 `$KEY$`를 확장하지 않고 원문을 그대로 유지하며 `LOC_DYNAMIC_UNSUPPORTED` 또는 `LOC_UNSUPPORTED_ESCAPE` 진단을 남깁니다. 보호 영역 밖의 정상 정적 참조는 계속 확장합니다. 엔진의 동적 표현식은 실행하거나 의미를 추측하지 않습니다.

reader 기본 자원 한도는 파일당 16 MiB, 한 행당 1 MiB, 항목/전체 기록(header·comment·unknown 포함) 각 100,000개, 진단 1,000개입니다. entry prefix는 선택적 숫자 marker와 whitespace를 서로 겹치지 않는 순방향 스캔으로 처리합니다. 각 기록을 추가하기 **직전** record budget을 검사하고, 정확히 한도에 도달한 파일 종료는 성공, 다음 기록 추가는 `LIMIT_EXCEEDED`와 `complete=False`를 반환합니다.

resolver 기본·지원 최대 참조 depth는 64, visits는 4,096, 누적 source scan은 8 MiB, 확장 출력은 UTF-8 1 MiB, diagnostics는 100입니다. 한도 초과를 무한 탐색·조용한 성공으로 바꾸지 않습니다. 원본 bytes·SHA-256·안전한 상대 경로·snapshot 일치가 검증된 입력 문맥으로 SourceRef를 생성하며, technology 정의·필드 출처와 localisation entry·정적 확장 출처는 섞지 않습니다.

현재 수용 근거는 프로젝트 직접 작성 합성 fixture뿐입니다. 실제 게임 설치 파일과 게임 엔진 의미, 로드 우선순위, TASK-010 SQLite persistence는 아직 검증·구현되지 않았습니다.

## 로컬 조사 보고

파일 수, encoding 분포, 성공/부분/실패 수, 미지원 구문 유형, 상대 경로 진단만 공개합니다. 원문·DLC 콘텐츠·세이브·개인 경로는 올리지 않습니다. 재현이 필요하면 직접 만든 최소 합성 사례를 사용합니다.

**TASK-014 foundation (partial; authored synthetic grammars only)**

`domain/generic.py` provides opt-in `DOMAIN_REGISTRY` entries for component templates (`common/component_templates/`, unique static `key` field), buildings (`common/buildings/`, top-level literal ID), districts (`common/districts/`, top-level literal ID), and pop jobs (`common/pop_jobs/`, top-level literal ID). These paths and rules are **authored synthetic fixtures**, not verified mappings from an installed Stellaris version. Unrecognised top-level syntax remains `unhandled` with a diagnostic. No actual game precedence or cost/condition evaluation is inferred.

The non-technology `DomainCandidate` contract carries `game_id|None`, `kind`, `definition_occurrence`, raw ordered `items`, `fields`, `conditions`, definition/ID `SourceRef`, diagnostics, resolution, support level and explicit synthetic `localisation_key`. The new adapter validates source SHA, candidate path, token/node spans, parser budgets and raw serialization budgets; a separate `verify_domain_candidate` re-parses to reject tampered identifiers, kind, spans and occurrences. The old `TechnologyCandidate` and SQLite v1 contracts remain unchanged, as do SearchService/AnswerService/CLI implementations. A successful adapter extraction does **not** mean indexed, searchable or citeable product support.

Historical four-domain foundation status (before Phase A): traits, governments, civics, origins, traditions, ascension perks, events and scripted triggers/effects had not yet been implemented. **Current status after Phase A:** trait, government, civic and origin have authored *synthetic* adapters; the remaining unimplemented domains are **tradition, ascension perk, event, scripted trigger and scripted effect**. E-027 remains `not_run` until the full authored synthetic matrix passes. No real installation grammar or localisation convention has been verified.

**TASK-014 Phase A — 추가 4개 합성 도메인 어댑터 (실제 게임 미검증)**

`domain/generic.py`의 opt-in registry에 Trait(`common/traits/`, 최상위 literal ID), Government(`common/governments/`, `governments = { <government_id> = { ... } }`의 직계 하위 ID), Civic(`common/governments/civics/`, `civic = { key = <civic_id> ... }`의 유일한 정적 `key`), Origin(`common/governments/origins/`, `origin = { id = <origin_id> ... }`의 유일한 정적 `id`)을 **직접 작성한 synthetic grammar**로 등록했습니다. 이는 Stellaris 설치본에서 경로·문법·실제 ID 규칙을 검증한 결과가 아닙니다. 정부 wrapper의 타입 이름, 시빅·기원의 타입 이름, 파일명, 순번은 실제 ID로 승격하지 않습니다. 동적·중복·누락 ID는 `partial` 또는 미지원 unhandled 원문·진단으로 남습니다.

Trait의 현지화 key는 명시적 합성 `game_id` 규칙이고, Government/Civic/Origin은 `name = <literal_key>`를 단 한 번 정의한 경우에만 game ID와 분리된 synthetic localisation key로 사용합니다. 정적 `name`이 없거나 동적·중복이면 `DOMAIN_UNRESOLVED_LOCALISATION_KEY` 진단과 `partial`로 표시하며 임의의 표시 이름을 생성하지 않습니다. 기존 LocalisationCatalog/resolve_localisation의 한국어→영어→ID fallback, root/dependency SourceRef, unresolved/ambiguous/partial 및 안전한 정적 참조 확장을 재사용합니다. `localisation_key=None`인 후보는 안전하게 이름 해석을 거부합니다. 정적인 `name` key를 추출했지만 번역 항목을 찾지 못한 경우 resolver의 마지막 fallback은 **그 localisation key**이며 별개인 `game_id`와 혼동하지 않습니다.

모든 8개 synthetic adapter는 동일한 `adapt_domain`의 파일 SHA·경로·canonical ParseResult 전체 바인딩(R2)과 `verify_domain_candidate`의 ordered items, field/condition value, nested raw backing 검증(R1)을 사용합니다. Government의 하위 후보도 별도 약한 검증 경로로 우회하지 않습니다. 공개 `DomainCandidate/DomainField/DomainDiagnostic`의 기존 필드·직렬화·4개 기존 도메인 동작은 보존했습니다. `scripts/bench_domain_wave2.py`는 동일 파일의 후보별 재파싱 호출 횟수와 경과시간을 양 OS에서 비차단 측정하는 authored 합성 microbenchmark이며 TASK-019의 공식 성능 기준선이 아닙니다.

이 문단은 Phase A 작성 당시 잔여 범주를 기록한 역사적 내용입니다. **Phase B 구현 PR**에서는 전통(tradition)과 승천 특전(ascension_perk)의 합성 정적 추출을 추가했습니다. 아직 구현되지 않은 도메인은 이벤트(event), scripted trigger, scripted effect입니다. 전 도메인 E-027 전체 평가, 실제 게임 문법·버전, SQLite 다도메인 영속화, CLI 다도메인 검색과 UI는 이번 PR 범위 밖입니다. TASK-014=`doing`, F-005=`in_progress`, E-027=`not_run`입니다.

**TASK-014 Phase B — 전통·승천 특전 합성 어댑터 (실제 게임 미검증)**

경로 `common/traditions/`와 `common/ascension_perks/`는 *직접 작성한 synthetic fixture 전용 조사 후보*입니다. 전통은 `traditions = { group_entry = { id = tr_a name = tr_a_name ... } }` 형식으로, 바깥 `traditions` 블록과 `group_entry`의 이름을 ID로 **사용하지 않습니다**. 직계 자식 블록 내부의 고유하고 정적인 `id` 값만 `game_id`로 기록합니다. 승천 특전은 `ascension_perk = { id = perk_a name = perk_a_name ... }`의 정적 고유 `id` 필드만 ID로 사용합니다. 다른 계층·파일명·동적/중복 ID로 추측하지 않고 `partial` 또는 명시적 `unhandled`와 원문·진단을 남깁니다.

두 범주 모두 단일한 정적 `name` 필드가 `localisation_key`라는 *합성 정책*을 사용하며 게임 ID와 별개입니다. 현지화 key가 없으면 이름 해석을 거부하고, key는 있으나 한국어·영어 번역이 없을 때는 그 key로 fallback합니다. 출처의 SHA·snapshot·path·ordered AST·field/condition raw backing(R1) 및 canonical ParseResult 전체 결합(R2)을 기존과 동일하게 검증합니다. 그룹 내부 child마다 진단 한도 1,000을 검사하고, 단일 후보 내부에서 너무 많은 operator/unknown 진단이 발생할 때도 원문 raw 투영을 만들기 전에 차단합니다. 실제 적용 우선순위·비용/효과 계산은 수행하지 않습니다. 별도 `bench_domain_wave3.py`는 32개 합성 후보의 적응 호출 1회 vs 개별 검증 32회 재파싱과 경과시간을 비차단 측정하며 TASK-019 공식 성능 평가는 아닙니다.


**TASK-014 Phase C1 — Event 합성 namespace 어댑터 (실제 게임 문법 미검증)**

조사 후보 경로 `events/`는 authored synthetic fixture일 뿐 실제 Stellaris 설치본 호환성 증거가 아닙니다. 등록된 이벤트 유형은 `country_event`와 `planet_event`뿐입니다. 두 유형 모두 고유한 정적 `id` 필드를 통해서만 `game_id`를 추출하고, `namespace = authored` 선언과 접두어를 대조합니다. 이벤트 유형, namespace 자체, 파일명·순번·중첩 이벤트 표현식을 독립 ID로 추측하지 않습니다.

동일한 namespace의 반복 선언은 각각 `DOMAIN_EVENT_NAMESPACE` info 진단의 SourceRef로 보존합니다. 선언 누락·동적·무효·충돌, 다른 namespace 접두어, 정적 ID·title 누락은 명시적 부분 결과로 유지하며 다른 파일에 있는 선언이 현재 파일에도 적용된다고 추론하지 않습니다. 미등록 event wrapper는 원본 unhandled로 남습니다. `trigger`는 조건 원문이며 `immediate` 등 중첩 이벤트 관련 내용은 실행하거나 별도 이벤트로 생성하지 않고 ordered AST/raw로 보존합니다. 고유한 정적 `title`은 `game_id`와 별개의 합성 `localisation_key`로만 사용합니다.

Event C1도 기존 `adapt_domain`의 정확한 SHA/path/snapshot 및 canonical 전체 ParseResult 검증(R2), `verify_domain_candidate`의 items/fields/conditions/RawNodeRef 하위 트리 개별 backing 검사(R1)를 그대로 사용합니다. namespace provenance, parser 진단, adapter 진단은 전체 1,000개 예산을 공유하고, 한도 도달 시 `LIMIT_EXCEEDED`·`blocked=True`·빈 후보로 중단합니다. 단일 후보 내부의 미지원 operator/unknown 노드 대량 진단 사전 검사도 유지됩니다.

별도 `scripts/bench_domain_event.py`는 동일 합성 원문의 이벤트 32개를 적응할 때 1회, 각 후보를 독립 검증할 때 32회의 canonical reparse를 관찰하는 비차단 측정입니다. 반복 파싱의 개선은 source_id/snapshot/path/SHA와 완전한 raw backing 무결성을 유지하는 검증된 읽기 전용 컨텍스트가 필요하며 TASK-019/E-035 통과 근거가 아닙니다. 이 C1 결과로 scripted trigger/effect 및 13개 전 도메인의 E-027 평가가 완료되는 것은 아닙니다. TASK-014=doing, F-005=in_progress, E-027=not_run을 유지합니다.


## TASK-014 Phase C1 — 이벤트 ID 형식 R1/P2 후속 검증

다음은 실제 설치본에서 검증한 게임 이벤트 문법이 아닌, **PR #32의 직접 작성한 synthetic fixture 전용** 정적 ID 규칙입니다.

- 형식: `<namespace>.<suffix>` (마침표 구분자 정확히 한 개)
- namespace: `[A-Za-z_][A-Za-z0-9_]*`
- suffix: `[A-Za-z0-9_]+` (한 글자 이상; 영문 ASCII·숫자·밑줄)
- `authored.1`, `authored.example`은 정상입니다. `authored.`(빈 suffix), `authored..1`(중복 마침표), `authored.1.`(후행 마침표), `.1`(빈 namespace), `authored.1.2`(복수 분리)는 완전한 합성 ID가 아닙니다. 하이픈 또는 다른 구분자도 이 **제한된 합성 규칙**에는 포함하지 않습니다.
- 접두 namespace가 해당 파일에서 출처를 검증한 선언과 다르면 `DOMAIN_EVENT_NAMESPACE_MISMATCH`, 마침표가 전혀 없으면 `DOMAIN_EVENT_UNQUALIFIED_ID`, 구분자가 있어도 정적 형식이 맞지 않으면 `DOMAIN_EVENT_INVALID_QUALIFIED_ID` warning으로 `partial` 처리하며 `complete=True`로 승격하지 않습니다. 원본 `game_id`, `id_source_ref`, 원본 바이트와 필드 순서/occurrence는 바꾸지 않습니다.
- 선언 누락·중복 동일 namespace·서로 다른 namespace 충돌 등 기존 처리는 유지합니다. 유효 ID에서도 namespace 추측이나 게임 엔진의 실제 문법 해석은 하지 않습니다. 다른 10개 도메인의 공통 `_ID` 검증은 변경하지 않습니다.

재현 및 회귀 근거: `harness/evidence/TASK-014-event-review-followup.md`. 필수 R1/R2 출처 검증과 1,000개 공유 진단 예산도 그대로 유지합니다.
