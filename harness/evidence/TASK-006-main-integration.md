# TASK-006 main integration evidence

날짜: 2026-09-23  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/12  
병합 commit: `1c8247ee2eea330b6444de33fdc2cb03a82abb91`

## Main push CI

Package and tooling run 35815351949:
- Ubuntu/Python 3.11.16: 130 passed, lexer 30 passed, Ruff/harness success.
- Windows/Python 3.13.15: 130 collected, 127 passed + 3 intentional skips; lexer 28 passed + 2 intentional skips; Ruff/harness success.
- Windows skips:
  - existing POSIX-only inventory surrogateescape filename regression.
  - POSIX-only lexer tracemalloc peak threshold.
  - POSIX-only lexer escape-dense wall-clock threshold.

Documentation harness run 35815351946:
- Ubuntu success.
- Windows success.

## 결론

PR #12의 R1 memory, R2 escape-dense string CPU, R3 many-comment CPU follow-up을 포함한 최종 head `9c9f1111cc672c05e1e848e14a1c2537574d55a2`가 main에 병합됐다.

TASK-006 done. E-009/E-010 pass 유지. F-004는 TASK-007/E-011~013이 남아 있으므로 in_progress 유지.

실제 Stellaris files는 사용하지 않았고 latest_game_version은 null 유지.
