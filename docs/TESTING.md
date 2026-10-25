# 테스트 전략

문서 검사, 검사기 자체 테스트, 제품 테스트, 실제 게임 검증을 구별합니다. 패키지·설정/doctor, 합성 corpus, 안전한 inventory·버전 증거, lexer/ordered parser, technology adapter에는 구현과 합성 회귀 테스트가 있습니다. 현지화 reader/resolver는 합성 E-015~017 회귀가 구현되어 PR #17의 실제 `main` 병합 커밋 CI에서 검증됐습니다.

PR #19 보완 합성 회귀는 R1에서 원본/복제 동일 bytes 경로 바꿔치기·루트 변경·source ID 충돌·symlink, R2에서 NFC 한국어/분해형 한글 자모/Latin combining/BOM/CRLF/원문 byte 위치, R3에서 정책 JSON 1MiB 정확 경계·초과·중첩·노드 수, R4에서 DB cache pointer 위조와 과거 정상 snapshot 읽기를 검증합니다. R5는 ADR 테이블 행 연속성과 합성 DB 크기별 `PRAGMA quick_check` 대비 read-only schema preflight 비용을 별도 **비차단** 방식으로 측정합니다. 실게임 검색 warm p95나 실제 파일시스템 공격 완전 방어를 이 측정 결과로 보장하지 않습니다. 현지화 reader/resolver의 합성 E-015~017 검증은 유지되며 TASK-010은 SQLite 저장소와 스냅샷 원자성에 대한 별도 E-018/E-019 부정·경계 회귀를 추가합니다. 이는 DB Repository 단위 검증으로, DB를 포함한 검색·인용/CLI 종단 연결이나 실제 게임 설치본 검증 완료를 뜻하지 않습니다. [평가 사례](../harness/evals.jsonl)는 실행 근거가 있는 항목만 pass로 기록합니다.

TASK-011 검색 후보에는 `tests/test_retrieval.py`의 합성 E-020/021/022 정답·정규화·FTS 비활성·SQL 메타문자·스냅샷 격리 및 cache SHA 검사가 추가됩니다. 검색 PR의 Ubuntu/Windows 합성 회귀 통과 및 평가 결과는 `harness/evidence/TASK-011-retrieval.md`에 기록합니다. 실제 기능 종료는 별도 독립 리뷰·실제 main 병합·main push CI 이후에만 판단합니다. 실게임 검색 검증이나 공식 p95 보장은 아닙니다.

## 테스트 계층

| 계층 | 검증 대상 | 데이터 |
|---|---|---|
| harness | JSON 원장, ID·의존성·근거·문서 링크 | 작은 임시 문서 저장소 |
| unit | 기존 lexer·AST·technology adapter·inventory 테스트와 후속 localisation·정규화 검사 | 직접 만든 문자열·bytes |
| integration | 구현된 모듈의 합성 통합 검사; inventory → parser → DB → search → citation 전체 연결은 후속 | 합성 디렉터리 corpus |
| CLI | 종료 코드, stdout JSON, stderr 로그, 설치 후 명령 | 임시 가상환경·합성 corpus |
| security | 경로·권한·한도·통신·정보 노출·중단 | 악조건 합성 입력 |
| evaluation | 검색 정답·근거 위치·보류·버전 격리 | 버전이 고정된 합성 정답 세트 |
| local acceptance | 실제 설치 데이터의 경로·구문·도메인 차이 | 사용자 PC, 비공개 원문 |

## fixture 정책

모든 커밋 가능한 fixture는 직접 만든 합성 데이터입니다. 실제 게임·모드·번역·세이브를 복사하지 않습니다. 이름은 demo_/synthetic_ 계열이고 origin: synthetic을 명시합니다. TASK-002 corpus는 [tests/fixtures/synthetic](../tests/fixtures/synthetic/README.md)에 있으며 manifest가 상대 경로·scenario·encoding·byte size·SHA-256을 고정합니다. generator 출력과 committed bytes를 Linux/Windows에서 비교합니다. TASK-018이 이후 평가 runner를 연결합니다.

필수 시나리오: 정상·중복·혼합 블록, 문자열 속 brace/#, escaped quote, BOM/CRLF, 미종결 문자열/brace, 비UTF-8, 깊이·파일 한도, 미지원 표현식, 한국어/영어/ID fallback, 번역 순환·중복, 같은 ID의 다른 snapshot, 빈/짧은/특수 질의, 누락 참조·그래프 순환, 파일 추가/삭제/변경, 색인 중 파일 변경, 취소·DB 실패, 입력 지시문·개인 경로 노출.

