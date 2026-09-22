# 2026-09-22 TASK-031 containment follow-up

사용자 제공 리뷰에서 PR #6 merge 이후 synthetic generator의 추가 네 가지 containment 반례가 재현됐음을 확인했다.

## 수행

- PR #5 head의 generator 방어 구현을 확인.
- current main을 기준으로 새 branch `fix/generator-containment-regressions` 생성.
- PR #5를 통째로 병합하지 않고 필요한 generator 방어만 선별 통합.
- main의 ownership marker 및 기존 configuration/doctor 수정 유지.
- 리뷰에서 실패한 네 사례를 pytest 회귀 테스트로 추가.
- PR #7 생성.

## 검증

Candidate `a5f3ca88c6b6b94e975a881e58bdfacac4db3883`:
- Ubuntu Python 3.11.16: 56 passed, synthetic corpus 15 passed, Ruff/harness success.
- Windows Python 3.13.15: 56 passed, synthetic corpus 15 passed, Ruff/harness success.
- Documentation harness: both platforms success.

중간 run에서는 TASK-031을 재개방하면서 F-002가 verified로 남은 원장 불일치를 harness가 차단했다. F-002를 in_progress로 교정하고 재검증했다.

## 인계

E-047 candidate validation은 pass. 하지만 reviewer가 merge approval을 보류한 상태이므로 PR #7은 병합하지 않는다. TASK-031=blocked, blocker는 explicit merge approval 대기. 승인 후 main merge + main push CI를 확인해 최종 완료한다.
