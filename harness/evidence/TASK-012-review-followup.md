# TASK-012 PR #23 review follow-up: R1–R5 (synthetic scope)

Base main: \`221e0044ab399f99ba1473bb1acf3ea22fd9014f\`.
Review head: \`ee47dbc6fa8dc0d54280296299b626271e84f28c\`.
Technical review: https://github.com/Gandalem/stellaris-suppoter/pull/23#pullrequestreview-5483312738
Same PR #23 and branch \`task/TASK-012-static-answers-citations\`; no merge/auto-merge or TASK-013.

## R1/P2: mixed-field source
Pre-fix: \`_format_hit\` verified each independently valid SourceRef but compared only numeric bounds with definition. Two synthetic files A (\`demo_a cost=100\`) and B (\`demo_b cost=999\`); replacing A's stored candidate_json field/value refs with B's valid refs could return B's 999 as A's cost.
Fix: full snapshot/source_kind/source_id/relative_path/file_sha256 identity bound to definition, plus exact parser-origin field and child value offsets. Any borrowed ref fails \`SOURCE_CHANGED\` without returning facts. Test: \`test_r1_cross_file_valid_refs_cannot_be_borrowed\`. Normal B remains accessible.

## R2/P2: syntax and occurrence
Pre-fix: substring \`cost in cost_modifier\` and \`= in any expression\` could be accepted as evidence, occurrence unchecked.
Fix: bounded reparse of the *verified original definition bytes*, using existing \`parse_bytes\` AST, require one top-level PairNode with BlockNode, ordered direct PairNode fields exactly matching candidate_json count/name/operator/occurrence/field span/child value span; all refs bound to same original file. A malformed/partial or too-large definition fails explicitly rather than inventing structure.
Tests: \`test_r2_forged_field_structure_rejected\` (5 negative parameter cases), \`test_r2_normal_duplicate_nested_fields_preserved\`. Comment/string fake keys remain inert due to parser.

## R3/P2: lookup before unsupported intent
Pre-fix: \`combat/chance\` regex fired before typed validation or exact search.
Fix: \`SearchService._validate(Query)\` first, then actual \`SearchService.search\`; an exact game ID/name/verified alias lookup is never suppressed by lexical intent keywords. Unsupported free-text calculation prompts are abstained with no numeric claims and pinned context. Bad limit/kind/snapshot yields \`QUERY_INVALID\`.
Tests: \`test_r3_normal_combat_chance_exact_names\` (2), \`test_r3_bad_query_precedes_unsupported\` (3). Previous E-024 abstention cases retained.

## R4/P2: envelope budget and verified cache
Pre-fix: each result reset 64 facts, 256 citations and 64KiB output; BlobCache.read rehashed entire same file for every citation.
Fix: shared \`_Budget\` across all results: max 64 facts, 256 distinct returned SourceRefs (counted per result), and 64KiB accounted display-name, field span and raw value bytes; raw value at most 512 bytes. Limit returns partial+truncated and diagnostic, never silent ok. The output metric is explicitly an accounted payload-byte budget, **not** Python object RSS or a serialized JSON envelope-size guarantee.
\`SnapshotRepository.citation_reader(snapshot_id)\` begins a pinned read-only transaction and retains an LRU of verified source bytes, with 24MiB total retained data+4-byte newline index charges, 16MiB maximum blob, maximum 1M newline offsets (4MiB); SHA-256 checked by existing BlobCache on each load, exact manifest checked for every citation, line positions via bisect rather than repeated full scans. Evicted entries are reverified on reload; no source/cache write.
Tests: \`test_r4_request_global_fact_limit_and_cache_reuse\` (100 source entities, all same source; search layer one SHA verification and answer reader one SHA verification for file, **not** one per fact), \`test_r4_exact_value_512_bytes_and_one_over\` (512 accepted, 513 truncated). Existing baseline E-023 cache-corruption remains.

## R5/P3: typed match provenance
Adds optional \`AnswerResult.match_source_ref\`, \`match_reference_selections\`, and \`match_language_used\` slots without changing existing constructor order. Root and ordered dependency refs are separate from display-localisation metadata. A distinct match-language field is optional; the current SearchHit does not expose matched_language independently, so do not interpret it as definitive for English match against Korean display. Further explicit upstream match-language support is nonblocking.

## Evidence / limitations
The prior \`harness/evidence/TASK-012-static-answers-citations.md\` is preserved. E-023/024/025 remain synthetic pass from previous verified head, with follow-up cases requiring latest CI check. Baseline 428 Ubuntu passed, Windows 425 passed + 3 prior skips.
No original game files, calculated game rules, real OS peak RSS, 10k end-to-end latency, FTS speedup or general malformed database forensic guarantee are claimed. Bounded source reparse (1MiB definition) is intentionally fail-closed for larger definitions; full 16MiB source cache read is still supported.

## Verified follow-up CI (code/document candidate)

- Reviewed old head: \`ee47dbc6fa8dc0d54280296299b626271e84f28c\`.
- Code/doc verification head: \`5f63d281fb4bd15b5a2b6610f16497f49dfd869a\`.
- PR **test-merge**, not actual main: \`306fa369a491cc42694d29219684a7368fedc77a\`.
- Package CI: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38141154994 — Ubuntu Python 3.11 **442 passed**, Windows Python 3.13 **439 passed, 3 original skips**, Ruff and check_harness both OS passed (harness_valid=true).
- Documentation harness: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38141155010 — both OS succeeded, same test-merge checkout in each job.
- 14 new authored synthetic test parameter instances versus prior Ubuntu 428 pass; previous E-023/E-024/E-025 pass retained. R1/R2 tampered candidate_json returns SOURCE_CHANGED with zero results; R3 exact names and bad-query precedence pass; R4 cache.read count and global facts/value-size boundary pass.
- This follow-up evidence commit itself changes the PR head; **its own head/test-merge, Package/Docs and head push CI must be inspected after commit**. This evidence does not imply actual merge or approval.

## R6/P2 — root technology ID, candidate/row and deterministic entity identity

- Re-review: https://github.com/Gandalem/stellaris-suppoter/pull/23#pullrequestreview-5483408389 ; **prior head** `3d1068af05717d6fb663d4bd1419b6e77c6a1cc2`.
- Pre-fix code: `answers._field_structure()` reparsed a valid definition but checked only child fields. The top-level `root.key_text` was not compared with the persisted technology ID. A parsed synthetic `demo_real = { cost = 100 }` candidate changed by `replace(candidate, game_id="demo_forged")` preserved valid source/cache but might be answered under forged ID. This was a code-path counterexample from review; do not claim the previous implementation's end-to-end execution was independently logged.
- Fix: `_field_structure(..., game_id)` now compares the parser AST top-level root key to the hit's actual game ID. `AnswerService._format_hit` compares `candidate_json.game_id/kind`, SQLite row game_id/kind and SearchHit game_id/kind and explicitly requires technology kind. The bounded `SnapshotRepository.answer_entity` now returns SQLite occurrence and defining source coordinates, which are compared against `TechnologyCandidate.source_ref`. It recomputes `entity_key=SHA256(storage_json({"kind", "game_id", "source", "occurrence"}))` exactly as the staging algorithm to reject occurrence, source, or row identity drift. SQLite v1 schema and snapshot identity remain unchanged.
- Tests: `test_r6_stage_forged_candidate_game_id_fails_closed` (the tampered candidate successfully stages/activates, then answer errors), `test_r6_sqlite_entity_game_id_tamper_fails_closed`, `test_r6_candidate_json_identity_tamper_fails_closed` (2 parametrized cases, ID and kind), `test_r6_entity_occurrence_identity_tamper_fails_closed`, and `test_r6_normal_same_id_multi_file_and_multiple_occurrences`. **Six new synthetic pytest cases**, all under E-023/E-025. Bad provenance expected and actual: status=`error`, diagnostic=`SOURCE_CHANGED`, `results=()`. Valid same ID in multiple files and repeated occurrences retain 100/200/300 distinct raw facts, no cross-file merging; other technology intact.
- Verified code/test head `b17e329c42a5f2b4c307f22e123cd962b57098bf`, actual PR test-merge **`758af0e1a3abcd2bcb2da4cd823da8e1389742a6`** (**not** main).
- Package PR run https://github.com/Gandalem/stellaris-suppoter/actions/runs/38142399579 : Ubuntu Python 3.11 **448 passed**; Windows Python 3.13 **445 passed + existing 3 skipped**. Ruff and `scripts/check_harness.py` both OS successful, harness_valid=true. Documentation harness https://github.com/Gandalem/stellaris-suppoter/actions/runs/38142399599 : Ubuntu/Windows success. All four actual job logs checked out `758af0e1...`.
- The R6 evidence-only final commit creates a newer head/test-merge. Check its own Package/Docs and exact head push CI separately before requesting review; do not confuse provisional head with final integration. No real game files, performance certification, merge, TASK-012 closure or TASK-013 implementation.
