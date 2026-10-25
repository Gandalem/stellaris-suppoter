# TASK-015: 선행 기술·정적 참조 조회 개발 계획

작성일: 2026-10-21, Asia/Seoul. 관련 기능 F-010/F-011, 평가 E-028/E-029.
기준 main: dc6f031c1eca781b53ad224bc5c881cc01465938, PR #36 병합본.

이 문서는 초기 설계의 기록이다. 사용자가 승인한 [2안](REFS-OPTION-2.md)으로 구현했으며, 실제 명령·응답·제한은 [CLI](CLI.md)와 [데이터 계약](DATA_CONTRACTS.md)이 기준이다. 구현 파일은 references.py, domain/event_references.py, storage/reference_reader.py, 테스트는 test_references.py와 test_references_cli.py로 정리했다. 검증은 사용자 지시에 따라 기능 구현 100% 이후에 시작했다.

## 1. 사용자에게 제공할 결과

기술 ID를 지정하면 정적으로 명시된 선행 기술을 조회하고, 각 연결의 원본 위치를 확인한다. 이벤트 ID에는 지원하는 구문에서 확인한 이벤트 참조를 같은 방식으로 제공한다. 조회 중 선택한 스냅샷은 끝까지 고정한다.

A → B의 뜻은 다음과 같다.

- prerequisite: A 기술의 원문 prerequisites에 B가 직접 명시되어 있다.
- event_reference: A 이벤트의 지원된 효과 구문에 B 이벤트의 정적 ID가 명시되어 있다.

resolved는 선택 스냅샷 안의 정적 정의와 연결됐다는 뜻이다. 연구 가능 여부, 실제 실행·발생 여부, 조건 충족, 확률, 소요 시간, 모드 적용 결과를 뜻하지 않는다.

## 2. 현재 코드와의 연결

| 기존 구현 | 재사용/보완 |
|---|---|
| domain/technology.py의 prerequisites 및 SourceRef | 기존 추출 의미를 보존하고 출처·순서·대상을 재검증 |
| storage/schema.py의 entities/relations 테이블 | 물리 schema v1을 유지하는 것이 첫 설계 선택 |
| repository.py는 관계를 unresolved/target=null로 저장 | 조회 결과의 연결 상태는 동일 스냅샷에서 계산. 읽기 중 DB를 갱신하지 않음 |
| repository.citation_reader, answer_entity, snapshot context | SHA·byte·행·UTF-8 검증 및 고정 스냅샷 조회 재사용 |
| cli.py의 설정/출력/종료 코드 처리 | refs를 새 subcommand로 연결 |
| 이벤트 adapter는 합성 정의 추출만 제공 | 참조 추출, 이벤트 저장, 명시적 이벤트 색인 연결 추가 필요 |
| SearchService는 모든 entity row로 projection을 만들지만 허용 query kind는 technology | 이벤트 저장 후 기본 기술 검색에 이벤트가 섞이지 않도록 projection 범주를 명시적으로 제한 |

E-028은 누락·동명 prerequisite/event target을 함께 요구한다. 따라서 기술 구현만으로 TASK-015 전체를 완료하지 않는다.

## 3. 구현 범위와 순서

### A단계: 기술 선행 관계를 끝까지 연결

- 기존 스냅샷의 기술 정의와 prerequisites를 사용한다.
- 정적 ID, 직접 관계, 지정 깊이까지의 관계 조회를 제공한다.
- 중복된 관계 occurrence와 출처를 보존한다.
- 누락·동명·순환·깊이/개수 제한, JSON/text, 정확한 ID 선택을 구현한다.
- 기존 index/search/show/snapshots 동작과 schema v1을 유지한다.

### B단계: 이벤트 참조와 최소 저장·색인 연결

