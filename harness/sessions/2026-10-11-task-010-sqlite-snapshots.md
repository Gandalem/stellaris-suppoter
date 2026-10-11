# 2026-10-11 TASK-010 SQLite snapshots development

Date/time zone: 2026-10-11, Asia/Seoul.  
Agent: development, synthetic integration and CI checks; **self-check**, not independent technical approval.  
Branch: `task/TASK-010-sqlite-snapshots`. Base main commit: `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c`.  
Draft PR: https://github.com/Gandalem/stellaris-suppoter/pull/19

## Starting state, authority and dependencies

- PR #18 actually merged and main Package/Documentation CI successful. TASK-004/005/008/009 done, TASK-010 todo, E-018/E-019 not_run, F-007 planned, active_task null.
- Read AGENTS.md, SECURITY.md, REQUIREMENTS, DATA_CONTRACTS, ARCHITECTURE, OPERATIONS, TESTING, DECISIONS, BACKLOG, all related harness ledgers and existing technology/localisation data contracts. Chose separate `storage` package; no changes to game parsing/adapters or real files.
- TASK-010 doing and F-007 in_progress only on this branch.

## Actual implementation

- SQLite v1 eight typed snapshot-scoped FK tables, indexed duplicate-safe IDs, saved raw-source provenance and separate entity/localisation JSON.
- Canonical bounded source/policy identity, safe cross-platform relative path and Unicode policies; no clock, personal path or discovery-order nondeterminism.
- Private content-addressed cache SHA-256 verification; temporary+fsync+rename, no writes under game_root.
- SQLite WAL, FULL synchronous, FK ON, busy 250 ms, BEGIN IMMEDIATE writer/activation transaction and explicitly recoverable building state.
- Active pointer separate from immutable snapshot build status; staging failure, SQL insert failure, cancellation, cache corruption, locked DB, changed live source and partial security failure preserve previous active.
- `stage_from_results` propagates parser/adapter/localisation partial diagnostics and verifies source bytes/SourceRefs.
- No automatic migration, engine simulation, search ranking, FTS, CLI indexing, model connection or actual game compatibility.

## Verification

| Actual command / run | Environment | Observed | Result |
|---|---|---|---|
| `python -m pytest` in PR Package run `38131453597` | Ubuntu Python 3.11.17 / SQLite 3.45.1 | 337 passed (335 prior candidate +2 explicit failure injections), exit 0 | pass |
| `python -m pytest` in same run | Windows Python 3.13.15 / SQLite 3.50.4 | 334 passed + 3 prior POSIX-specific skips, exit 0 | pass |
| `python -m ruff check .` in same run | Ubuntu + Windows | all checks passed, exit 0 | pass |
| `python scripts/check_harness.py` in same run | Ubuntu + Windows | harness_valid true, exit 0 | pass |
| Documentation harness run `38131453587` | Ubuntu + Windows | successful jobs | pass |
| Local independent full suite in a separate checkout | not executed | not_run | no claim |
| Actual game installation and engine rules | not accessed | not_run | unknown |

Test-merge of the code+test candidate: `8df521765fd6b81b3c15f4fd492ff22dc8181614` (CI integration candidate, **not actual main merge**). Code/test/docs SHA: `7a72588dad8b298a4c3b52befef964484baedc10`.

Initial intermediate candidates had fixture failures; later candidate pytest succeeded but Ruff reported six import/UTC issues. Both corrected before successful candidate. Concurrency cancellation of superseded head runs was not treated as test success. A new CI run after evidence/ledger commits is required.

## Evaluations and handoff

Evidence: [TASK-010 SQLite snapshot E-018/E-019](../evidence/TASK-010-sqlite-snapshots.md). E-018 and E-019 set pass based on synthetic bound/fault-injection regressions and passing Ubuntu/Windows CI. Historical E-015/E-016/E-017 pass untouched.

TASK-010 remains **doing**, F-007 **in_progress**, F-005 **in_progress**, TASK-009 **done**, F-006 **verified** (synthetic only); latest_game_version null and product_implemented false. No old review threads resolved, no PR auto-merge. Next: verify final PR head/test-merge CI, request independent technical review, then only after actual main integration consider closing task. Do not start TASK-011/012/013.
