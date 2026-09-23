# 2026-09-23 TASK-006 PR #12 resource follow-up

PR #12 review에서 lexer의 per-character position map 및 unbounded token accumulation이 P2 merge blocker로 재현됐다.

## 수행

- 기존 E-009/E-010 correctness evidence 유지.
- position map 제거, streaming line/column cursor로 변경.
- long token searches를 regex/bytes.find 기반으로 변경.
- max_bytes/max_tokens lexer budgets 추가.
- byte budget은 decode 전, token budget은 token allocation/next long-token scan 전에 적용.
- LIMIT_EXCEEDED explicit result.
- 1 MiB comment/whitespace/string, token flood, exact/over limit, limit validation 회귀 추가.
- POSIX tracemalloc allocation regression 추가.
- 대형 pytest parameter에 explicit short ids 추가.

## 검증

Final head `ba130da911b0082b858e06e9c04a008993540ca6`.

Package push run 35804610541:
- Ubuntu: 122 passed, lexer 22 passed, Ruff/harness success.
- Windows: 122 collected, 120 passed + 2 intentional skips; lexer 21 passed + POSIX-only allocation probe 1 skipped; Ruff/harness success.

Documentation harness PR run 35804614559: Ubuntu/Windows success.

## 인계

TASK-006 doing 유지. E-009/E-010 pass 유지. F-004 in_progress. Reviewer 재검토/main integration 전 TASK-007 시작 금지.
