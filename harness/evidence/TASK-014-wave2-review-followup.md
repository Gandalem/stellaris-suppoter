# TASK-014 Phase A PR #29 — R1/P2 diagnostic-budget review follow-up

Date: 2026-10-12 Asia/Seoul. **Authored synthetic fixtures only.** This follow-up preserves the original `TASK-014-domain-adapters-wave2.md`, `TASK-014-foundation.md` and `TASK-014-foundation-review-followup.md` unchanged.

## Review target, reproduced fault and security impact

- Original R1/P2 [review #5486207528](https://github.com/Gandalem/stellaris-suppoter/pull/29#pullrequestreview-5486207528): reviewed PR head `6eb1d4786b1b219ff3caefbd226ed35ed620ade8`; actual base main `762636db1ffef1ef66d032b5e55d485f26ab4a11`. The PR was open/unmerged; initial test-merge `3169fc8f88f02bb78b4255005e1c4207c2bbec20` was not a main merge.
- **Test-only red commit** `bb784181ac65535094ef9f4452478d8eb0eb9f27` added `tests/test_domain_wave2_review_followup.py` without modifying the adapter. [Red PR Ubuntu Package #38198691417](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38198691417): **4 failed / 605 passed**. These were actual pytest results, not just reviewer inference.
- Before repair, 1,200 synthetic direct government children, each without `name`, produced **1,200 `_make_candidate` calls** even though the shared diagnostic budget is **1,000**. Final return: `blocked=True`, **one `LIMIT_EXCEEDED` diagnostic** and **zero candidates**. There is no false normal result, but 200 excess candidates and diagnostics were created unnecessarily.
- 1,200 unsupported bare scalar children led to **1,200 `_raw_node` calls** before the same single error/blocked/empty result. Mixed 250 unsupported scalars followed by 1,000 missing-name definitions created **1,000 candidates** before stopping; correct bound is **750 candidates**. One parser `PARSE_UNKNOWN_SYNTAX` diagnostic plus one unsupported child should leave budget for only **998 missing-name candidates**; before repair it created **1,200**.
- Evidence from red run is Ubuntu only. Older Windows jobs can be superseded/cancelled and are not claimed as reproducing the initial red test.

## Targeted fix

In `src/stellaris_supporter/domain/generic.py` `_adapt_bound_domain`, introduce `stop_at_diagnostic_limit` shared by the existing top-level definition loop and the new `nested_identifier` **inner child loop**. The helper checks the combined parser+adapter `diagnostics` count and returns `DomainAdaptResult(candidates=(), diagnostics=(LIMIT_EXCEEDED,), unhandled=(), complete=False, blocked=True)` when it reaches the existing `DEFAULT_PARSER_MAX_DIAGNOSTICS` (1,000). Each nested child now triggers the check **immediately after** `accept(child)` or `retain_unsupported(child)`, before another raw projection/candidate is constructed.

This does not change the diagnostic threshold or exceed it, and it preserves unlimited diagnostic-free valid definitions within existing parser token/node/byte budgets. No changes were made to R1 full `items`/`fields`/`conditions` recursive backing verification or R2 canonical source-bound `ParseResult` comparison.

## Green regression evidence and call-count contract

- **Code fix:** `447dfac5b4b676310fb61f7279fc211c2290649a`. Its [PR Ubuntu Package run #38198783774](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38198783774) ran **609 passing pytest cases (including all 12 new authored cases)**. Ruff caught one unnecessary explicit UTF-8 `encode` argument in the *new test file*; corrected without changing the test logic in `494dddad233360fdc01f9f8b319bc9e8e187aa42`. Thus the **code-only green run is not represented as complete CI success**.
- New parametrized regression assertions, which ran green: 999 name-missing definitions -> 999 builds, unblocked, 999 warnings/999 candidates; 1,000 -> exactly 1,000 builds, blocked/one `LIMIT_EXCEEDED`/zero candidates; 1,200 -> **only 1,000 builds**, blocked/one `LIMIT_EXCEEDED`/zero candidates.
- Unsupported children: 999 -> 999 raw projections/unblocked; 1,000 -> 1,000 projections/blocked; 1,200 -> **1,000 projections/blocked**. Mixed 250 unsupported + 1,000 name-missing -> **750** builds/blocked. One parser diagnostic + one unsupported child + 1,200 missing-name definitions -> **998** builds/blocked. All reject `complete=True` when the limit is reached.
- **1,200 valid government definitions with unique static `name` fields remain complete** with no diagnostics and all candidate IDs retained. Same-ID nested government definitions remain `ambiguous` with separate occurrence and verified SourceRefs. Previous four adapter kinds and new trait/civic/origin functions remain untouched; full existing test suites verify regressions.
- New regression also verifies unchanged R1 forged government `cost=100`/other backing `999` rejection, unchanged R2 foreign empty `ParseResult` rejection, and existing hard parser depth stop. New test count: **12**, not a deletion or skip.

## Documentation P3 and non-gating follow-ups

`docs/PARSING.md` now explicitly marks the outdated four-domain foundation inventory as **historical**; current unimplemented kinds are tradition, ascension perk, event, scripted trigger, scripted effect. It distinguishes absent `localisation_key=None` (cannot resolve a name) from a verified static localisation key with missing translation (resolver falls back to that key, **not** a separate game ID).

Known P3 performance issue is unchanged: validating 32 separate candidates can require 32 full-file canonical reparses. Consider a future source/SHA/snapshot/path-bound cached verification context without relaxing R1/R2, but do **not** claim TASK-019 performance evaluation.

## Final CI and remaining merge gate

This follow-up Evidence is committed *with* the above documentation and ledger evidence links, so it cannot embed its own final Git commit SHA before Git creates it. The **actual final head, temporary PR test-merge SHA, exact final head push CI, Ubuntu/Windows Package, Ruff, harness, Documentation job results and checkout SHAs must be validated and posted in PR #29's review-request comment after this Evidence commit**. Do not substitute earlier head CI for final commit CI.

All PR #29 changes remain a **partial** TASK-014 Phase A. Preserve TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`, TASK-015–022 `todo`, active/next `TASK-014`, latest_game_version `null`, product_implemented `false`. No PR merge, main writes, old review-thread resolution, Phase B or full E-027; owner merge and actual main CI are future gates.
