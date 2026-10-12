# TASK-014 Phase C2 / PR #33 — R1/P2 Scripted PairNode variable-key follow-up

2026-10-12, Asia/Seoul. **Authored synthetic script fixtures only**. Installed Stellaris grammar, engine semantics, real game versions, mod order and live sources have not been verified.

## Scope and immutable review reference

- Same [PR #33](https://github.com/Gandalem/stellaris-suppoter/pull/33), same `task/TASK-014-domain-adapters-wave5-scripted` branch; reviewed head `8c22dec2e4c308f34d687786bb8d14dff7d5bf71`, unchanged actual base main `e77b38dd3d568ee368d07e3a18777d4aacee8ce2`.
- Original blocking [technical review #5491123354](https://github.com/Gandalem/stellaris-suppoter/pull/33#pullrequestreview-5491123354) found a **variable key** omission inside `_first_scripted_dynamic`. That review performed static code analysis, not an actual new pytest run; **the independently executed CI red reproduction below** supplies that missing measurement.
- The prior 11 non-scripted synthetic adapters, existing 39 Phase C2 authored test cases, Technology/SQLite/Search/CLI regressions, event namespace-qualified IDs, original Wave5 evidence (`harness/evidence/TASK-014-domain-adapters-wave5-scripted.md`) and earlier Wave4/Phase B/Phase A evidence are preserved, not reimplemented or deleted.
- Baseline before follow-up: Ubuntu Python 3.11 **743 passed**, Windows Python 3.13 **740 passed + existing 3 skipped** with Ruff, harness and Documentation both OS success. The code in the baseline only detected authored `@`-prefixed **scalar values** in a PairNode; it did not look at `key_kind/key_text/key_span`.

## Real pre-fix pytest failure (tests committed before any fix)

- **Tests-only head `01f9981e47580ace684386890f9b5d5ada8543f6`** added `tests/test_domain_scripted_review_followup.py` without modifying product source. [Exact-head push Package CI #38252974871](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38252974871), Ubuntu Python 3.11 job **114823693407** executed pytest and logged **20 failed / 749 passed**.
- **12 direct counterexamples failed:** two kinds `scripted_trigger` / `scripted_effect` × two keys `@dynamic`, `@variable` × three positions (direct, nested, deeply nested). In each case the *actual pre-fix* candidate was `(resolution='raw_definition', support_level='synthetic_static', complete=True)` even though the `PairNode` itself was correctly parsed as `key_kind='variable'` and the expectation was `('partial','partial',False)`.
- **8 more failing boundary cases:** two kinds × 999, 1,000 and 1,200 dynamic-key warnings (6), plus combined parser+adapter diagnostics (2). Before the fix those uncounted keys yielded too few warnings and did not properly block at 1,000. The six other added cases (existing variable **value**, quoted key/value + comments, independent R1 field/children raw backing mutation, R2 empty/altered ParseResult binding) passed without the fix, confirming no regression in those existing protections.
- The source fixture includes `authored_rule = { nested = { @dynamic = yes } }` in each kind's path under `common/scripted_triggers/` or `common/scripted_effects/`, SourceContext contains SHA256 of exact source bytes, and tests compare `PairNode.key_span` and the warning's SourceRef byte start/end, snapshot_id, relative_path and file SHA. The source `authored_rule` ID and occurrence, repeated field order, nested RawNodeRef and unaltered original input are independently asserted.
- The red workflow's status may change/cancel after later commits; **the completed Ubuntu job's actual pytest log and result**, not a hypothetical or all-OS red claim, is the factual before-fix evidence.

## Narrow R1/P2 implementation

- Source: `src/stellaris_supporter/domain/generic.py` only. `_first_scripted_dynamic(node)` now returns the **original SourceSpan**, not an artificial AST item:
  - For a `ScalarNode` with an authored `@`-prefixed scalar value, return `node.span` (existing behaviour).
  - For a `PairNode` with `node.key_kind == 'variable'` and `node.key_text.startswith('@')`, return `node.key_span`. Otherwise descend into `node.value` unchanged.
  - For `BlockNode`, retain source-ordered recursion into every child, including nested value blocks.
  - The pre-existing candidate-level `warning('DOMAIN_DYNAMIC_EXPRESSION_UNSUPPORTED', ..., _source_ref(context, returned_span))` still provides a **source-grounded exact variable key/value span**, reserves from the existing shared parser+adapter diagnostic budget and marks the returned candidate `partial`. At the 1,000 budget it stops with `LIMIT_EXCEEDED`, `blocked=True`, and no candidates; no weakened R1/R2 verification.
- Quoted `"@dynamic"` keys have `key_kind='string'`, not `'variable'`; quoted scalar values begin with the quote, not `@`. Comments have no parsed PairNode. These remain untouched.
- No common `_ID` changes; no localisation key synthesis, effects evaluation, original source mutation, parser budget raise or unrelated 11-kind policy modification. Any P3 parse-cache experiment must remain separate.

## New synthetic tests and full regression matrix

- **26 newly parameterized pytest cases**, test functions in `tests/test_domain_scripted_review_followup.py`. **12 new variable-key cases** cover both kinds × two variable keys × direct/one-level/deep nested. Remaining 14 include variable scalar values (2), quoted key/string/comment (2), R1 field/child raw backing + R2 foreign/coordinates (2), 999/1000/1200 key budget (6), combined parser+adapter diagnostics budget (2).
- The previous **39** Phase C2 synthetic cases, all event namespace/ID regressions (valid/empty/repeated/trailing delimiter), old foundational R1 independent item/field/condition/nested RawNodeRef `_source` tampering, R2 canonical full-source ParseResult binding, BOM/CRLF/Korean UTF-8, existing lexer/parser ceilings, and Technology/SQLite/Search/CLI are all retained. **No test deleted or new skip introduced.**
- Work must run `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py` on Ubuntu Python 3.11 and Windows Python 3.13, plus Documentation harness both OS. Final head push Package and final PR test-merge must be verified **for their actual checkout SHAs in all four PR jobs**, not guessed from PR metadata.

## Final SHA and CI publication rule

This evidence was written *before* a future final PR test-merge SHA and workflows existed. **Final exact head, temporary test-merge SHA, four checked-out job SHA values, exact head push run, final Ubuntu/Windows pytest counts, Ruff/harness and Documentation conclusions must be fetched from the real successful runs and appended in a timestamped final PR #33 review-request comment.** Do not self-certify an external `APPROVED` or confuse a temporary PR merge with an actual main merge.

## Non-gating P3 and progression gates

- Earlier C2 synthetic microbenchmark on 32 candidates per kind observed **1 canonical parse during per-file adaptation and 32 whole-file parses during 32 candidate-verification calls** on both OS. This is non-gating TASK-014 P3 observation, **not TASK-019/E-035 hardware-normalized performance evaluation**.
- A future resource-bounded source-/snapshot-/path-/SHA-bound read-only validated parse context can reduce redundancy **only if** each candidate's items, fields, conditions, nested RawNodeRef backing and canonical whole-source provenance remain checked. Never reuse across different snapshots or changed bytes.
- PR #33 is **partial TASK-014 Phase C2 only**. Independent technical re-review, owner merge and **new real main** Ubuntu/Windows Package+Documentation success must occur before C3's 13-kind `E-027` evaluation. A separate closure follows after later C3 acceptance.
- Ledger is unchanged except new evidence links: TASK-013 `done`, TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`, active_task=next_task `TASK-014`, TASK-015–022 `todo`, latest_game_version=null, product_implemented=false. No auto-merge, direct main writes, force pushes or unilateral review-thread resolution.
