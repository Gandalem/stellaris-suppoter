# TASK-015 — 2안 정적 참조 조회 실행 기록

2026-10-21, Asia/Seoul. TASK-015/F-010/F-011, E-028/E-029.
브랜치 task/TASK-015-refs-option-2; 시작 dc6f031c1eca781b53ad224bc5c881cc01465938.

## 작업 순서와 범위

소유자가 2안 구현을 명시적으로 요청했다. 기술/이벤트 refs, opt-in 이벤트 색인, CLI, UI 독립 조회·이동·출처·snapshot 고정 카드 인터페이스를 모두 작성한 뒤 기능 구현 100%를 보고하고 검증을 시작했다. 구현 전에 테스트·검수·lint를 실행하지 않았다. 기존 2안 문서와 초기 설계 변경은 보존했다. 신규 런타임 라이브러리와 schema migration은 없다.

## 현재까지 실제 실행

환경: Windows, Python 3.12.14, SQLite 3.53.1, pytest 9.1.1, Ruff 0.16.10. 데이터는 직접 작성한 합성 bytes/임시 디렉터리다. .venv/Scripts를 PATH 앞에 두고 PYTHONUTF8=1을 사용했다. pytest 임시 경로는 .venv 아래 매번 별도 폴더를 사용했다.

- 첫 참조 테스트: 42 passed, 2 failed. 이벤트 제목 localisation-key 경고가 참조 coverage까지 부분 상태로 만들던 처리를 구별했다.
- 기술/이벤트+CLI: 49 passed, 이후 저장 byte budget·cache/이벤트 부정 사례를 추가해 56 passed.
- 검수 보강: guard 원문의 반복 복제에 추출 중 공통 byte budget 적용; 잘못된 API 입력이 unbounded 오류 응답으로 반사되지 않도록 수정; kind 교차 연결 차단·동시 active 변경·카드 고정 포함.
- 62개 추가 회귀 첫 실행: 61 passed, 1 failed. compact JSON의 공백에 의존하던 비교를 JSON 필드 비교로 고쳤고 관련 2 cases passed.
- 첫 전체 실행: 970 passed, 9 skipped, 4 failed / 285.24s. 신규 문서 heading 3개와 refs help에 대한 이전 기대값 1개가 원인. 해당 계약 테스트를 갱신해 16 passed / 0.87s.
- Ruff: All checks passed. harness 검사: harness_valid=true, features=20/tasks=32/evaluations=48.

## 전체 회귀와 마지막 보강

`python -m pytest -q --basetemp .venv/refs-full-final --tb=short --junitxml .venv/refs-full-final.xml`: exit 0, **980 passed, 9 skipped / 295.28s**. 989개 수집. 기존 POSIX 전용 3개 및 이 Windows 실행자의 symlink 권한 부족 6개를 건너뛰었다. 새 skip은 추가하지 않았다. 이 실행은 마지막 scan-budget/ID 경계 보강 직전의 코드로 collection/import되었다.

마지막 보강은 두 가지다. source proof로 검사한 대상 정의의 관계도 요청 공통 scan budget에 포함한다. ID가 없는 event는 partial로 남기되 ID가 없는 technology는 거부해 기술 저장 경계를 보존한다. 보강 후 참조/CLI **63 passed / 82.76s**, ID 경계 **2 passed / 3.17s**. 이 후속 코드의 전체 989+3개 회귀를 다시 실행했다고 주장하지 않는다. 영향 범위인 참조/CLI의 최종 65개 합성 사례는 별도 기록한다.

## 평가 근거

- E-028: 기술/이벤트 missing·ambiguous 대상, 같은/다른 파일의 중복 정의 선택, kind 교차 연결 차단, 지원 범위 없는 event snapshot을 구별했다.
- E-029: 기술 자기/두 노드 순환 및 이벤트 순환, 기술/이벤트 depth 제한, 최소 BFS depth, DAG 다이아몬드 비순환, node/result/scan 한도를 확인했다.
- SourceRef: BOM/CRLF/한글 원본 위치와 중복 관계 occurrence를 보존한다. nested 정의, 관계 추가/삭제·대상·line/span·candidate/key/status/guard 위조와 cache 손상은 facts 없이 중단한다.
- 저장과 CLI: opt-in event 정책 identity/ready reuse/partial 동의와 active 보존, 기존 기술 snapshot/검색/show, 실제 subprocess JSON/text/인자 오류, snapshot 교체 중 고정, navigate/source_text/card pin/refresh를 확인했다.

## 검수와 인계

검토자 self_review. 기능 구현 100% 이후에 소스 검토·부정 사례·정적 검사·전체 회귀를 진행했다. 발견한 localisation coverage, 반복 guard byte budget, invalid query reflection, scan-budget 계상, 기술 ID 저장 경계 문제를 수정했다. 새 런타임 의존성과 schema migration 없음. CLI와 데이터/파싱/아키텍처/결정/테스트 문서를 함께 갱신했다.

선행 게이트: PR36 main dc6f031c1eca781b53ad224bc5c881cc01465938. Package 39594572087 (Ubuntu job 119203581389 / Windows 119203581693), Docs 39594572102 (Windows 119203581294 / Ubuntu 119203581708) 모두 success 및 실제 checkout SHA를 개발 시작 전에 확인했다. 이는 선행 main의 근거이며 이번 로컬 코드의 원격 CI 결과가 아니다.

TASK-015 doing / F-010·F-011 in_progress를 유지한다. E-028/E-029는 이 로컬 합성 범위의 pass만 기록한다. 후속 독립 검토와 main 통합은 별도 단계이며 F-011은 TASK-016 diff까지 관련된다. 이 요청에서 커밋·push·PR·병합·배포는 실행하지 않았다. 실제 관리창·오버레이 제작은 후속이고 이번 변경은 공통 호출 인터페이스까지다. 실제 게임 원문·설치 호환성은 검사하지 않았다.

개인 경로·게임 원문·DB·세이브·키는 이 기록에 포함하지 않는다.


## 마지막 코드의 참조·CLI 일괄 실행

`python -m pytest tests/test_references.py tests/test_references_cli.py -q --basetemp .venv/refs-complete-final --tb=short --junitxml .venv/refs-complete-final.xml`: exit 0, **65 passed / 53.48s**. scan proof budget과 ID-less technology 거부를 모두 포함한 현재 제품 코드의 실행이다. 이전 전체 실행 이후 제품 코드는 이 두 보강만 변경했고 관련 회귀와 실제 CLI를 이 실행에 포함했다. 전체 980-pass 실행과 이 65-pass 실행은 서로 다른 checkpoint이며 단순 합산하지 않는다.