- 현재 event adapter가 지원하는 authored synthetic country_event/planet_event 정의를 재사용한다.
- 이벤트 정의 안의 지원 효과 위치에서 정적으로 명시된 이벤트 호출 ID만 추출한다.
- 이벤트 candidate/관계를 기존 entities/relations에 저장할 수 있는 제한된 저장 경계를 추가한다.
- index --include-events로 events/**/*.txt 수집을 명시적으로 선택하게 한다. 기존 index의 기본 기술 범위는 유지한다.
- 이벤트를 포함한 새 스냅샷에서도 기존 기술 검색·show가 동일하게 작동하도록 범주 혼입 회귀를 추가한다.
- 이벤트 refs의 첫 표시 이름은 검증된 ID를 기준으로 한다. 이벤트 이름 검색·전체 이벤트 상세 답변 일반화는 이번 완료 조건이 아니다.

이번 범위 밖: 역방향 참조, 경로 최적화, 연구 순서 추천, script_reference, 모든 도메인의 검색 연결, 증분/diff, AI, 웹/오버레이, 게임 엔진 평가. 이벤트의 미지원 구문은 원문·진단과 불완전 상태로 남긴다.

이벤트 지원 구문은 합성 계약이다. 실제 Stellaris 문법 전체를 지원한다고 표현하지 않으며, 실제 설치본 검증은 TASK-021에서 별도로 수행한다.

## 4. 제안 CLI

~~~text
stellaris-supporter --config ./config.toml refs demo_tech_c
stellaris-supporter --config ./config.toml refs demo_tech_c --depth 3
stellaris-supporter --config ./config.toml --format json refs demo_tech_c --snapshot <SHA256>
stellaris-supporter --config ./config.toml refs demo_tech_c --entity-key <ENTITY_SHA256>
stellaris-supporter --config ./config.toml index --include-events
stellaris-supporter --config ./config.toml refs authored.1 --kind event --depth 2
~~~

| 인자 | 제안 계약 |
|---|---|
| GAME_ID | 필수, 정확 ID. 이름/부분 문자열/오타 보정으로 엔티티를 선택하지 않음 |
| --kind | technology 기본값, B단계에서 event 추가 |
| --snapshot | 생략하면 요청 시작 시 active를 한 번 선택 |
| --entity-key | 선택적 SHA-256. 중복 정의를 사용자가 특정할 때 사용. GAME_ID/kind와도 일치해야 함 |
| --depth | 기본 1, 1~16. root 깊이 0, 직접 대상 깊이 1 |
| --limit | 기본 min(20, 설정 max_results), 1~100. 반환하는 관계 occurrence 수 기준 |
| --language | 기존 ko/en 옵션 재사용. 번역을 검증할 수 없으면 ID 표시 |
| --format | 기존 text/json 계약 재사용 |

새 relation type 선택 옵션은 첫 버전에 넣지 않는다. technology는 prerequisite, event는 event_reference로 고정한다. 옵션의 subcommand 전후 우선순위는 기존 CLI 계약과 동일하다.

루트 ID가 중복이면 임의의 첫 정의를 선택하지 않는다. partial과 bounded root_candidates를 반환하고 --entity-key 선택 방법을 안내한다. 후보가 잘리면 truncated도 표시한다. 엔티티 키를 지정해도 GAME_ID/kind 불일치나 다른 snapshot의 키는 거부한다.

## 5. 관계 추출 규칙

### 기술

기존 adapter의 prerequisites 규칙을 재사용한다. 새 추출 규칙으로 기존 의미를 조용히 바꾸지 않는다. 올바른 assignment block의 지원 literal과 정확한 원문 span을 보존한다. @변수 등 기존 adapter가 지원하지 않는 값, 비정상 연산자, 미종결 블록은 기존 진단을 보존한다.

조회 검증에서는 relations row의 target ID만 신뢰하지 않는다. 캐시의 해당 부모 기술 정의를 bounded AST로 확인하고, 원래 prerequisites의 순서·토큰·span이 row의 occurrence·target과 일치하는지 대조한다. 같은 파일의 다른 필드/주석에서 빌린 동일 문자열도 참조 근거로 인정하지 않는다.

### 이벤트

