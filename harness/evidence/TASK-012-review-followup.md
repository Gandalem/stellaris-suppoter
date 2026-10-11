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
