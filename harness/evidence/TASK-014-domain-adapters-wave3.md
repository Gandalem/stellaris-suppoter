# TASK-014 Phase B — tradition and ascension-perk synthetic adapters

Date: 2026-10-12 (Asia/Seoul). **Actual source main at branch creation:** `1944e5725cb2680799107dcfde017b0d57d4baa0` (PR #29 merged and actual main Package/Documentation integration previously confirmed). Work branch `task/TASK-014-domain-adapters-wave3`. PR #30 dependency-pruning remained OPEN at Phase B branch creation and was independently reviewed with a COMMENTED technical review, **not merged**; new overlay task dependencies must not be cited as current main truth.

This is a partial TASK-014 implementation. E-027 remains `not_run`. The existing eight synthetic adapters and all previous foundation/wave2 evidence are retained. No game files, online content, mods, DLC, live engine, SQLite schema migration, CLI implementation or Windows GUI support is represented.

## Explicit synthetic ID contracts

| kind | candidate source path (unverified in game) | candidate shape | game ID rule | localisation key |
|---|---|---|---|---|
| tradition | `common/traditions/*.txt` | `traditions = { group_entry = { id = trad_a name = trad_a_name ... } }` | **unique static direct-child `id` field**; wrapper/group key NOT ID | unique static `name` field |
| ascension_perk | `common/ascension_perks/*.txt` | `ascension_perk = { id = perk_a name = perk_a_name ... }` | **unique static `id` field** within wrapper | unique static `name` field |

Both grammars are directly authored synthetic conventions. Dynamic/missing/duplicate ID and name expressions remain `partial` with diagnostics; unregistered wrappers, groups and unknown raw AST are never turned into inferred game IDs. Ordered duplicate fields, condition/effect raw expressions, occurrences and cross-file conflicts retain their exact source spans. Effective gameplay values and mod/file precedence are not inferred. Support level is `synthetic_static` only for fully static registered forms.

## Source integrity, resource budgets and regression

- Both adapters use unchanged public `adapt_domain(parsed, source, SourceContext, kind)` canonical source-bound ParseResult comparison (old PR #28 R2) and candidate R1 verifier for independent ordered items, field values, condition values and nested `RawNodeRef.children`. SHA/path/snapshot/byte spans and line/column are preserved; borrowed field sources, `100` → `999` backing, wrong occurrences and foreign parse are negative cases.
- Nested tradition uses the same per-child combined diagnostics limit as government (old PR #29 R1/P2). Positive 999 warnings remains partial, 1,000 triggers `LIMIT_EXCEEDED`/blocked/empty, 1,200 stops before the 1,001st candidate. Parser+adapter diagnostics share this bound; 1,200 clean definitions remain valid.
- Safety hardening **within one candidate**: preflight warning-generating fields/unknown AST before raw projections; reserve a diagnostics slot before creating each adapter diagnostic. This closes the separate risk of a single definition generating >1,000 warnings before failing. Parser/lexer hard stop remains blocked, never silent success. All bounds (16MiB, 100k tokens, 128 depth, 100k AST nodes, 1k parser diagnostics, raw output byte budget) remain.
- Existing TechnologyCandidate, SQLite/search/CLI, the foundation four adapters, Phase A four adapters and previous R1/R2 source-attack tests are not replaced or skipped.

## Authored synthetic acceptance and localisation

`tests/test_domain_wave3.py` adds both kinds to the regression matrix: good/static source, groups vs real IDs, missing/dynamic/duplicate ID/name, repeated fields/conditions/ID occurrences, in-file and cross-file collision, cross-kind ID separation, source/field/operator/snapshot attacks, external ParseResult and tampered token/AST positions, UTF-8/BOM/CRLF/Korean/source-budget, unclosed/unknown/operators and quoted fake syntax, and the 999/1,000/1,200 child/root diagnostics matrix including parser diagnostics and 1,200 clean definitions. Two further parameterized tests cover excessive warning fields in *one* candidate. Localisation reuses existing catalog+resolver for KO/EN, KO→EN fallback, missing key fallback, duplicate translation ambiguous, $KEY$ multistep refs/cycle, dynamic [Root.GetName]/icon partial, root/dependency SourceRefs, wrong SHA/snapshot and scan budget.

## Actual pre-implementation red evidence

- **Tests-only commit:** `c243012e7e593b4e89bda32e0a0ae95d02a08683`. [Head push Package #38235691423](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38235691423) Ubuntu full pytest: **43 failed / 609 passed**: the two new kinds were not in the registry. This is a real run, not an inference, and the 609 pre-existing passing tests were retained.
- A subsequent test-only change required explicit field-derived tradition IDs (never treat a group key as an ID). Extra test-only runs can be cancelled by repository workflow's `cancel-in-progress`; do not claim a red result that was not logged as completed.
- Source implementation heads before evidence: initial `3612c6c4f04f19cab045fbb372e96e9ab7a2f6eb` (registry), refinement `2b3185c5b6ba8fd222392eccb2dbf80dc708bb8a` (nested ID-field), safety hardening `6f0fd32924ed083314f5ced5ed7a3204a2a017ea` (single-candidate budget preflight). Final results must come from actual CI, not inferred.

## P3 performance and remaining gates

`scripts/bench_domain_wave3.py` constructs 32 authored synthetic candidates in memory per new kind, repeats 3 times, records raw SHA, platform, adapter canonical parse calls (expected 1), 32 separate `verify_domain_candidate` canonical parses, and wall-clock samples. A non-gating Package CI step runs on both OS; **this is not** TASK-019's 10k-entity throughput/FTS5/peak RSS/p95 acceptance. Source-/snapshot-/path-/hash-bound shared verification context is a future design candidate; do not skip R1/R2 to reduce latency.

**CI/evidence publication contract:** The PR is created after this evidence commit; the exact final PR number, head commit, temporary PR test-merge SHA, head push Package CI, Ubuntu/Windows full pytest+Ruff+harness, Documentation harness and actual four PR job checkout SHAs must be independently fetched and posted in a PR technical review request comment. Evidence is intentionally committed before final Git SHA exists, so earlier code-only tests do not replace final-head green checks.

**Remaining TASK-014:** Event, Scripted Trigger, Scripted Effect, full all-domain E-027 normal/error/collision/localisation/tamper evaluation, then separate official TASK-014 closure PR, its owner merge and actual main CI. TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`, TASK-015–022 `todo`, latest_game_version=null, product_implemented=false. No Phase C or TASK-015 before owner merger+main CI gate.