첫 authored synthetic 지원 위치는 이벤트 정의의 immediate 및 option 효과와, 그 안의 명시적으로 등록한 if/else_if/else/hidden_effect 블록이다. if/else_if의 limit는 조건 원문으로 보존하며 실행하지 않는다. option의 name/title 문자열은 호출로 취급하지 않는다.

지원 호출은 효과 위치의 country_event/planet_event assignment block이며, 직접 id 필드가 정확히 하나이고 기존 event adapter의 qualified literal ID 정책에 맞아야 한다. 부모 이벤트 정의 자체의 id는 호출 edge가 아니다. 파일 namespace를 근거로 생략된 namespace를 자동 보충하지 않는다.

- 정적 대상 ID마다 별도 event_reference와 occurrence를 만든다.
- 호출 전체 span, id 값 span, 원본 scope/조건을 가리키는 context SourceRef를 보존한다.
- days 등 부가 표현식은 원문으로만 유지하고 발생 시점/확률을 계산하지 않는다.
- 동적·누락·중복 id, 지원하지 않는 호출형/컨테이너, parser 오류는 진단과 참조 추출 불완전 상태로 남긴다. 가짜 target 문자열이나 edge를 만들지 않는다.
- 문자열/주석 안의 호출 모양 텍스트를 참조로 추출하지 않는다.
- ID를 확정할 수 없는 표현은 target_game_id NOT NULL인 관계 테이블에 억지로 넣지 않는다. 진단과 원문으로 보존한다.

지원하지 않는 효과 컨테이너를 발견했으면 그 안을 임의의 게임 scope로 해석하지 않는다. 관계가 하나도 없어도 해당 정의의 참조 coverage가 불완전하면 ok/완전한 빈 관계로 보고하지 않는다.

## 6. 연결 상태와 탐색

| 상황 | 반환 동작 |
|---|---|
| 같은 snapshot·예상 kind에 대상 정의가 정확히 1개 | resolved, target_entity_key 설정 |
| 대상 정의가 0개 | unresolved, target_entity_key=null. 선택 색인 안에서 미해결이라는 뜻 |
| 대상 정의가 2개 이상 | ambiguous, target_entity_key=null, bounded 후보·출처 표시. 임의 확장하지 않음 |
| 동적/미지원 참조 구문 | 원문·진단과 partial coverage, 정적 대상 edge를 발명하지 않음 |
| root 없음 | 지원 범위 안이면 not_found |
| root는 있으나 직접 관계가 없음 | complete coverage일 때 ok, 빈 edges |
| 선택 snapshot이 event 색인을 포함하지 않음 | unsupported + scope 안내. 현재 게임 폴더를 읽어 보충하지 않음 |
| 순환 발견 | cycle 진단과 닫히는 연결 표시, 무한 확장 방지 |

관계는 원문의 방향을 유지한다. BFS로 최소 깊이와 반환할 유한 부분 그래프를 구성하고, 수집한 검증 그래프에 iterative DFS의 현재 경로/완료 집합을 적용해 순환을 확인한다. 반복 방문만으로 순환을 선언하지 않는다. A→B, A→C, B→D, C→D의 다이아몬드는 순환이 아니다.

순환의 모든 가능한 경로를 열거하지 않는다. 수집된 부분 그래프에서 확인한 대표 경로/닫히는 edge를 제한적으로 보고한다. 순환이 있다는 사실만으로 정적 관계가 잘못되었다거나 실제 이벤트가 무한 실행된다고 판단하지 않는다.

depth 경계 너머의 관계를 생략했으면 partial/truncated와 사유를 표시한다. 순환을 찾지 못했다는 결과는 요청한 반환 그래프에 한정하며 전체 게임 그래프에 순환이 없다는 뜻이 아니다. 동일 엔티티의 중복 edge도 occurrence와 SourceRef는 유지하되 엔티티 확장은 반복하지 않는다.

## 7. 응답 계약 제안

새 ReferenceQuery / ReferenceService / ReferenceEnvelope를 추가한다. 기존 검색 Query와 AnswerEnvelope에 그래프 필드를 무리하게 섞지 않는다.

