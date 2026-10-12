# TASK-014 Phase C1 PR #32 — R1/P2 event ID qualification follow-up

Date: 2026-10-12 (Asia/Seoul). **Authored synthetic event grammar only**, not an installed Stellaris-version compatibility claim.

## Review anchor and change boundary

- [Original technical review R1/P2](https://github.com/Gandalem/stellaris-suppoter/pull/32#pullrequestreview-5489970509): reviewed head `7ecd4132687cfb638c8c1f45cac711a39451d964`, base main `57ac44ce594ec5090f69b76d68db52db8d0afe48`, temporary pre-fix PR test-merge `41d27b5c0f31fae25d939534749dd42a898a539b`.
- PR #32 same original branch `task/TASK-014-domain-adapters-wave4-event`, **never** direct main modification or automatic merge. C1 Event adapter, namespace declaration provenance and original 35 authored synthetic regressions preserved. Source definitions and all prior `harness/evidence/TASK-014-domain-adapters-wave4.md` evidence retained.
- Fix is constrained to `src/stellaris_supporter/domain/event.py`, new `tests/test_domain_event_id_qualification.py` and documentation/evidence links. The common `generic._ID` regex remains untouched, preventing collateral modification to the ten existing synthetic kinds.

## Actual pre-fix red reproduction

- **Tests-only head:** `4b9a72ef1329568daff8b77fac9de6b858bf5d68` added **10 parameterized regression cases** (6 invalid for country/planet types and 4 valid). This commit was **before** the event implementation change.
- [Head-push Package run #38242013102](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38242013102), Ubuntu Python 3.11 **job #114786676795** completed with pytest **6 failed, 694 passed**. The run itself later became **cancelled** after a subsequent push superseded it; this does **not** negate its completed Ubuntu red job. The Windows job was cancelled and is **not** counted as a red execution.
- All six failing cases were `authored.`, `authored..1`, `authored.1.` for both `country_event` and `planet_event`. Each actually returned `(complete=True, resolution='raw_definition', support_level='synthetic_static')` although the regression expects `(False,'partial','partial')`. The originally separate `authored.1` and `authored.example` positives passed. This was a real GitHub Actions pytest assertion failure, not simply static reasoning.
- Each regression fixture constructs an exact `SourceContext(snapshot_id='A', source_id='authored', source_kind='synthetic', relative_path='events/invalid_suffix.txt', sha256(actual_raw))`; asserts original literal `game_id`, exact `id_source_ref.raw_bytes(raw)`, snapshot/path and normal `verify_domain_candidate` grounding. No external game files used.

## Minimal implementation and explicit synthetic policy

- **Event-only regular expression:** `(?P<namespace>[A-Za-z_][A-Za-z0-9_]*)\.(?P<suffix>[A-Za-z0-9_]+)\Z` with fullmatch. Exactly **one ASCII dot** separates a nonempty static namespace from a nonempty suffix. Suffix permits ASCII letters, digits, underscore. Missing suffix, adjacent/repeated dots, leading/trailing dots, further dotted segments, hyphens/other separators in the suffix are outside this *limited authored synthetic policy*.
- Valid literals `authored.1`, `authored.example` and `authored.alpha_2` remain normal when `namespace=authored` is verified. `authored.`, `authored..1`, `authored.1.`, `authored.1.2` become explicit `DOMAIN_EVENT_INVALID_QUALIFIED_ID` warnings with exactly the original `id_source_ref`, `resolution='partial'`, `support_level='partial'`, `complete=False`. Unqualified literals keep `DOMAIN_EVENT_UNQUALIFIED_ID`; well-formed other prefixes keep `DOMAIN_EVENT_NAMESPACE_MISMATCH`; missing/conflicting/invalid declarations keep existing namespace diagnostics. No missing segment is invented and no event is executed.
- Event qualification is validated even if a namespace declaration is missing (those candidates were already partial). New diagnostics count against the **existing** shared parser+namespace+adapter 1,000 limit, using existing bounded `candidate_warning`. The regex does **not** widen parser budgets, weaken R1/R2, change public DomainCandidate/Field/Diagnostic, or alter old 10-domain ID extraction rules.
- Post-fix test file additionally locks `authored.1.2` rejection and `authored.alpha_2` acceptance: **14 new parametrized pytest cases** in total (8 negative, 6 positive). The first six negatives are supported by the real before-fix failing job; added policy cases were written following the source fix. They coexist with (do not replace) the original Event 35 and prior ten-domain tests.

## Required whole-suite regression and security matrix

The final PR CI must execute the entire pytest suite plus `python -m ruff check .` and `python scripts/check_harness.py` on Ubuntu Python 3.11 and Windows Python 3.13. Existing `tests/test_domain_event.py` and earlier wave1/2/3/Technology/Search/SQLite/CLI suites remain unmodified and unskipped. They cover the full C1 existing matrix: both event types, namespace missing/identical/conflicting/mismatched, static/duplicate/missing/dynamic IDs, same-file/other-file/cross-kind collisions and `definition_occurrence`, id/name distinction, Korean/English resolver/fallback/root/dependency SourceRefs, R1 independent item/field/condition/nested raw backing tamper and field loans, R2 foreign/empty canonical ParseResult/token/AST span/line/column/SHA, invalid UTF-8, BOM/CRLF/Hangul, parser+adapter diagnostics including 999/1000/1200, 1,200 warning-free events and one-candidate 1,200 bad operators. Original API and source integrity contracts are not reduced.

## Final exact-head CI publication rule

The evidence and code are committed **before** the final PR test-merge SHA exists. The final `head`, `main` base, actual PR test-merge SHA and **all four real checkout logs**, exact final-head push Package, Ubuntu/Windows pytest counts, Ruff/harness, Documentation harness and outcomes must be independently retrieved and linked in a **new PR #32 final-head technical re-review request comment**. The PR discussion is the canonical append-only, SHA-pinned live follow-up evidence (do not invent a future commit SHA inside its own content). The original wave4 evidence stays unchanged.

## Outstanding P3 and later gates

For a given authored source file with 32 candidates, the measured implementation performs **1 canonical parse for adaptation and 32 for separate per-candidate verification**. Do not remove canonical ParseResult validation (R2) or recursive RawNodeRef independent backing checks (R1) to optimize. A future source-/snapshot-/path-/SHA-bound read-only validation context with bounded resource use can be considered separately; the non-gating 32-candidate microbenchmark is **not** TASK-019/E-035 acceptance.

PR #32 remains a **partial** TASK-014 C1 implementation until independent technical review, owner merge and actual new main cross-OS Package/Documentation success. C2 Scripted Trigger/Effect and C3 entire 13-domain E-027 evaluation are not started. TASK-014=`doing`, F-005=`in_progress`, E-027=`not_run`, TASK-015–022=`todo`, active_task/next_task=`TASK-014`, latest_game_version=`null`, product_implemented=`false`. No real game-version validation or release approval.
