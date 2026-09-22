# TASK-005 PR #11 review follow-up evidence

날짜: 2026-09-23  
리뷰 전 head: `e248f695eea4557cd984b89aefb216e42ff3dff5`  
후속 기능 candidate: `49352f945e889c6759337a48ecb15d4718742751`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/11

## 리뷰에서 재현된 계약 누락

기존 E-007/E-008 성공 evidence는 삭제하지 않는다. PR #11 검토에서 E-007의 두 추가 반례가 재현됐다.

1. metadata branch가 존재하지만 stable/beta로 해석되지 않을 때 이를 metadata 없음과 동일하게 취급해 user-reported branch로 fallback.
2. metadata/user version 또는 build conflict, unsupported branch의 원본 값이 resolved result/to_dict에서 소실.

## 수정

### Observation 모델

선택 결과와 원본 evidence를 분리하기 위해 `VersionObservation`을 추가했다.

필드:
- field: game_version|build_id|branch
- source: metadata|user_reported
- raw_value
- normalized_value|null
- disposition: selected|corroborating|conflict|suppressed_by_metadata|unrecognized

`VersionEvidence.to_dict()`는 persistence/private evidence representation으로 observations를 포함한다. `to_public_dict()`는 raw observations를 제외한다. Diagnostic 메시지는 raw version/build/branch 값을 포함하지 않는 정적 문구를 유지한다.

### Unsupported metadata policy

문서의 "metadata가 없을 때만 user-reported fallback" 정책을 구현한다.

- metadata branch absent + valid user branch → user_reported 선택 가능.
- metadata branch present + valid stable/beta → metadata 선택.
- metadata branch present but unrecognized + valid user branch → branch=unknown, branch_source=unknown.
- 이때 metadata observation은 unrecognized, user observation은 suppressed_by_metadata.
- BRANCH_UNKNOWN 및 BRANCH_USER_FALLBACK_BLOCKED diagnostic으로 선택 정책을 명시한다.

## 회귀 테스트

기존 13개 versioning 테스트에 review follow-up 6개가 추가되어 총 19개가 실행된다.

- unsupported metadata + user stable.
- unsupported metadata + user beta.
- version conflict raw observations serialization.
- build conflict raw observations serialization.
- unsupported branch raw label persistence.
- public serialization raw observation omission.

## CI

Package and tooling PR run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35751962279

| 환경 | 전체 pytest | versioning | Ruff | harness |
|---|---:|---:|---|---|
| Ubuntu / Python 3.11 | 100 passed | 19 passed | success | success |
| Windows / Python 3.13 | 99 passed + 1 existing POSIX-only inventory skip (100 collected) | 19 passed | success | success |

Documentation harness run 35751962314도 Ubuntu/Windows 모두 success.

## 상태

E-007 pass로 복구. E-008 기존 pass 유지. TASK-005는 reviewer 재검토 및 실제 main 병합 전까지 doing. F-003은 in_progress. latest_game_version=null.
