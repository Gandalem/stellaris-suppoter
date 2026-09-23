# TASK-008 main integration evidence

날짜: 2026-09-23  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/14  
병합 commit: `3275aeabbfa51a249b3449c34ec192fbec966adb`

## Final reviewed head

- PR head: `9ad4e7f61344b6c6c7876ea505dca1c803ea6ebf`
- base: `959e3fc669c0927ed8eddec559bef055e155f253`
- pre-merge test candidate: `0feb546ab45b8820bea555c9583d90412f789471`
- 기술 재검토에서 R1-R3 해결 확인 후 병합 보류 해제.

## Main push CI

Package and tooling run `35868827744`:
- Ubuntu / Python 3.11.16: 174 passed, technology adapter 20 passed, Ruff/harness success.
- Windows / Python 3.13.15: 174 collected, 171 passed + 3 intentional skips, technology adapter 20 passed, Ruff/harness success.
- Windows skips are the existing POSIX-only inventory/lexer tests.

Documentation harness run `35868827712`:
- Ubuntu success.
- Windows success.

## Closure

- TASK-008 technology adapter is merged and verified on actual main CI.
- E-014 remains pass.
- F-005 remains in_progress because other domain-adapter work remains outside TASK-008.
- latest_game_version remains null because no real Stellaris installation/version was inspected.
- No next task is activated by this closure change.

TASK-008 done.
