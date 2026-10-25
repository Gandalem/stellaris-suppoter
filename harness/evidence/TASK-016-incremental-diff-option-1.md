# TASK-016 — 1안 증분 색인·스냅샷 비교

2026-10-21 / Asia/Seoul. 시작 HEAD dc6f031c1eca781b53ad224bc5c881cc01465938, 브랜치 task/TASK-016-option-1. 기존 TASK-015의 로컬 제품·문서·테스트 변경을 그대로 보존했다. 사용자 지시로 Git 통합은 별도 작업이다.

## 구현

- incremental.py: SHA/정책별 파일 산출물, 등록 dataclass JSON codec, snapshot-neutral SourceRef/Context 및 event guard 재연결. 기존 private blob cache/settings 사용, 구형·손상·과대 캐시는 원본 재처리.
- cli_index.py: 추가/수정/삭제/동일 파일 집계, 실제 parsed/reused 수, --full, 번역 catalog·표시 이름 재구성, 같은 immutable snapshot의 전체 추출 일치 대조.
- storage/repository.py: immutable manifest, 전체 제품 대조, 게시 전/활성 전환 시 파일 membership·SHA 재수집과 expected_active 전환 보호. 기본 activate 호출은 기존 계약 유지.
- comparison.py: 양쪽 snapshot 고정, semantic ordered field 비교, 위치/스냅샷 ID 제외, 보수적 duplicate 대응, 기술·이벤트 관계 및 번역/이름 변경, 출처 전후 연결, 관심 ID/범주·페이지 필터, 분석/출력 예산.
- cli.py: diff 및 index --full, text/JSON, processing 요약. 기존 검색·상세·refs 흐름을 재사용한다.
- 파서/어댑터·분석 문맥이 달라지면 정의 비교를 생략하고 파일·정책 차이를 표시한다. 한쪽만 수집한 이벤트를 추가/삭제로 표시하지 않는다. 번역 파싱이 불완전하면 번역 삭제/이름 변경을 단정하지 않는다.

런타임 의존성과 DB schema 변경 없음. Diff 비교는 source cache를 사용하며 live 원본이나 active pointer를 변경하지 않는다. 실제 원본의 주석/공백·표현식·중복·순서를 구별하며 실제 엔진 의미를 계산하지 않는다.

## 실행 순서

사용자 요청대로 모든 기능을 먼저 작성하고 구현 100%를 보고한 뒤 테스트·정적 검사·필수 검수를 시작했다. 전체 도메인 회귀, 전체 성능 benchmark, 새로운 OS 환경 검사로 확대하지 않았다.

환경: Windows / Python 3.12.14 / SQLite 3.53.1 / pytest 9.1.1 / Ruff 0.16.10. PYTHONUTF8=1, console 검사에는 .venv/Scripts PATH를 사용했다. 테스트는 합성 bytes와 임시 디렉터리만 사용한다.

| 실행 | 실제 결과 |
|---|---|
| python -m pytest tests/test_incremental_diff.py -q --basetemp .venv/task016-essential-first --tb=short --junitxml .venv/task016-essential-first.xml | exit 0, 21 passed / 30.51s |
| python -m pytest tests/test_incremental_diff.py tests/test_cli_vertical.py tests/test_references_cli.py tests/test_package.py -q --basetemp .venv/task016-essential-final --tb=short --junitxml .venv/task016-essential-final.xml | exit 0, 96 passed / 141.87s: 신규 26 + 기존 CLI 61 + refs CLI 5 + package 4 |
| python -m pytest tests/test_incremental_diff.py -q --basetemp .venv/task016-comparison-final --tb=short --junitxml .venv/task016-comparison-final.xml | exit 0, 27 passed / 41.38s; 마지막 불완전 번역 보강 포함 |
| python -m pytest tests/test_normative_document_integrity.py -q --basetemp .venv/task016-docs-final --tb=short | exit 0, 12 passed / 0.05s |
| python -m ruff check . | exit 0, All checks passed |
| python scripts/check_harness.py | exit 0, harness_valid=true, 20 features/32 tasks/48 evaluations |
| python -m stellaris_supporter --help | exit 0, diff 포함 실제 명령 표시 |
| git diff --check | exit 0 |

신규 테스트 초기 Ruff 형식 지적(한 줄 복수 문장/정렬)은 수정했다. 제품 수용 테스트 실패는 없었다. 검수 중 불완전 번역을 삭제/이름 변경으로 단정하는 경로를 보강하고 최종 27개로 확인했다. 96개 실행과 마지막 27개는 중복 사례가 있으므로 합산하지 않는다. 마지막 제품 변경은 comparison.py의 불완전 번역 처리이며 최종 27개 실행에 포함했다. 전체 저장소 테스트를 실행했다고 주장하지 않는다.

## 수용 근거

E-030: 변경 파일만 파싱하고 동일 파일 재사용, 실제 warm 경로의 parse 차단 실험, 정책 변경 시 재처리, 삭제 반영, 동일 입력의 증분/전체 및 새 저장소 전체 결과의 snapshot ID/엔티티 payload 일치, 한국어 표시 이름 재구성과 이벤트 guard/citation 새 snapshot 연결. 예전 snapshot refs 연결도 유지한다.

E-031: staging 이후 추가/수정/삭제에 대한 활성 전환 차단, 다른 작업이 먼저 활성화한 snapshot을 현재 작업이 덮어쓰지 않음. 파일 재수집과 CAS를 실제 합성 테스트로 확인했다. OS 파일시스템 전체의 원자적 snapshot 보장은 범위 밖이다.

Diff: 비용/참조 상태 전후, 추가/삭제, 주석·공백·위치 변경 분리, 중복 정의/반복 필드, 번역 간접 참조 이름 변경, event guard, 색인 범위/처리 정책 차이, 관심 ID/페이지/분석 한도, 저장 정의 누락과 최종 출력 한도에서 abstain, 실제 subprocess text/JSON과 기존 search/show/refs 영향 경로를 확인했다.

## 완료와 별도 작업

TASK-015 및 TASK-016은 사용자 승인에 따른 로컬 기능 완료로 기록한다. 이 상태는 원격 PR/CI/main 통합 완료를 뜻하지 않는다. 커밋·push·PR·병합·배포는 실행하지 않았다. 실제 관리창/오버레이는 공통 서비스 연결 이후의 별도 작업이다. 실제 게임 원문·설치 호환성·다른 OS 실행 근거는 추가하지 않았다. 다음 원장 작업은 TASK-017이며 자동 시작하지 않는다.
