# 2026-09-22 TASK-031 containment follow-up

사용자 제공 review에서 PR #6 merge 이후 synthetic generator의 추가 containment 반례가 재현됐고, 이를 current main 위에서 수정·재검증했다.

## 수행

- PR #5 head의 generator 방어 구현을 확인.
- current main을 기준으로 `fix/generator-containment-regressions` branch 생성.
- PR #5를 통째로 병합하지 않고 필요한 generator 방어만 선별 통합.
- main의 ownership marker 및 기존 configuration/doctor 수정 유지.
- 리뷰에서 실패한 네 사례를 pytest 회귀 테스트로 추가.
- PR #7 생성.
- 기술 검토에서 reviewed head `9f61a0a727c4c47d507b84600b18b5611e59b277` 병합 허용 의견 확인.
- PR #7 실제 main merge commit `b583f89de389ce838987b8c3e5b6a2fd0e7c58b9` 확인.

## 검증

PR candidate:
- Ubuntu Python 3.11.16: 56 passed, synthetic corpus 15 passed, Ruff/harness success.
- Windows Python 3.13.15: 56 passed, synthetic corpus 15 passed, Ruff/harness success.
- Documentation harness: both platforms success.

Actual main merge commit:
- Package and tooling run 35742263578: Ubuntu/Windows success, 56 tests each, synthetic corpus 15 tests each, Ruff/harness success.
- Documentation harness run 35742263716: Ubuntu/Windows success.

## 하네스 교정

재개방 중 F-002가 verified로 남아 있거나 TASK-031 상태와 active_task가 불일치한 중간 커밋은 harness가 실패시켰다. 최종 main merge 검증 후 TASK-031=done, F-002=verified, active_task=null, next_task=TASK-004로 복구한다.

## 비차단 후속

손상된 manifest가 JSON object가 아닌 경우 내부 AttributeError/traceback이 날 수 있다는 review 피드백을 기록한다. 파일 보호 실패는 재현되지 않았으므로 TASK-004 진입을 막지는 않지만 generator 오류 정규화 후속으로 남긴다.

## 인계

TASK-031 done. E-047 pass. F-002 verified. 다음 작업은 TASK-004 Safe inventory.
