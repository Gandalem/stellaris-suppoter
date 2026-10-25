# TASK-015 — 2안 참조 조회 개발

2026-10-21 / Asia/Seoul. 작업자 Codex, self_review.
시작 commit dc6f031c1eca781b53ad224bc5c881cc01465938, 작업 브랜치 task/TASK-015-refs-option-2. 신규 commit 없음.

소유자가 2안 개발을 명시적으로 요청했다. 전체 기능을 작성하고 구현 100%를 보고한 뒤에 테스트와 검수를 시작했다. 승인 범위는 기술/이벤트 정적 refs, CLI, 향후 관리창/오버레이의 공통 서비스다. 기존 사용자 문서 변경은 보존했다.

구현 파일: src/stellaris_supporter/references.py, domain/event_references.py, storage/reference_reader.py와 기존 repository/cli/cli_index/retrieval 연결. 기존 파서·SQLite v1과 기술 snapshot identity를 활용했다. GUI toolkit과 runtime dependency 추가 없음.

실행: 전체 회귀 980 passed / 9 existing environment skips (295.28s). 그 뒤 scan-budget 보강 참조/CLI 63 passed 및 기술 ID 경계 2 passed. Ruff와 harness 검사 통과. 현재 제품 코드의 최종 참조/CLI 일괄 실행은 65 passed / 53.48s. 모든 실패/수정 기록은 [근거](../evidence/TASK-015-refs-option-2.md)에 기록한다. 전체 회귀의 실행 코드와 마지막 보강의 검증 범위를 구분한다.

E-028: 기술/이벤트 누락·동명/모호함을 보존. E-029: 기술/이벤트 순환·깊이 제한과 다이아몬드 구별. 원문 파일/행/byte/순서, snapshot 고정·동시 active 교체·카드/이동/원문 패널, 위조·손상·자원 한도, 실제 CLI subprocess와 기존 기술 검색/show를 합성 입력으로 확인했다.

TASK-015 doing, F-010/F-011 in_progress 유지. E-028/E-029는 로컬 합성 실행 근거로 갱신한다. F-011의 TASK-016 diff는 별도 범위다. 다음 단일 작업은 이 변경의 독립 검토와 요청된 통합 절차이며, 후속 개발을 자동 시작하지 않는다. 커밋·push·PR·병합·배포 요청은 없었다. 실제 게임 설치 호환성, 실제 관리창/오버레이 제작은 이 세션에 포함되지 않는다.

사용자 작업 규칙: 명시적 개발 요청 시 시작, 범위 안 자율 진행, 큰 변경은 먼저 제안, 기능 구현 100% 뒤 검증/검수, 실제 진행 보고, 기존 코드 우선, 사용자 변경 보존, 커밋/푸시/병합/배포 범위 구분.
