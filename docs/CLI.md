# CLI 계약 v0.1

명령: **init, doctor, index, search, show, refs, diff, snapshots**. 기술 색인·검색·정적 상세와 기술/이벤트 참조 조회를 제공한다.

## 공통 실행

`stellaris-supporter` 또는 `python -m stellaris_supporter`. 전역 `--config PATH`, `--format text|json`, `--game-root PATH`, `--data-dir PATH`, `--language ko|en|korean|english`는 subcommand 앞뒤에 사용할 수 있습니다. 같은 옵션을 앞뒤 모두 지정한 경우 **subcommand 뒤 값이 우선**합니다. 설정 파일 TOML보다 CLI override가 우선이며, TOML 상대 경로는 설정 파일 폴더, CLI 상대 경로는 현재 작업 폴더 기준입니다.

| 명령 | 인자 | 구현 범위 |
|---|---|---|
| init | --game-root PATH [--data-dir PATH] | 기존 파일 덮어쓰기 없는 안전한 TOML 작성, network=false |
| doctor | 없음 | 설정/경로/Python/SQLite/FTS5 네트워크 비활성 진단; 전체 index는 안 함 |
| index | [--allow-partial] [--include-events] [--full] | 기술·한/영 현지화 색인. include-events를 지정하면 events/**/*.txt의 지원 이벤트 정의·참조도 포함 |
| search TEXT | [--kind technology] [--snapshot SHA] [--limit 1..100] | SearchService의 정확 ID·한/영 이름·짧은/부분 검색·동명 정의 |
| show GAME_ID | [--kind technology] [--snapshot SHA] [--limit 1..100] | **정확한 게임 ID만** AnswerService의 R1–R6 검증을 거쳐 정적 표현식·SourceRef 반환 |
| refs GAME_ID | [--kind technology\|event] [--snapshot SHA] [--entity-key SHA] [--depth 1..16] [--limit 1..100] | 정확 ID의 선행 기술/정적 이벤트 호출, 중복 정의 선택·출처·순환·제한 |
| diff BEFORE AFTER | [--kind technology\|event] [--game-id ID] [--include-source-changes] [--limit 1..100] [--offset 0..100000] | 두 스냅샷의 내용·관계·번역·파일 변경 비교 |
| snapshots | [--limit 1..100] [--offset 0..100000] | 제한된 read-only 목록, active·status·문맥·버전 |

아직 없는 `ask/sync/save/simulate/serve`는 제공하지 않습니다. 명시적 snapshot 없이 search/show/refs하면 요청 시작 시 active가 고정됩니다. snapshot이 없으면 종료 3입니다.

참조 조회 방향과 화면 연결 흐름은 [2안](REFS-OPTION-2.md), 세부 설계는 [정적 참조 조회](REFS.md)를 참조하세요.

## 합성 테스트에서 사용하는 호출 형태

Linux:
```sh
stellaris-supporter --config ./private/config.toml init --game-root '/path/to/synthetic-game' --data-dir '/path/to/private-data'
python -m stellaris_supporter --config ./private/config.toml --format json doctor
python -m stellaris_supporter --config ./private/config.toml --format json index
stellaris-supporter --config ./private/config.toml --format json search '합금 연구'
stellaris-supporter --config ./private/config.toml --format json show demo_tech
stellaris-supporter --config ./private/config.toml --format json snapshots
```
Windows PowerShell (경로·인용은 개인 환경에 맞게 교체):
```powershell
python -m stellaris_supporter --config '.\private\config.toml' init --game-root 'C:\synthetic game' --data-dir 'C:\private data'
python -m stellaris_supporter --config '.\private\config.toml' --format json index
python -m stellaris_supporter --config '.\private\config.toml' --format json search 'demo_tech'
python -m stellaris_supporter --config '.\private\config.toml' --format json show 'demo_tech'
```
위 PATH는 설명용 플레이스홀더입니다. 실제 개인 절대 경로나 게임 원문을 공개 evidence에 포함하지 않습니다.

