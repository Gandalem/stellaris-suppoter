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