| 필드 | 내용 |
|---|---|
| schema_version / command | 응답 버전 1 / refs. SQLite schema 버전과 별개 |
| status | ok, partial, not_found, unsupported, error |
| query | game_id, kind, selected entity key, depth, limit, language, 요청 snapshot |
| context | 실제 고정 snapshot, snapshot 상태, 버전/분기·근거, 정적 분석 문맥, 지원 참조 범위/정책 |
| root / root_candidates | 유일한 루트 또는 선택이 필요한 중복 정의 목록 |
| nodes | 검증된 entity_key, game_id, kind, 최소 depth, 정의 SourceRef, 선택적 이름·이름 출처 |
| edges | edge_id, occurrence, from_entity_key, relation_kind, target_kind, target_game_id, target_entity_key|null, status, 대상 후보, SourceRef, 호출/조건 context refs |
| cycles | 반환 그래프 안에서 확인한 bounded 순환 설명 |
| diagnostics | 누락/모호성/미지원/범위/한도/손상 원인 |
| truncated / truncation_reasons | 깊이·결과 수·탐색 예산 등 생략 여부와 원인 |
| traversal | 실제 방문 수, 검사한 관계 수, 검사한 깊이, cycle 검사 범위 |

edge_id는 기존 row의 snapshot/from_entity_key/occurrence에 안정적으로 연결하며 새 DB 기본키를 추가하지 않는다. status는 조회 시 재검증한 상태다. 저장 row의 resolved 표지만으로 검증을 건너뛰지 않는다.

출력은 BFS 깊이 → from kind/ID/정의 출처 → 원문 occurrence → 대상 ID 순서 등 고정된 정렬로 결정한다. SQL 조회 순서에 기대지 않는다. JSON은 객체 하나, text는 기존 제어 문자 이스케이프를 재사용한다.

예시의 가상 데이터: demo_tech_c → demo_tech_b → demo_tech_a. depth 2이면 두 관계를 근거와 함께 표시한다. demo_missing은 unresolved, 동일 ID의 정의가 여러 개면 ambiguous다. 이 예시는 실제 게임 기술이나 검증 결과가 아니다.

## 8. 자원 한도와 오류

다음 수치는 첫 설계값이며 성능 달성 수치가 아니다. 구현 시 계약·경계 테스트와 함께 고정한다.

- 요청 depth 1~16, 결과 관계 1~100, query 길이는 기존 512자 및 설정 query_chars 적용.
- 탐색은 요청 전체에서 최대 256개 고유 엔티티 확장, 1,024개 관계 row 검사. SQL에서 bounded batch/LIMIT+1을 적용한다. 전체 entities().fetchall()로 그래프를 만들지 않는다.
- 관계별 대상 후보는 요청 전체 결과 예산을 공유하며, 후보만 늘어나 출력/메모리 한도를 우회하지 못하게 한다.
- 출처 읽기는 기존 파일 최대 16MiB, bounded citation cache/line 검증을 재사용한다. 요청 전체에서 실제 재로딩한 원본 byte 누적 64MiB 상한을 제안한다. 재로딩도 계상한다.
- parser byte/token/node/depth/diagnostic 한도를 늘려서 입력을 우회하지 않는다. 참조 검증용 parsed source 재사용은 요청 내부의 검증된 문맥에만 묶는다.
- 전체 직렬화 출력은 기존 CLI 1MiB 상한을 적용한다.

| 경우 | 응답/종료 |
|---|---|
| 정상, not_found, unsupported, 표시된 의미상 partial | 0 |
| 잘못된 ID/형식/depth/limit/snapshot/key | 2 |
| 설정·선택 snapshot 없음 | 3 |
| 설정된 query/result 예산 위반, provenance/parser hard limit, 출력 hard limit | 4 |
| 원본·cache·구조/관계 위조 | SOURCE_CHANGED 등 기존 의미에 따라 5 |
| DB/schema 실패 | 6 |
| 취소 | 130 |

