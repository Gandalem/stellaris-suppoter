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

Remaining TASK-014 domains (traits, governments, civics, origins, traditions, ascension perks, events, scripted triggers/effects) are not yet implemented. E-027 remains `not_run` until the entire authored synthetic domain matrix including localisation, collisions, limits and citation attacks passes. Real installation grammar and localisation key conventions remain unverified.
