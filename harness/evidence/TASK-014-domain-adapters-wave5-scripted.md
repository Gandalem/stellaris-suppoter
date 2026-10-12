# TASK-014 Phase C2 — Scripted Trigger and Scripted Effect authored synthetic adapters

Date: 2026-10-12 Asia/Seoul. **No actual Stellaris installed-data grammar, script execution, mod order or version is claimed.**

## Real main gate before work

- [PR #32](https://github.com/Gandalem/stellaris-suppoter/pull/32) was actually merged as `e77b38dd3d568ee368d07e3a18777d4aacee8ce2` from reviewed implementation head `0b074d3ae1c2bfd6e40beeb4966b1926f3efea39`. Exact main SHA at C2 branch creation: `e77b38dd3d568ee368d07e3a18777d4aacee8ce2`.
- [Real-main Package #38248847704](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38248847704): Ubuntu Python 3.11 **704 passed**, Windows Python 3.13 **701 passed, original 3 skipped**; Ruff and `scripts/check_harness.py` successful on both OS. Job IDs Ubuntu 114809573875, Windows 114809573636.
- [Real-main Documentation #38248847705](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38248847705): Ubuntu 114809574114, Windows 114809574398 successful. **All four actual main checkout logs** show exact `e77b38dd3d568ee368d07e3a18777d4aacee8ce2`. The gate was checked *before* C2 source changes.
- Dedicated branch `task/TASK-014-domain-adapters-wave5-scripted` created from this SHA; no duplicate pre-existing Wave5 PR or branch was present. This phase is partial, E-027 is **not_run**.

## Synthetic ID and localisation contracts

| kind | unverified path candidate | ID rule | localisation policy | raw condition projection |
|---|---|---|---|---|
| scripted_trigger | `common/scripted_triggers/` | unique static top-level identifier assignment to raw block | **none**, never fabricate key from id/name/title | `limit`, `trigger`, `potential`, `allow`, `if` |
| scripted_effect | `common/scripted_effects/` | unique static top-level identifier assignment to raw block | **none**, never fabricate key from id/name/title | `limit`, `if`, `trigger`, `potential`, `allow` |

A repeated static ID creates separate ordered candidates with `definition_occurrence` and `ambiguous` resolution. Same-kind cross-file collisions preserve all definition source refs, different kinds never collide, mixed snapshots reject. Unsupported/dynamic top-level IDs, non-assignment operators, unclosed blocks and unknown syntax remain unhandled/partial, never silently evaluated. Conditions/effects, `@dynamic`, `weight`, `random`, nested `if`, `AND`, `limit` remain exact authored script expressions, **not game-engine evaluations** or mod precedence.

The new registry values extend the original eleven synthetic kinds to thirteen; the public DomainCandidate, DomainField, DomainDiagnostic, SourceRef and serialization contracts are unchanged. `localisation_rule="none"` is used only for two scripted kinds; even an authored field `name` or `title` must not become a guessed localisation key; `resolve_domain_name` rejects absent keys rather than synthesizing KO/EN names. Existing eleven kinds, technology, SQLite, search and CLI remain untouched.

## Real test-first failing evidence and subsequent repair

- New `tests/test_domain_scripted.py` was written **before source implementation**, commits `3321bc7c324fdf550f05c7061c898cef1ed90424` and `3260d24dbd20bf45bb3e09c7c3f9c8305ff7021c`. Ubuntu Package #38249561349 **job 114812058685** actually ran pytest and logged **33 failed / 704 passed** (`ValueError: unregistered domain adapter`) before the registry was changed. The workflow itself was later cancelled when new commits superseded it; the completed Ubuntu red pytest log remains available, but do not claim a fully successful/complete red workflow.
- Source registration/no-localisation code head `95af1999de24a81c790c1a1a0920a58ea2e85092`. Exact implementation/final head CI is verified after this evidence commit and posted on the PR, not inferred from its source.
- The authored synthetic cases cover static IDs and exact bytes, fields and repeated condition occurrences, no invented localisation (Korean/English resolver must reject), 11-kind preservation, root dynamic/number/unsupported operator, duplicate same-file definitions, same-kind cross-file conflicts, cross-kind isolation, provenance/sha/snapshot/path checks, R1 direct `_source` 100→999/field borrowing/condition and nested child backing, R2 foreign/empty parse AST + token/column tamper, BOM/CRLF/Hangul/invalid UTF-8, raw serialization budget, parser limits, unclosed/fake string/comment/unknown operator, 999/1000/1200 warnings and 1200 clean definitions, parser+adapter budgets, one-candidate 1200 warnings early block, canonical parse once per adapt vs once per candidate verification.
- All older event qualified namespace ID regressions (including `authored.`, double/trailing dots), Phase A/B, earlier R1/R2, and SQLite/Search/CLI tests remain present. No test was deleted or newly skipped.

## Non-gating P3 observation / remaining C3

- `scripts/bench_domain_scripted.py` observes **32 candidate definitions per kind × 3 repetitions** on each CI OS: `adapt_domain` performs one canonical parse on an already supplied parsed input, whereas 32 separate `verify_domain_candidate` calls perform 32 entire-file canonical parses. It records platform, Python, raw SHA, parse count and timing. This is only a non-gating synthetic microbenchmark, **not TASK-019/E-035 official p95, FTS5 or peak RSS**.
- A future resource-bounded source-bound read-only verified parse context may avoid redundant canonical parse when snapshot_id/source_id/relative_path/SHA and original bytes match; changes invalidate it and different snapshots must not share it. R1 field/condition/nested backing and R2 whole-file binding can **never** be bypassed for speed.
- C2 adds scripted domains but does **not** execute the `all-domains` E-027 coverage matrix. The following gated **C3 PR** will evaluate all thirteen synthetic kinds for normal/error/collision/localisation/source attacks, with no assumptions about actual game grammar. TASK-014 done/closure and TASK-015–022 are disallowed until C3 approved owner merge and new actual main CI.

## Final PR head publication contract

This evidence is committed *before* a future PR number/final head/test-merge SHA can exist. Once the PR is opened, verify **exact** latest head, temporary test-merge SHA, PR Ubuntu/Windows Package pytest/Ruff/harness and Documentation jobs' **four real checkout SHAs**, and **exact head-push CI**. Post real run IDs, counts, any discovered test corrections and any P3 timing observations in a final-head independent technical review request comment, not as fabricated values here. Do not auto-merge, modify main, resolve past review threads or start C3 early.

**Ledger:** TASK-013 done; TASK-014 doing; F-005 in_progress; E-027 not_run; active_task/next_task TASK-014; TASK-015–022 todo; latest_game_version=null; product_implemented=false.

## Intermediate test expectation correction (not a product-code defect)

- Initial implementation/evidence head `e6942ea9e6b1b0a7cd5c6a657e4eb412f14987e7`, [exact-head push Package #38250064253](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38250064253), Ubuntu job `114813752091` ran **736 passed / 1 failed**. Failure: `test_c2_duplicate_ids_fields_conditions_and_occurrences[scripted_effect]` assumed the `limit` nested inside `if` would also be materialized as another **top-level** DomainField.condition. The authored fixture has only one direct top-level `limit` from its extra body; the other is correctly preserved within `if` RawNodeRef.
- The test was corrected to expect 2 direct `limit` fields for Scripted Trigger, **1 direct** for Scripted Effect, and **explicitly assert** the nested `if` raw value contains its own original `limit = { has_country_flag = active }`. No production adapter or source security rule altered; no test deleted/skipped. The intermediate partial-green run does not stand in for final green CI; new head push, PR test-merge four checkout logs still required.

## C2 explicit dynamic expression follow-up — actual pre-fix red

- The first registered-scripted implementation head `ed7604d4242d49b6681b2f79ec9f3c83a8904d33` had exact-head Ubuntu push pytest **737 passed**, Ruff and harness success, before a later extra safety requirement was tested.
- Six new authored synthetic cases were added in **tests-only head `549e94172cf1b7ab19a396b0c0b609a5fb2fb6d2`**. The original normal fixtures now use truly static leaf expressions rather than `@dynamic`. Four new cases require `@dynamic`/`@variable` nested raw scalars to produce `partial` and a source-grounded `DOMAIN_DYNAMIC_EXPRESSION_UNSUPPORTED` warning for each scripted kind; two cases ensure a quoted `"@dynamic"` and a comment are never interpreted as dynamic.
- [Actual pre-fix head push Package #38250576500](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38250576500), Ubuntu job `114815492856`: **4 failed, 739 passed**. All four failures actually showed `candidate.resolution == "raw_definition"` where `partial` was required. This is independent from the earlier **33 failed, 704 passed** pre-registry test. New tests were committed **before** the scripted dynamic detection implementation.
- Fix: a **C2-only** bounded recursion over the canonical validated AST identifies the first unquoted `@`-prefixed scalar. Preserve original `game_id`, ordered SourceRefs and RawNodeRefs. Add exactly one warning for a candidate with such a dynamic expression via the existing budget-reserving `warning()` helper, thereby returning a partial candidate without inventing semantics and retaining the parser+adapter shared 1,000 limit. Earlier eleven kinds and parser source integrity remain unchanged.
- Total new scripted test cases after this follow-up: **39 parameterized cases** on top of the previous 704 passing baseline. Full exact final PR green counts must be verified after this code+evidence commit; do not cite older 737-pass run as final.