## 실행 규칙

unit/integration/evaluation은 네트워크를 막고 실제 사용자 홈·게임 폴더에 접근하지 않습니다. 임시 디렉터리와 명시적 경로를 사용합니다. seed·locale·timezone·정렬·시간 주입을 고정합니다. filesystem·환경·network 대체는 pytest의 monkeypatch 등 공식 API를 참고합니다([S-06](SOURCES.md)).

한 테스트가 다른 테스트의 DB·상태를 재사용하지 않습니다. 실제 시간·외부 모델 출력·최신 공지에 단위 테스트 정답을 의존시키지 않습니다. Windows 경로·잠금, Linux 경로·permission을 각각 확인합니다. OS가 다른데 실행했다고 주장하지 않습니다.

## 현재 명령

```sh
python -m pytest
python -m ruff check .
python scripts/check_harness.py
python scripts/generate_synthetic_corpus.py --output ./tmp-synthetic
```

마지막 명령은 검사용 임시 출력 생성이며 기존 비어 있지 않은 디렉터리는 기본적으로 덮어쓰지 않습니다. 소유권이 확인된 출력에만 `--force` 갱신을 허용하며, manifest 검증 실패는 stderr의 `error:` 진단과 종료 코드 `2`로 보고하고 기존 내용을 변경하지 않습니다. TASK-018 이후 평가 runner의 정확한 명령을 추가합니다. Python API의 parser/search/answers와 TASK-013 브랜치에서 연결 중인 index/search/show **CLI 명령**은 별도의 E-026 합성 subprocess 검증으로 구분합니다. 미실행 명령이나 실제 게임 통합을 완료로 주장하지 않습니다.

## 품질 게이트

수정한 기능의 실패 재현 → 관련 unit/integration → 전체 회귀 → 인용/안전/버전 평가 → 패키지 스모크 순서입니다. 한도·보안·unknown 처리의 회귀는 필수입니다. coverage는 참고 지표이며 100% 숫자만으로 정확성을 보장하지 않습니다. v0.1 전체 합성 필수 평가가 통과하기 전 verified로 바꾸지 않습니다.

실패한 테스트를 삭제·skip하거나 broad exception으로 숨겨 통과시키지 않습니다. flaky test는 seed와 원인을 기록하고 수정합니다. 미실행·환경상 불가·실제 실패를 각각 not_run/blocked/fail로 구분합니다.


PR #21 R1~R3 follow-up은 합성 테스트에서 dynamic §/£/bracket/escaped dollar, 정적 다단계/영어 참조의 전체 SourceRef, 중복·순환·누락 참조의 partial 반환, 다른 entity/key/snapshot 출처의 별칭 위조와 조작된 byte span을 평가합니다. 기존 E-020~022와 34개 검색 테스트를 그대로 유지하고 추가 테스트를 양 OS Package CI에 포함합니다. R4 FTS 탐지/중복 SQL 제거는 검색 가속을 증명하지 않으며, 초기 SQL-only microbenchmark는 FTS on/off E2E 비교가 아닙니다. 독립 리뷰 및 실제 병합 이전에 TASK-011 done/F-008 verified를 선언하지 않습니다.

TASK-012 E-023–025는 `tests/test_answers.py`의 저작 합성 원본으로 field/value 정확한 byte·line 인용, BOM/CRLF, 한국어→영어 종속 출처, 고의적인 cache SHA 손상, 동적 표현식 보류, 없는 ID/필드, 중복 정의, stable/beta snapshot 격리와 active 변경을 평가합니다. `harness/evidence/TASK-012-static-answers-citations.md`에 실제 CI와 평가 증거를 따로 기록하며 CI 전에는 not_run을 유지합니다. 실제 설치본과 게임 엔진 의미는 미검증입니다.

TASK-012 R1–R5 재검토 합성 회귀는 `tests/test_answers.py`에 서로 다른 파일로부터 대여한 Field/Value SourceRef, 저장 JSON의 필드 구문/occurrence 위조, Combat Computers/Chance Discovery 정확 검색과 미지원 의도, Query 유효성 우선순위, 100건 공통 예산·cache.read 호출 수, raw value 512/513 bytes를 포함합니다. 후속 재평가 근거는 `harness/evidence/TASK-012-review-followup.md`를 참고합니다.

**TASK-013 E-026 CLI contract**