사용자가 지정한 depth/result 수나 정상 탐색 예산 때문에 관계를 생략한 경우는 표시된 partial/truncated로 종료한다. 무결성·보안 한도 실패는 partial 동의로 우회하지 않으며 검증된 사실처럼 일부 결과를 내보내지 않는다. 일부 snapshot 자체가 partial이면 그 상태를 응답에 전파한다. 순환 진단만 있고 모든 요청 관계가 검증·반환됐다면 순환 자체로 truncated를 켜지 않는다.

## 9. 저장·정책·호환성

- 조회는 snapshot/캐시에서만 수행한다. live 게임 파일 재파싱, DB 재색인, 네트워크, 모델 호출은 없다.
- 관계의 source_ref는 해당 부모 정의와 AST 참조 위치에 속해야 한다. 같은 파일/다른 부모·다른 snapshot·잘못된 kind·변조된 occurrence/target/span을 거부한다.
- 저장된 edge 누락도 완전 성공으로 숨기지 않는다. 검증한 부모 AST의 정적 참조 목록과 저장 목록을 예산 내에서 대조하며, 다 확인하지 못한 경우 complete라고 표시하지 않는다.
- 조회 중 active가 바뀌어도 기존 선택 snapshot에 남는다. source/target/후보/번역은 전부 그 snapshot에 속해야 한다.
- event 포함 여부, 참조 추출 버전/지원 컨테이너 정책을 SnapshotPolicy identity에 반영한다. 정책이 바뀌면 새 snapshot을 만든다. 기존 ready snapshot의 내용은 수정하지 않는다.
- 기술만 있는 구 snapshot은 기술 refs에 재사용하고, event refs는 scope 부족을 표시한다. read-only 구 snapshot을 임의로 업그레이드하지 않는다.
- 기존 schema v1의 테이블/열로 수용하는 것이 우선이다. event candidate 저장은 kind별 명시적인 검증/직렬화 경계를 추가한다. TechnologyCandidate의 prerequisites 속성을 모든 kind가 갖는다고 가정하지 않는다.
- 기존 기술 entity identity/JSON 구조를 불필요하게 변경하지 않는다. 조건·호출 context proof는 검증 가능한 candidate payload 또는 원본 AST에서 도출하고, SQL 필드에 무근거 문자열을 복제하지 않는다.
- 물리 schema 변경이 불가피하면 구현을 확대하기 전에 데이터 계약·ADR·migration/재색인·복구 방안을 함께 설계한다.
- SearchService의 기본/technology 조회는 기술 row만 projection에 넣는다. 이벤트는 이번 refs 전용 직접 조회로 제공하며, event를 기술용 AnswerService에 전달하지 않는다.

## 10. 파일별 변경 계획

| 파일 | 예정 역할 |
|---|---|
| 신규 src/stellaris_supporter/references.py | typed query/result, snapshot 고정, 대상 해석, bounded 그래프·순환·예산 |
| 신규 src/stellaris_supporter/domain/references.py | source-bound 정적 참조 추출·부모 AST 대조, 이벤트 지원 경로 |
| storage/repository.py | 정확 root/edge/target bounded 조회, 이벤트 저장 입구, citation context 재사용 |
| domain/event.py / generic.py | 필요 최소의 source-bound event 연결. 기존 정의 검증은 유지 |
| cli.py | refs 인자·JSON/text·종료 코드·출력 예산 |
| cli_index.py | opt-in events 수집, 정책 버전·diagnostics/partial 유지 |
| retrieval.py | mixed-kind 저장 시 기존 기술 검색의 범주 격리 |
| 신규 tests/test_references.py | 관계 해석·중복·누락·그래프·스냅샷·손상/한도 |
| 신규 tests/test_reference_extraction.py | tech/event AST 위치·동적·위조·미지원 경로 |
| 신규 tests/test_cli_refs.py | 실제 subprocess 종단·오류·JSON/text·opt-in 색인 |
| 기존 storage/domain/CLI/retrieval 테스트 | 회귀 유지 및 연결 영향 검사 |
| docs/CLI.md, DATA_CONTRACTS.md, PARSING.md, ARCHITECTURE.md, DECISIONS.md | 구현과 같은 변경에서 refs 계약·범위·새 결정 반영 |
| harness 원장 및 evidence/session | 실제 구현 시작/검증/완료 시에만 근거와 함께 갱신 |

