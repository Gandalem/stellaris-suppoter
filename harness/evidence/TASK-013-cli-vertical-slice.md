# TASK-013 authored synthetic CLI vertical integration — candidate evidence

- Initial actual main merge: `422f6aa06849b2c210905d75bfe47a32e62f0bf4` after PR #24 owner merge.
- Prerequisite real main push CI: Package `38144498887` Ubuntu 448 passed, Windows 445 passed + original 3 skipped; Ruff/harness both OS succeeded; Documentation `38144498941` both succeeded.
- Branch `task/TASK-013-cli-vertical-slice`. E-026 was **not_run** before CI; its later synthetic pass is recorded below. Existing TASK-012/R1-R6 evidence preserved.
- New synthetic corpus created only under pytest temporary directories. No actual game files, saves or proprietary translations included.
- Planned command path: `init` exclusive TOML → `doctor` existing service → scoped inventory SHA/live capture → parse/adapt/localisation → `SnapshotRepository.stage_from_results` → exact manifest `activate` → `SearchService.search` → `AnswerService.answer(exact_game_id=True)` → bounded snapshot listing.
- Capture and activation preserve physical path, origin SHA and previous active on exception. Source read uses O_NOFOLLOW where present; OS hostile same-path TOCTOU not completely eliminated.
- The candidate execution and limitations are recorded below; no actual game compatibility is claimed.

## Verified synthetic E-026 CI (implementation candidate)

- Actual **starting main** after PR #24 owner integration: `422f6aa06849b2c210905d75bfe47a32e62f0bf4`. Main push Package `38144498887` and Docs `38144498941` Ubuntu/Windows succeeded; baseline 448 Ubuntu, 445 Windows + 3 previous skips.
- **Code and regression candidate head:** `e65a9cac1d05ef7a55b3d7510ef66a4fce3322a2`. The **actual PR #25 test-merge checkout** was `38b6bb2f177d134e0346993c7904fcf764982bbc`, checked in all four PR CI job logs; this is **not** an actual main merge.
- PR Package CI: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38146789624 — Ubuntu Python 3.11 **486 passed**; Windows Python 3.13 **483 passed + 3 existing skips**. Ruff `python -m ruff check .` and harness `python scripts/check_harness.py` succeeded on both (`harness_valid=true`).
- PR Documentation harness: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38146789613 — Ubuntu and Windows success at same test-merge.
- Exact code-head push Package: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38146786512 — Ubuntu and Windows successful.
- **38 new authored synthetic pytest cases** above the existing 448 Ubuntu regression tests, no tests removed and no new skips. E-026 is `pass` **only on synthetic inputs**. The upcoming evidence-only commit changes the head and must itself receive new Package/Docs/head push CI before a final independent review request.

## E-026 exercised vertical contract

- `init`: explicit root and disjoint private data_dir, network disabled, supported language, TOML with atomic exclusive no-overwrite publication; invalid config, symlink/reparse-path and NUL rejection.
- `doctor`: original TASK-003 config/runtime/SQLite/FTS5 diagnostics without indexing.
- `index`: only technology and Korean/English localisation subtrees; inventory SHA and safe live bytes capture, source_id/path identity, deterministic `SnapshotPolicy`, original ordered parser and `adapt_technologies`, pre-stage technology root-ID check, localisation reader/catalog/resolver and `stage_from_results` diagnostics; activation rechecks cached and **exact live manifest** before atomically updating active. Partial parser/localisation requires `--allow-partial`; no security, SHA, identity or path errors are bypassed.
- `search`: original `SearchService.search(Query)` on pinned active/explicit snapshot for exact technical IDs, Korean and English names and bounded literals. SQL parameterization and FTS fallback are inherited rather than bypassed.
- `show GAME_ID`: original `AnswerService.answer(exact_game_id=True)`, never a fuzzy name hit. Verified SourceRef for actual technology definition and field/value byte offsets, root translation and dependency; uncomputed `@demo_cost` is returned only as raw expression. Duplicate ID occurrences retain distinct SourceRefs.
- `snapshots`: read-only `list_snapshots(limit 1..100,offset 0..100000)` with active marker/status/context/branch/version/created/checked values, including non-ready snapshots without enabling them.
- Actual subprocess `python -m stellaris_supporter` and installed console script exercised synthetic init→doctor→index→ID/Korean/English search→exact ID show→value source byte equality→snapshots and repeat index reuse; same source bytes in independent root paths yield same snapshot ID.
- JSON stdout is exactly one sanitized schema_version 1 object, including errors, no Python traceback or partial JSON. Argparse error→exit **2**; config/path/snapshot missing→**3**; path/limit/overlap/network/NUL/1 MiB whole wire payload budget→**4**; source changed/partial refused→**5**; synthetic SQLite_BUSY writer failure→**6**; explicit KeyboardInterrupt→**130**; success/not_found/allowed partial→**0**. Text output retains snapshot/version, context/branch and actual fact-relative source/line positions.
- Source tests cover inventory/capture mutation, stage/activation race, previous active pointer preservation after failure, corrupted cache SHA, forged technology ID rejected **before stage**, duplicate occurrence isolation, bad UTF-8, partial consent and security override refusal, symlink path escape, private source read-only, bounded results, no network. Windows symlink privilege differences are handled with portable guard tests, not new skips.

## Unsupported and unverified

The selected index roots deliberately omit mod/DLC, other adapters, actual engine evaluation, probabilities, `refs/diff/ask/sync/simulate/serve` and automated database migration. There is no tested actual Stellaris installation, inferred latest game version, mod effective semantics, full hostile same-path OS TOCTOU solution, process peak RSS, cold index timing, 10,000-entity full p95 or FTS5 speed measurement. 1 MiB CLI output is a UTF-8 wire budget, not peak RAM; underlying AnswerService fact/citation/source budgets remain separate. No proprietary files or personal absolute paths are in public tests/evidence.

TASK-013 **doing**, F-011 **in_progress** because TASK-015 refs and TASK-016 diff are also linked; F-005/F-013 in_progress, E-026 synthetic `pass`, `latest_game_version=null`, `product_implemented=false`. No auto-merge, main edits, review-thread resolve or TASK-014.