## 안전성·출력·오류

index는 안전한 inventory SHA → 실제 live source O_NOFOLLOW(가능한 OS) 파일 캡처 SHA/크기·경로 검증 → 결정적 정책 identity → parser/adapter·localisation → `stage_from_results()` → `activate(...,sources=...)`로 실행합니다. config·DB·cache는 game_root 밖의 명시적 data_dir에만 기록합니다. 동일한 정상 snapshot은 재활성화 시에도 **현재 live manifest와 캐시**를 다시 검증합니다. `--allow-partial`은 parsing/translation partial에만 적용하며 PATH_REJECTED·SOURCE_CHANGED·LIMIT_EXCEEDED를 우회할 수 없습니다. 원본의 같은 경로를 공격적으로 교체하는 OS 수준 TOCTOU 위험은 완전히 제거한 것은 아닙니다.

JSON 모드는 stdout에 유일한 객체 하나(기본 schema_version 1, command, status, diagnostics 포함), 한국어를 ensure_ascii=False로 출력합니다. 오류·로그는 stderr와 구분하고 안전 오류는 내부 traceback이나 개인 원문을 출력하지 않습니다. `doctor`는 기존 운영자를 위한 로컬 진단 계약을 보존하므로 **명시한 개인 경로를 출력할 수 있습니다**. 공개 증거에는 `DoctorReport.to_dict(public=True)` 등 별도 비식별 직렬화를 사용하세요.

검색 hit와 show facts는 상대 경로, source ID·SHA, byte_start/byte_end, 실제 line_start/line_end, snapshot_id를 구분합니다. `raw_expression`은 엔진 계산이 아니라 **검증된 원문 표현식**입니다. E-026은 직접 만든 합성 fixture만 사용합니다.

| 종료 코드 | 의미 |
|---|---|
| 0 | 정상, not_found, 명시 승인된 partial |
| 2 | 잘못된 인자/질의, 미지원 명령 |
| 3 | 설정·경로·snapshot 부재 |
| 4 | 안전 경계·입력 한도 위반 |
| 5 | 원본 변경·decoding/parse로 인한 활성화 불가 |
| 6 | SQLite·schema·저장 또는 알 수 없는 안전한 내부 오류 |
| 7 | 후속 provider 실패 — TASK-013에서는 사용하지 않음 |
| 130 | 사용자 취소 |

구현 결과는 `harness/evidence/TASK-013-cli-vertical-slice.md`에 CI 실제 실행을 확인한 다음 연결합니다. 동일 입력·동일 정책은 동일 snapshot ID를 생성하며 절대경로/시간을 ID에 혼합하지 않습니다.

## TASK-013 R1–R5 안전 경계 (PR #25 검토 후속)

