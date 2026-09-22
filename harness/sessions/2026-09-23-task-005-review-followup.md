# 2026-09-23 TASK-005 PR #11 review follow-up

PR #11 review에서 unsupported metadata fallback과 conflict raw evidence loss가 재현되어 E-007을 재개방했다.

## 수행

- VersionObservation private evidence record 추가.
- metadata/user raw observation과 normalized/disposition 분리.
- unsupported metadata branch를 metadata absence와 구분.
- unsupported metadata가 존재하면 valid user branch fallback 차단.
- version/build conflict 원값을 persistence serialization에 보존.
- public serialization에서 raw observations 제외.
- 회귀 테스트 6개 추가.
- docs/UPDATES, DATA_CONTRACTS, TASK-005 계약 갱신.

## 검증

Candidate `49352f945e889c6759337a48ecb15d4718742751`:
- Ubuntu: 100 passed, versioning 19 passed, Ruff/harness success.
- Windows: 100 collected, 99 passed + 기존 POSIX-only inventory 1 skipped, versioning 19 passed, Ruff/harness success.
- Documentation harness: Ubuntu/Windows success.

## 인계

E-007 pass로 복구. E-008 pass 유지. TASK-005 doing / F-003 in_progress / latest_game_version=null. Reviewer 재검토와 main integration 전 TASK-006 시작 금지.
