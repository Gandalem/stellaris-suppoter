# TASK-013 CLI PR #25 technical review R1–R5 follow-up

- Base main: `422f6aa06849b2c210905d75bfe47a32e62f0bf4`.
- Reviewed old PR head: `b4bcee52688fcf98a16c5ce6ee4987411ec64beb`.
- Technical review: https://github.com/Gandalem/stellaris-suppoter/pull/25#pullrequestreview-5483720276 (COMMENTED, merge hold; not an APPROVED).
- Same branch: `task/TASK-013-cli-vertical-slice`, PR #25, no new PR or actual main merge.
- Previous baseline: Ubuntu 486 passed, Windows 483 passed + three existing skips, Ruff/harness/Docs success. The original `harness/evidence/TASK-013-cli-vertical-slice.md` remains unchanged.

## Reproduction provenance
Tests were added **before** the fixes in head `70c675d1f862c07f85ddb96e4fe58848c9e0459f`. Actual Package CI [#38148793706](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38148793706) and PR Package [#38148799524](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38148799524) failed as expected on the new regressions. Ubuntu logs recorded missing R1 guard, R2 .bin budget failures, absent R3 settings budgets, R4 metadata loss and R5 ESC passthrough. The first test draft also included two non-implementation fixture/assertion issues (short prefix expected found rather than not_found, and an untranslated second ID causing partial without consent); these expectations/fixtures were corrected explicitly rather than counting them as defects. Avoid claiming every first-run failure was an independent production defect.

## R1/P2 — hard parser and resolver limits do not permit consent activation
- **Before:** `cli_index.index_technologies` forwarded `TechnologyAdaptResult.diagnostics` and resolved-name diagnostics to `stage_from_results`, then `activate(... allow_partial=True)`, without classifying hard parser or resolver limits. Injected lexer/parser limit error diagnostic did not raise before staging. Deep static localisation default gave exit 5 without consent and could be consented under the old path.
- **Fix:** explicit `_reject_resource_limits` for `LIMIT_EXCEEDED`, `PARSE_DEPTH_LIMIT`, `PARSE_NODE_LIMIT`, `PARSE_DIAGNOSTIC_LIMIT` in technology adaptation, and resolver per-name diagnostics/truncated before stage. Even an existing older partial snapshot is rechecked before allowing activation; ready snapshot reuse still checks live manifest/cache.
- **Tests:** `test_review_r1_technology_bound_is_not_partial_consent` (4 parameter cases), `test_review_r1_actual_parser_depth_exhaustion_is_not_partial`, `test_review_r1_deep_static_localisation_reference_is_never_activated`, `test_review_r1_resolver_visit_and_output_bounds` (2). Expected corrected result: LIMIT_EXCEEDED/CLI exit 4, previous active preserved. Pre-existing `test_e026_partial_explicit_opt_in_keeps_diagnostics` and localisation partial consent remain valid.

## R2/P2 — only allowed extensions consume file budgets and SHA
- **Before:** `scan_inventory` evaluated every regular file's size/count/total and hashed it before `cli_index` filtered unsupported file suffix. The first run verified oversized or numerous .bin siblings denied a normal .txt index.
- **Fix:** optional suffix filter in the existing inventory candidate traversal, after secure type/symlink/reparse and path text checks but before file size/count/byte charging and hash reads. CLI calls inventory with the exact .txt/.yml per-root selection; cross-root aggregate budget still checked. All directory visited-entry/recursion security limits remain in effect even for names not selected for hashing.
- **Tests:** `test_review_r2_non_target_file_size_does_not_consume_budget`, `test_review_r2_non_target_file_count_does_not_consume_budget`, `test_review_r2_target_budget_and_cross_root_aggregate`, `test_review_r2_supported_symlink_remains_rejected`.

## R3/P2 — configured query bounds before service use
- **Before:** CLI populated Query directly from flags/defaults without settings.limits.query_chars or max_results. The first run verified a text of 5 characters was accepted with query_chars=4; show similarly ignored configured length.
- **Fix:** `_bounded_query_limit` validates typed query/service hard 512 chars/100 results first (QUERY_INVALID, exit 2). Configured smaller query_chars/max_results next (LIMIT_EXCEEDED, exit 4). Omitted --limit adapts to min(default search20/show100, configured max_results) so ordinary show works at max_results=1. SearchService and AnswerService retain their own semantic validation.
- **Tests:** `test_review_r3_configured_query_char_boundary_search` (2), `test_review_r3_configured_result_default_and_explicit_limit`, `test_review_r3_show_applies_configured_query_chars`. Existing invalid 0/101 and normal search tests are retained.

## R4/P2 — complete text snapshots representation
- **Before:** `_emit_text` rendered only snapshot_id and status, losing active flag, branch, version and times; demonstrated by first-run test.
- **Fix:** dedicated snapshots text rendering of all bounded Repository listing columns; includes limit, offset, truncated and unknown values without mixing statuses.
- **Tests:** `test_review_r4_snapshot_text_contains_full_row_metadata` with two live synthetic snapshots and page controls; `test_review_r4_all_snapshot_statuses_text` (four parameter cases for ready/partial/building/failed).

## R5/P2 — terminal-text boundary, without changing source or JSON
- **Before:** raw user-controlled localisation display names and diagnostics inserted into text output; first-run injected ESC CR BS and U+202E escaped neither.
- **Fix:** `_safe_terminal_line` escapes all `not str.isprintable()` codepoints as readable escaped characters and preserves ordinary Korean/English. Called for CLI text including doctor and snapshots; does not mutate cached source or SourceRef. JSON retains original data values and single-object stdout.
- **Tests:** `test_review_r5_terminal_controls_escaped_only_in_text` (ESC/reset, CR/BS and bidi, JSON semantic equality), `test_review_r5_end_to_end_unsafe_name_is_only_escaped_in_text` (actual synthetic localisation → index/show subprocess).

## Verified interim code/test execution (not final gating)
- Initial corrective candidate `19e7641bb05dfce1290cef01f241e2d29ff5dd09`: Package CI [#38148963954](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38148963954) logged Ubuntu **500 passed / one assertion failure in test representation**. The test expected `\\r/\\b`, whereas safe text chose equally explicit `\\x0d/\\x08`; implementation normalized that display to `\\r/\\b`.
- Extended-code candidate `083796c1fc062afcf03b56e67233b5a323a3119e`: Package [#38149124298](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38149124298) actually ran **Ubuntu 509 passed and Windows 506 passed + existing 3 skips**. Workflow remained unsuccessful because of four **Ruff style-only** diagnostics in new tests (import ordering and unused f-prefix), which were fixed after this run. Documentation harness [#38149124227](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38149124227) succeeded both OS.
- This follow-up note is not the final CI result. The eventual final head must pass Package pytest/Ruff/harness Ubuntu/Windows, Docs both, head push and exact PR test-merge checkout. No passing status may be inferred from partial runs.

## Nonblocking residual limitations
- A previously missing DB may be created on nominally read-only search/show/snapshots constructor; explicit non-creating read-only open should be separately designed.
- File access denied versus cache/DB failure exit-code differentiation remains a later error-mapping quality task.
- File traversal `max_entries` remains a security limit counting physical directory entries even when non-target file bytes and max_files are excluded.
- Hostile same-path OS TOCTOU, actual Stellaris installation compatibility, cold index timing, peak RSS, 10k full search p95, and measured FTS5 acceleration are **unverified**. No LLM, game engine or real game files.
- Ledger must stay TASK-013 doing, F-011 in_progress, E-026 synthetic pass; TASK-014 todo, F-005/F-013 in_progress, latest_game_version null, product_implemented false. No merge, force push or review-thread changes.

## Verified R1–R5 corrective candidate CI (not final ledger-commit test-merge)

- Code + tests + documentation head: `d4338eb032367c568ffebe92c8b117009169203d`.
- Actual PR **test-merge checkout**: `b123359c6c04908c6dbc4582f12b6b57cc1cd2e3`, verified exactly from **all four** Ubuntu/Windows Package and Documentation job logs. This is NOT an actual main merge.
- [PR Package and tooling #38149318668](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38149318668): Ubuntu Python 3.11 **509 passed**, Windows Python 3.13 **506 passed + 3 pre-existing skips**; `python -m ruff check .` success both OS; `python scripts/check_harness.py` success both OS (`harness_valid=true`).
- [PR Documentation harness #38149318757](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38149318757): Ubuntu/Windows success with same checked-out test-merge.
- [Exact-head push Package #38149315850](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38149315850): Ubuntu/Windows success, same code head.
- Baseline retained 486 Ubuntu / 483 Windows + 3 skips. **23 additional authored pytest cases** yielded 509 Ubuntu / 506 Windows + 3 skips. No deletion or new skipped tests, no threshold relaxation.
- E-026 remains **pass for synthetic subprocess CLI only**; this follow-up extends its test evidence, without making real-game, process RSS or hostile same-path TOCTOU claims.
- The evidence/ledger linking commit will be a newer PR head; its own Package/Docs/head push and actual test-merge checkout MUST be verified separately. No merge or formal independent APPROVED is implied.
