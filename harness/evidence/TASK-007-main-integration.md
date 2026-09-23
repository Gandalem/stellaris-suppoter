# TASK-007 main integration evidence

날짜: 2026-09-23  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/13  
병합 commit: `959e3fc669c0927ed8eddec559bef055e155f253`

## Final reviewed head

- PR head: `149a36e8983eb299feddafc0d95c064ecc67ac60`
- base: `1c8247ee2eea330b6444de33fdc2cb03a82abb91`
- pre-merge test candidate: `9c0e457a8cc83f0e9179185eed5ac051c30baaa6`
- R1-R4 기술 재검토에서 병합 보류 해제.

## Main push CI

Package and tooling run `35858348427`:
- Ubuntu / Python 3.11.16: 154 passed, parser 24 passed, Ruff/harness success.
- Windows / Python 3.13.15: 154 collected, 151 passed + 3 intentional skips, parser 24 passed, Ruff/harness success.
- Windows skips are the existing POSIX-only inventory/lexer checks.

Documentation harness run `35858348284`:
- Ubuntu success.
- Windows success.

## Feature/evaluation closure

- TASK-006 main integration already complete.
- TASK-007 ordered AST/parser implementation is now merged to main.
- E-009, E-010, E-011, E-012, E-013 are pass.
- F-004 requirements are satisfied by the synthetic corpus + lexer/source spans + ordered AST/parser evidence.
- F-004 can move from in_progress to verified.
- latest_game_version remains null because no real Stellaris installation/version was inspected.

TASK-007 done.
