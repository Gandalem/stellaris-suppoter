# TASK-015 — Static references 개발 명세

작성일: 2026-10-21. 이 파일은 2안 구현 범위를 기록하며 진행 상태는 [작업 원장](../tasks.json)이 기준이다.
관련 기능 F-010/F-011, 평가 E-028/E-029. 선행 작업 TASK-014.
기준 main: dc6f031c1eca781b53ad224bc5c881cc01465938 (PR #36 병합본).

## 범위·계약

상세 명령·응답·추출 규칙·예산·파일별 변경·테스트 행렬은 [refs 개발 계획](../../docs/REFS.md)을 따른다. 이 문서는 기존 규범을 대체하지 않으며 구현 PR에서 CLI/데이터 계약과 함께 확정한다.

- A단계: 기존 기술 prerequisites 관계를 정확 ID와 선택 snapshot에서 조회하고, 누락·동명·순환·깊이/개수 제한·출처·CLI를 연결한다.
- B단계: 명시적으로 지원하는 합성 이벤트 참조와 최소 event 저장/index --include-events 연결을 추가한다. 기존 기술 검색에 이벤트가 섞이지 않아야 한다.
- E-028에는 prerequisite/event 대상이 모두 포함되므로 A단계만으로 TASK-015 전체를 완료하지 않는다.
- schema v1과 구 기술 snapshot을 우선 보존한다. 조회 중 DB/게임 파일을 변경하거나 live 파일로 근거를 보충하지 않는다.
- 역방향 탐색·script_reference·모든 도메인 검색·diff·AI·UI·엔진 계산은 이번 범위 밖이다.

## 수용 조건

1. 루트·대상은 (snapshot, kind, game_id, entity_key)로 구별하고 duplicate occurrence를 보존한다.
2. missing/ambiguous 대상의 연결을 발명하지 않으며, 미지원/불완전 참조 추출을 정상 빈 결과로 숨기지 않는다.
3. 관계 row를 원본 AST의 해당 부모·토큰·순서·span과 대조하고 cache SHA·행·UTF-8·snapshot 위조를 거부한다.
4. 탐색·후보·출처 읽기·출력에 요청 공통 예산을 적용한다. 순환/다이아몬드·깊이 경계를 구별한다.
5. 기술 및 이벤트 합성 E-028/E-029, CLI 실제 subprocess와 기존 기술 search/show 회귀가 통과한다.
6. 실제 게임 호환성·이벤트 실행·연구 가능 여부를 검증한 것으로 표현하지 않는다.

## 검증·종료

사용자 승인 순서는 전체 기능 구현 → 구현 100% → 합성/CLI 회귀·Ruff·harness·검수 → 수정이다. 실제 실행 결과는 evidence/session에 기록한다. TASK-015의 main 통합과 후속 작업은 별도 승인 범위다.

F-011은 TASK-016 diff까지 관련되므로 이 작업만으로 verified로 올리지 않는다. 다음 구현 작업 시작 전에는 PR #36 이후 실제 main CI의 job checkout SHA와 선행 상태를 확인한다.