- `--allow-partial`은 일반적으로 미완성인 파싱·번역에만 적용합니다. 기술 lexer/parser의 `LIMIT_EXCEEDED`, `PARSE_DEPTH_LIMIT`, `PARSE_NODE_LIMIT`, `PARSE_DIAGNOSTIC_LIMIT` 및 localisation resolver의 확장 depth/visit/output 제한을 만나면 기존 active를 보존하고 종료 **4**로 실패합니다. 이미 존재하는 partial snapshot도 재활성화 전에 이 조건을 다시 검사합니다.
- Inventory의 파일 크기·파일 개수·SHA 청구는 `common/technology/**/*.txt`, `common/scripted_variables/**/*.txt`, `common/component_templates/**/*.txt`, `common/component_sets/**/*.txt`, 두 등록된 무기 CSV, `localisation/korean/**/*.yml`, `localisation/english/**/*.yml`만 포함합니다. 그 밖의 일반 파일은 해시·수집하지 않지만 경로, symlink/reparse 및 디렉터리 탐색 `max_entries` 보안 검사 대상입니다. 모든 지원 파일의 합계에 `max_files/total_bytes`가 적용됩니다.
- `search`·`show`는 설정 `limits.query_chars`, `limits.max_results`와 서비스 절대 상한 **512자/100개**를 모두 검사합니다. 인자 자체가 잘못됐거나 서비스 상한을 위반하면 `QUERY_INVALID`/**2**; 서비스 계약 내에서 TOML 한도를 초과하면 `LIMIT_EXCEEDED`/**4**를 반환합니다. `--limit` 생략 시 search는 `min(20, configured max_results)`, show는 `min(100, configured max_results)`를 사용합니다. snapshot·kind·검색 결과 의미는 기존 SearchService/AnswerService를 유지합니다.
- `snapshots`의 **기본 text** 출력은 JSON과 동일하게 각 항목의 `snapshot_id/active/status/context_kind/branch/game_version/created_at/checked_at`를 표시합니다. 알 수 없는 버전·시각은 `unknown`으로 표시하며 `limit/offset/truncated`도 출력합니다.
- 게임·모드 유래의 사용자 제어 문자열(검색명, 정의 필드·진단·경로 등)은 **text 출력에서만** ESC/C0/C1/Unicode bidi 등의 nonprinting 문자를 가시적으로 `\\xNN`, `\\uNNNN`로 이스케이프합니다. SourceRef, 원문 캐시, JSON 값의 데이터 의미를 변경하지 않습니다. 정상 한/영 이름은 그대로 표시합니다.

상기 계약은 `harness/evidence/TASK-013-review-followup.md`에 기록한 합성 검증 범위에 한하며, 실제 게임 설치본이나 OS-level hostile same-path TOCTOU 보증을 뜻하지 않습니다.


## refs 사용

```sh
stellaris-supporter --config ./private/config.toml refs demo_tech --depth 3
stellaris-supporter --config ./private/config.toml --format json refs demo_tech --entity-key ENTITY_SHA
stellaris-supporter --config ./private/config.toml index --include-events
stellaris-supporter --config ./private/config.toml refs demo.1 --kind event --depth 3
```

ID는 대소문자와 원래 표기를 그대로 비교한다. 이름은 search에서 찾고 선택한 ID와 entity_key를 전달한다. 루트 동명 정의는 `partial`과 candidates로 반환하며 하나를 선택할 때까지 확장하지 않는다. 대상이 없으면 unresolved, 여러 개면 ambiguous이며 해당 경로를 확장하지 않는다. ambiguous edge의 candidate_entity_keys는 최대 2개이고, 추가 후보가 있으면 candidates_truncated=true다. 해당 ID로 refs를 다시 호출하면 limit 범위의 정의 목록을 확인한다.

기본 depth=1, 최대 16. 기본 limit=min(20, configured max_results), 최대 100이며 반환 edge 수에 적용한다. depth/result/node/scan 한도는 partial, truncated, truncation_reasons에 표시한다. 순환은 반환 그래프의 cycles에 표시하고 각 노드를 한 번만 확장한다. 동일 노드로 합쳐지는 경로는 순환으로 세지 않는다. 입력·종료 코드·text 제어문자 이스케이프는 공통 계약을 따른다.

기존 기술 스냅샷도 기술 refs에 사용할 수 있다. 이벤트 범위가 없는 스냅샷의 event 요청은 unsupported다. include-events는 별도 정책 identity를 사용하며 기본 기술 색인 identity는 유지한다. 이벤트 파싱/참조 범위가 부분적이면 기존 allow-partial 규칙이 적용된다. search/show의 기술 범위는 유지한다.


## 증분 색인과 변경 비교

`index`는 파일 SHA·추출 정책이 같은 파일의 중간 결과를 재사용한다. 이전 형식에 산출물이 없거나 손상되면 해당 파일을 다시 처리한다. `index --full`은 재사용을 끄고 전체를 파싱하며, 스냅샷 식별자에 처리 방식을 넣지 않는다. 같은 ID가 이미 있으면 저장 결과와 대조하고 재사용한다. 원본/기존 스냅샷을 삭제하는 옵션이 아니다.

색인 응답 processing은 mode(incremental/full/full_fallback/snapshot_reuse), parsed_files, reused_files, file_changes(added/modified/removed/unchanged), reprocess_reason을 제공한다. 전체 스냅샷 재사용 시 parsed_files=0이다. 게시 전 및 활성 전환 직전에 허용 파일 목록·해시를 다시 확인한다. 수집 중 추가/변경/삭제 또는 다른 작업의 active 교체는 SOURCE_CHANGED/종료 5로 중단한다.

```sh
stellaris-supporter --config ./private/config.toml index
stellaris-supporter --config ./private/config.toml index --include-events --full
stellaris-supporter --config ./private/config.toml diff BEFORE_SHA AFTER_SHA
stellaris-supporter --config ./private/config.toml --format json diff BEFORE_SHA AFTER_SHA --game-id demo_thrusters
stellaris-supporter --config ./private/config.toml diff BEFORE_SHA AFTER_SHA --include-source-changes --limit 20 --offset 0
```

비교 목록은 정의·현지화·파일 순서로 표시한다. 정의에는 전후 표시 이름/정의 ID/출처와 변경 필드·관계를 묶는다. snapshot/정의 ID와 행 위치는 내용 비교에서 제외한다. 중복 정의는 내용·출처로 확실한 대응만 연결하고 남은 후보는 ambiguous로 함께 표시한다. 주석·공백·행 이동은 내용과 구별하며 출처만 바뀐 정의는 include-source-changes에서 표시한다. 번역 파싱이 불완전하면 번역 삭제나 표시 이름 변경을 단정하지 않는다.

범주·게임 ID 필터는 정의와 관련 현지화 목록에 적용한다. 이 경우 파일별 목록은 생략하며 summary.files는 공통 지원 파일 전체의 집계다. Python DiffQuery.interest_ids는 고정 카드 등에서 ID 목록을 전달하는 인터페이스다. 이벤트를 양쪽 모두 수집한 경우에만 이벤트를 비교한다. 파서/어댑터 또는 분석 문맥이 다른 경우 정의 비교를 생략하고 원본 파일과 정책 차이를 표시한다.

목록 페이지 제한은 truncated/result_limit이며 전체 분석 완료 여부(summary_complete)와 구별한다. 분석 한도에 걸리면 불완전한 양쪽 정의를 추가·삭제로 비교하지 않고 partial/analysis_limit을 반환한다. 하드 출처·최종 JSON 한도는 error/abstained다. diff는 active pointer를 변경하지 않는다.

새 색인은 파일별 영구 번역 카탈로그와 검색 투영을 재사용합니다. `processing`에는 파싱/재사용 파일 수와 파생 결과 재사용 수, `storage`에는 번역 항목 수와 불완전 파일 수를 제공합니다. 표시 언어만 바꾸면 같은 스냅샷을 이용합니다. 기존 스냅샷은 계속 조회할 수 있습니다. 상세: [로컬 데이터 저장 2안](DATA-STORAGE-OPTION-2.md).


기술 카드 기본 비용의 숫자 해석은 GUI 표시 계층에서 제공한다. CLI 답변의 원래 표현식·출처·지원 상태는 유지한다. 색인은 공통 변수 파일을 같은 스냅샷에 포함하고, 이전 스냅샷 카드는 사용자가 직접 갱신할 때까지 유지한다.


무기 자료는 기존 index 동작에서 함께 수집한다. 무기 검색과 상세는 관리창에서 제공하며 CLI search/show의 기본 기술 계약을 유지한다. 개별 무기 실행 파일 진단은 --diagnose-weapon과 별도 개인 설정/결과 파일을 사용한다.

개인 설정의 기존 무기 카드 읽기 진단은 desktop 실행 파일의 `--diagnose-weapon-card <ID> --preferences <개인 설정 경로> --diagnostics-output <개인 결과 경로>`를 사용한다. 카드를 새로 만들지 않고 같은 작업 스레드/요약 흐름을 읽은 뒤 종료한다. 결과는 개인 경로에 저장한다.
