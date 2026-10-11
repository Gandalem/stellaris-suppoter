# 2026-10-11 TASK-009 PR #17 R1-R4 follow-up

Base main: e49ab75153d695b92614b2db3a0e54136f148e37.
Old reviewed head: 1a260d2c045410781eeb1fa8dfb76c8b44a226d0.

Fixed linear prefix parsing, protected dynamic and unsupported escape regions, PARSING.md duplication, per-record budget. Added 38 parametrized review regression cases in tests/test_localisation_review_regressions.py; retained the original 50 localisation tests.

Code/test/doc head: 10dd9b721e13819cfa764ab30d6fe26e15ac2499.
Test-merge: 889ef8b85321a45ebcb68a39fc48f1f0f24429e3.
PR Package and tooling CI 38126968416: Ubuntu Python 3.11.17 268 passed; Windows Python 3.13.15 265 passed + 3 prior skips; Ruff/harness both passed.
PR Documentation harness CI 38126968353: both OS passed.

Standalone CPU microbenchmark (separate Linux Python 3.13.5) and full rationale recorded in harness/evidence/TASK-009-review-followup.md. No real game files or personal paths read.

Final operational state:
- E-015/E-016/E-017: pass, historical evidence preserved and follow-up linked.
- TASK-009: doing, pending independent re-review and actual main CI.
- F-006/F-005: in_progress.
- latest_game_version: null.
- TASK-010: todo; not started.
- PR #17: not merged; no review threads resolved.