새 런타임 라이브러리는 필요하지 않다. uv 전환, 검색 가속, UI, 모든 도메인 공통화는 이번 refs 구현의 선행 조건으로 묶지 않는다.

## 11. 필수 테스트 행렬

| 묶음 | 사례 및 기대 |
|---|---|
| 기본 | 한 관계, 빈 관계, 연쇄, 분기, 반복 occurrence, 안정 정렬, 정확 ID/선택 key |
| E-028 기술 | 없는 대상, 같은 파일/서로 다른 파일의 동명, 같은 ID의 다른 kind, 중복 root, partial 정의 |
| E-028 이벤트 | missing/ambiguous event target, 완전한 qualified ID, 별도 namespace, source/call id 혼동 방지 |
| E-029 | 자기 순환, 두 노드/긴 순환, 이벤트 순환, 다이아몬드 비순환, depth 정확 경계/한 단계 초과 |
| 이벤트 문법 | immediate/option/허용 조건 컨테이너, guard 원문, 문자열/주석 fake 호출, 동적/중복 id, 미지원 scope 진단 |
| 출처 | BOM/CRLF/한글, 정확 byte·행·UTF-8 경계, field/value/부모 일치 |
| 위조 | SQL 관계 target/occurrence/span/status/대상 key 변조, 다른 부모/파일 ref 대여, edge 삭제, cache SHA 손상 |
| snapshot | stable/beta 및 명시 snapshot 분리, 조회 중 active 전환, 구 기술 snapshot event scope 부족 |
| 예산 | 모든 상한의 경계·초과, 후보 폭증, 출력 1MiB, parser hard stop과 의미상 partial 구별 |
| 종단 | init→index→refs, opt-in event index→event refs, text/JSON 의미 일치, 단일 JSON·종료 코드·제어 문자 |
| 회귀 | mixed snapshot의 기존 기술 search/show, 이전 snapshot 재사용, 취소·쓰기 실패 시 active 보존, 원본 파일 byte 무변경 |

합성 fixture만 커밋한다. 실제 게임 설치 없이 자동 검사를 실행하고 실제 설치본 수용 검증과 구별한다. 입력 오류를 테스트 삭제·skip·무조건 예외 무시로 통과시키지 않는다.

## 12. 구현 전달 순서와 완료 기준

1. 계약/합성 실패 테스트를 먼저 작성하고 구현 브랜치에서 TASK-015를 doing으로 바꾼다. 이번 계획 브랜치에서는 바꾸지 않는다.
2. A단계 PR: 기술용 root/relations 조회 → 무결성·누락/모호성 → 직접 refs → bounded 다단계/순환 → CLI. 기술 범위 구현 근거만 기록한다.
3. A단계 검토·병합·main 검사 후 B단계 PR: 이벤트 추출/저장/opt-in 색인 → event refs → 혼합 범주 회귀.
4. 전체 E-028/E-029 기술·이벤트 평가 및 기존 회귀를 실행한다. Windows/Linux의 실제 workflow/checkout SHA와 테스트·Ruff·harness 근거를 확인한다.
5. 검토·실제 main 통합 근거를 갖춰 TASK-015 완료 및 F-010의 검증 범위를 기록한다. F-011은 TASK-016 diff가 남으므로 in_progress를 유지한다. 실제 게임 버전/호환성을 검증한 것으로 바꾸지 않는다.

예정 검증 명령(이번에는 제품 구현 검증으로 실행하지 않음):

~~~text
python -m pytest tests/test_reference_extraction.py tests/test_references.py tests/test_cli_refs.py
python -m pytest
python -m ruff check .
python scripts/check_harness.py
~~~

완료는 기능 구현, E-028/E-029의 실제 pass 근거, 기존 회귀, 문서 계약, 검토·main 통합까지 충족했을 때다. 계획 문서만으로 구현이나 평가를 완료하지 않는다.
