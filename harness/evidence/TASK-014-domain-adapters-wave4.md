# TASK-014 Phase C1 — event / namespace synthetic adapter evidence

Date: 2026-10-12 Asia/Seoul. **Authored synthetic fixtures only; not real Stellaris data or engine semantics.**

## Verified start and merge gates

- C1 base actual `main`: `57ac44ce594ec5090f69b76d68db52db8d0afe48`.
- PR #31 Phase B owner-merged as `2f35fb958ce1472efb460fac1cc3704eb809b7a6`, followed by PR #30 owner-merged as `57ac44ce594ec5090f69b76d68db52db8d0afe48`. At C1 branch creation there were no open PRs and no pre-existing Phase C branch.
- [Real main Package CI #38237779265](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38237779265): Ubuntu Python 3.11 **655 passed**, Windows Python 3.13 **652 passed + original 3 skipped**, Ruff and harness both OS success.
- [Real main Documentation harness #38237779261](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38237779261): Ubuntu and Windows success. All four jobs' actual checkout SHA was the real `57ac44ce594ec5090f69b76d68db52db8d0afe48`, not a PR test-merge. The earlier state note describing PR #30 as unmerged is **historical**, not removed.

## Event synthetic ID and namespace rules

- Registry `event`, investigation path `events/` (not validated from a game installation); accepted top-level types **country_event** and **planet_event** only. All others remain unknown/unhandled original ordered AST with explicit diagnostics.
- `namespace = authored` is a file-local static declaration; each identical declaration is recorded with its own `DOMAIN_EVENT_NAMESPACE` informational SourceRef. Conflicting/invalid/missing declarations are partial. Other files' namespace declarations are **not** presumed effective. Fully qualified `id = authored.1` must agree with the verified namespace; an unqualified, dynamic, absent or multiply declared `id` remains partial.
- Type name, namespace itself, filename, input order and nested `country_event = { id = ... }` under `immediate` never become independent event IDs. Nested/event-related trigger/condition/effect expressions remain raw bytes and ordered fields, never executed, calculated or precedence-resolved.
- A unique static `title = authored_title` is the authored synthetic display `localisation_key`, distinct from `game_id`. Dynamic/missing/duplicate title is partial. Existing KO/EN static resolver supplies optional root/dependency SourceRefs, English/ID-key fallback, duplicate, cycle, unsupported dynamic and bounded-output handling.
- No new fields or schema changes to public `DomainCandidate`, `DomainField`, `DomainDiagnostic`, `DomainAdaptResult`. The event-specific parser is called **only after** generic `adapt_domain` validates exact source SHA, source_id, path, snapshot, whole-file canonical ParseResult including AST/token coordinates (R2), and hard parser/lexer resource budgets. Candidate verification re-parses through this same event branch, compares all ID/field metadata and checks all independent `items`/`fields[].value`/`conditions[].value`/recursive child backing bytes (R1).
- File-wide parser+namespace+adapter diagnostics share the same 1,000 budget. 999/1,000/1,200 thresholds count namespace info; reaching the limit fails closed as `LIMIT_EXCEEDED`, `blocked=True`, empty candidates. One candidate with 1,200 unsupported operators cannot allocate all raw projections due to inherited preflight.

## Actual red-to-green CI stages

- Tests-only head `2e2de0d4a3777d5fea4cdb4006ad77c34a276682`, [Ubuntu push Package run #38239640359](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38239640359): **35 failed (new Event cases), 655 passed (existing)** before implementation. Failures were `unregistered domain adapter` / `KeyError: event`, not guessed.
- Initial source-implementation head `80bbaf3e3aa1944d095bb220e50dbbafc30463d6`, [Ubuntu Package #38240017042](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38240017042): **690 pytest passed** (all 35 new regressions); Ruff flagged the new `domain.Literal` annotation and test import formatting; these two lint defects were corrected on the branch prior to final PR submission. This intermediate run is **not** a claim of final all-green CI.
- `tests/test_domain_event.py` has 35 authored synthetic test cases including both event wrappers, namespaces (same/conflicting/missing/foreign/invalid), ID/title ambiguity/dynamics, file/type duplicate and cross-file/snapshot collision, nested raw non-extraction, fake comments, R1 cost 100→999 backing + field loan + condition/child tampering, R2 external/empty AST + token/line/column SHA, BOM/CRLF/Hangul/malformed UTF-8/hard limits, localisation KO/EN fallback/root/dependency/cycles/dynamic/resource budget, parser+adapter cumulative diagnostics and 1,200 valid events.

## Non-gating P3 measurement and remaining work

- New `scripts/bench_domain_event.py` observes 32 authored synthetic event candidates with three repetitions, recording SHA, OS/Python, adapter calls vs individual verification canonical re-parses and milliseconds. Expected 1 parse/adaptation and 32 parses/32 separate verifications. It runs as non-gating Package CI on both OS and is **not** TASK-019/E-035 acceptance.
- A future source-bound read-only context could reuse the validated immutable ParseResult only when **snapshot_id/source_id/relative_path/SHA-256/source bytes** agree, have bounded memory/time and retain per-candidate raw backing checks (R1) and canonical whole-source trust gate (R2). Cross-snapshot reuse and stale contexts must remain rejected. This improvement is separate from the narrow C1 safety requirements.
- **Remaining Phase C2:** Scripted Trigger and Scripted Effect; then **C3:** 13-domain `all-domains` E-027 normal/error/collision/localisation/tamper runner and evidence. Real game syntax, version and engine semantics are not verified. No multi-domain SQLite v1/index/CLI integration or overlay UI claimed.
- E-027 is `not_run`, TASK-014 remains `doing`, F-005 `in_progress`, TASK-015–022 `todo`, latest_game_version `null`, product_implemented `false`.

## Exact-head PR verification gate

This document is committed before C1 PR creation and intentionally cannot predict its final SHA. The **actual PR number, final head, temporary PR test-merge SHA, exact head push Package, PR Ubuntu/Windows Package, Ruff/harness, PR Documentation both OS and actual four PR job checkout SHAs** must be checked and recorded in a final-head PR review request. An initial green code-only pytest run is not sufficient. C1 stays open until independent review and owner merge, followed by actual new main cross-OS CI. No auto-merge, direct main update, older review-thread resolution or Phase C2/TASK-015 advancement.
