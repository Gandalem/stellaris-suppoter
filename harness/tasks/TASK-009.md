# TASK-009 Localisation reader/resolver

Task: TASK-009  
Feature: F-006  
Evaluation IDs: E-015, E-016, E-017  
Base main: `e49ab75153d695b92614b2db3a0e54136f148e37`  
Branch: `task/TASK-009-localisation-reader-resolver`

## Scope

Dedicated source-preserving reader and deterministic bounded resolver for synthetic Stellaris-like localisation:

- UTF-8 strict/BOM, LF/CRLF, language headers, keys, optional marker, quoted value and lexical escapes, comments/blank lines/EOF.
- Ordered duplicate entries, raw byte SourceRefs, line and column, distinct raw/display values, explicit unknown spans and diagnostics.
- Requested language → English → ID fallback, duplicate ambiguity and no invented precedence.
- Supported static `$KEY$` references only; explicit cycles, missing/ambiguous references, unsupported dynamic forms.
- Resource bounds on file/line/items/diagnostics and resolver depth/visits/scanned bytes/output.
- SourceContext hash/path/snapshot validation and technology-localisation SourceRef separation.

Out of scope: real game installation, DB schema, search/CLI integration, effective mod precedence, actual game scripting semantics.

## Evaluations

E-015 Language fallback: pass, including language/SourceRef of selected references.  
E-016 Localisation cycle: pass, self/multi-key, missing and bounded expansion.  
E-017 Duplicates and dynamic text: pass, retained raw/spans/markup, encoding and resource negative tests.

All evaluation evidence: [TASK-009 localisation reader/resolver](../evidence/TASK-009-localisation-reader-resolver.md).

## CI

PR #17 candidate code/test head `c6fa59143df0f1921fc6d2e7c9fb4557db85ad5a`.  
Test-merge `83a044412bdb59eb1b07069b41e7886295860a5a`.

- Package PR run `38125860266`: Ubuntu 230 passed; Windows 227 passed + 3 existing intentional skips. New localisation 50 tests passed both.
- Ruff and `scripts/check_harness.py`: both OS success.
- Documentation harness PR run `38125860274`: both OS success.

## Status

TASK-009 remains **doing** until reviewed/merged and actual main push CI succeeds.  
F-006 **in_progress**, F-005 **in_progress**, latest_game_version **null**.  
No main merge, original game file use, or review thread changes.


## PR #17 R1-R4 review follow-up

Reviewed blocked head: `1a260d2c045410781eeb1fa8dfb76c8b44a226d0`.

- R1/P2: replace overlapping whitespace regexp with monotonic entry-prefix scan; verify long no-quote malformed lines and 1 MiB boundary.
- R2/P2: classify bracketed/dynamic/unknown-escape regions before static dollar references; preserve regions without choosing inner references.
- R3/P2: repair duplicated/broken PARSING.md and add semantic document integrity regression.
- R4/P3: charge each record immediately before appending, including header/entry plus inline comments and exact-budget EOF.

Code/test/doc head `10dd9b721e13819cfa764ab30d6fe26e15ac2499`; PR test-merge `889ef8b85321a45ebcb68a39fc48f1f0f24429e3`.
Package PR run `38126968416`: Ubuntu 268 passed; Windows 265 passed + 3 existing skips. Ruff and harness succeeded both. Documentation PR run `38126968353`: both successful.

Historical evaluation successes remain intact, with additional follow-up evidence:
[TASK-009 R1-R4 review follow-up](../evidence/TASK-009-review-followup.md).

TASK-009 = doing; F-006 and F-005 = in_progress; E-015/E-016/E-017 = pass; latest_game_version = null.
No actual merge or TASK-010 work. Final evidence-only head will receive its own PR CI.


## PR #17 R5/P2 normative data contract follow-up

The blocked reviewed head `679c327c5b2c940c8a886d6b088b3008e0b62599` contained a broken `$KEY# 데이터 계약 v1` phrase and repeated source/snapshot/AST/entity sections in `docs/DATA_CONTRACTS.md`. Removed repeated content; restored protected-region-only `$KEY$` expansion, fallback, unresolved/ambiguous/partial semantics and budgets. Added 11 structural/semantic normative-document regression cases over five documents, including intentional corrupted variants.

Code/doc/test candidate head `eb5b68b377e7ba6566173543faf0a784de575b21`, PR CI test-merge `03718d748bda4ba12ba708d3268a5c142cd4c53d`.
Package run `38128348984`: Ubuntu 279 passed, Windows 276 passed + original 3 skips, Ruff/harness success both. Documentation harness run `38128348992`: Ubuntu/Windows success.

R5 evidence: [TASK-009 R5 documentation review follow-up](../evidence/TASK-009-r5-document-integrity.md). Historical prior evidence/CI remains unchanged. Final evidence/ledger head requires its own PR CI before requesting independent re-review.

TASK-009 remains `doing`, F-005 and F-006 `in_progress`, E-015/E-016/E-017 `pass`, TASK-010 `todo`, latest_game_version `null`. PR is not merged; no threads were resolved.


## Actual main integration and proposed official closure (2026-10-11)

PR #17 was **actually merged** into protected `main`:
- final implementation head `c4842aaae6f88216f33711d6a95b141074e2dad5`
- merge commit `f9638850dfd514790cf90c194f9ff062e7819f12`
- technical follow-up [R1–R5 review](https://github.com/Gandalem/stellaris-suppoter/pull/17#pullrequestreview-5482768133) was recorded as `COMMENTED` (technical hold lifted; not a formal APPROVED event)
- actual `main` Package push run [38128971447](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38128971447) on the merge commit: Ubuntu Python 3.11.17 **279 passed**, Windows Python 3.13.15 **276 passed + three existing POSIX-only skips**. Ruff and `scripts/check_harness.py` succeeded on both OS.
- actual `main` Documentation harness push run [38128971437](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38128971437): Ubuntu/Windows succeeded.

TASK-002 synthetic corpus and TASK-007 prerequisites are done; E-015/E-016/E-017 stay `pass`. F-006 requirements (Korean→English→ID, explicit missing/cycles, dynamic expression non-execution) are satisfied **for synthetic-supported behaviour**. Historical R1–R5 evidence is preserved. [Actual main integration evidence](../evidence/TASK-009-main-integration.md) was added.

This **separate closure PR branch** proposes TASK-009=`done`, F-006=`verified`, active_task=`null`, next_task=`TASK-010`. The official base main still carries the pre-closure state **until the closure PR is independently reviewed and actually merged with main CI**. F-005 remains `in_progress`, TASK-010 `todo`, F-007 `planned`, E-018/E-019 `not_run`, latest_game_version `null`, product_implemented `false`.

Scope remains project-authored **synthetic fixtures only**; real game engine/load order/install compatibility is **not verified**. No SQLite schema/repository implementation or TASK-010 development was started.