`tests/test_cli_vertical.py`는 실제 `python -m stellaris_supporter` 하위 프로세스를 통해 합성 game root에서 init→doctor→index→한국어·영어·ID 검색→exact ID show→개별 SourceRef 원문 span→snapshots→동일 index 재사용을 검사합니다. 설정 덮어쓰기·중첩 data_dir·symlink·없는 snapshot·잘못된 Query·인코딩 partial·실제 원본 read-only 및 stdout JSON 파싱을 부정 회귀로 검사합니다. R1–R6 기존 448 Ubuntu/445 Windows +3 skips 회귀는 변경하거나 skip하지 않습니다. CLI 실제 CI 결과와 미검증 취소/동시 writer/OS TOCTOU 범위는 [evidence](../harness/evidence/TASK-013-cli-vertical-slice.md)에 구분 기록합니다.

E-026 저작 합성 후보는 PR #25 코드 head `e65a9cac1d05ef7a55b3d7510ef66a4fce3322a2`, PR test-merge `38b6bb2f177d134e0346993c7904fcf764982bbc`에서 Ubuntu 486 passed, Windows 483 passed + 기존 3 skips, Ruff·harness·Documentation harness 양 OS 성공했습니다. 기존 Ubuntu 448개 테스트를 모두 유지하며 신규 합성 38개를 추가했습니다. 정확한 검증 범위·미검증 게임 호환성은 `harness/evidence/TASK-013-cli-vertical-slice.md`를 참조하세요. 이후 evidence 커밋의 최신 CI는 별도로 검증해야 합니다.


TASK-013 PR #25 R1–R5 추가 합성 테스트: 실제 subprocess와 작은 제어 한도의 in-process 검증으로 parser/lexer 진단, 실제 parser depth, localisation depth/visits/output, 정상 partial 및 hard-stop 구분, 비대상 .bin 크기·개수 미청구, 대상 초과와 디렉터리 집계·symlink, 설정된 search/show 길이·결과 한도와 종료 코드, 다중 snapshot 기본 text의 active/branch/status/created/checked/pagination, ESC/CR/BS/bidi text 경계·한/영/JSON 의미 보존을 검사합니다. 선행 실패 테스트 실행과 수정 CI는 `harness/evidence/TASK-013-review-followup.md`에 기록합니다. 실패를 skip하거나 전체 baseline을 제거하지 않습니다.

## 후속 Windows 오버레이 테스트 계획

TASK-032/E-048의 Windows 게임 창 기술 실험과 TASK-030/E-046의 정식 OVL-01~06 검증을 구별합니다. 합성 테스트는 상태 전이·단축키 충돌·서비스 검색/출처 일치·입력 차단 방지 논리를, 실제 Windows 수동 테스트는 게임 전경에서 표시·클릭/키 입력 통과·DPI·다중 모니터·최소화/종료 안전 숨김을 검증합니다. 개인 원문·설치 경로·화면 캡처를 공개하지 않습니다. [오버레이 기준](OVERLAY.md).


## TASK-015 참조 조회

소유자 지시에 따라 기능 구현 100% 뒤에 참조 테스트와 검수를 시작했다. `tests/test_references.py`와 `tests/test_references_cli.py`는 E-028의 기술/이벤트 missing·ambiguous, E-029의 기술/이벤트 cycle·depth와 다이아몬드 구별, BOM/CRLF/한글 출처, 중복 occurrence, snapshot 변경 중 고정·카드/이동·원문 패널, 저장 관계/출처/cache 변조, 누적 자원 한도, opt-in event 색인, 기존 search/show 격리, 실제 subprocess 출력을 확인한다. `harness/evidence/TASK-015-refs-option-2.md`가 이 개발의 실행 기록이다.

**TASK-033 필수 로컬 검사**

전체 기능 작성 후 `tests/test_desktop.py`와 영향 CLI/answer/index 회귀를 실행했다. Qt 검사는 `.[desktop]`에서 실행하며 기본 CLI 설치에서는 optional dependency 검사가 skip될 수 있다. `scripts/native_desktop_smoke.py`는 자체 창 API 확인이고 실제 게임 입력 수용과 구분한다. 근거는 [TASK-033](../harness/evidence/TASK-033-desktop-option-1.md).

**로컬 데이터 저장 2안:** `tests/test_disk_storage.py`는 파일별 저장/진단 스트리밍, 누락 의존관계·언어 대체·중복, 재시작 투영과 손상 복구, 전체 번역 비교, 취소/실패 재시도, writer 충돌, 색인 중 이전 스냅샷 검색을 검사한다. 인코딩 손상은 partial 동의로 우회하지 않는다. 실제 설치 결과와 겹치는 실행 묶음은 [근거](../harness/evidence/TASK-033-data-option-2.md)에 기록한다.
