# TASK-009 actual main integration and closure evidence

Date: 2026-10-11 (Asia/Seoul)  
Source branch: `task/TASK-009-localisation-reader-resolver`  
Integration source: https://github.com/Gandalem/stellaris-suppoter/pull/17  
Closure proposal: separate `chore/TASK-009-main-integration-closure` branch; do **not** merge without review.

## 1. Actual PR #17 merge versus the earlier test-merge

- The reviewed implementation head was `c4842aaae6f88216f33711d6a95b141074e2dad5`.
- Real PR #17 GitHub state: **closed / merged=true**, merged 2026-10-11T09:36:24Z.
- **Actual main merge commit:** `f9638850dfd514790cf90c194f9ff062e7819f12`.
- The current `main` branch was verified to point to the same commit at the start of this closure task.
- The previous pre-merge CI checkout `d82b56d158f0f0486fabd99f7f58d386df0a401a` was only a test-merge candidate, **not** the actual main integration.
- Final technical review: https://github.com/Gandalem/stellaris-suppoter/pull/17#pullrequestreview-5482768133. The reviewer confirmed the R1-R5 correction scope and removed the technical hold for the exact reviewed head. It was recorded as `COMMENTED`, **not formal GitHub APPROVED**; do not infer an independent required approval event.

## 2. R1-R5 defect closure and existing historical evidence

- **R1/P2**: Regexp backtracking on long malformed whitespace prefixes replaced by forward-only index scanner; indexed-character growth and size-boundary regressions.
- **R2/P2**: Dynamic bracket / icon / colour / unsupported escape regions protected before static `$KEY$` expansion; missing/cycle/duplicate reference and provenance cases retained.
- **R3/P2**: Repaired the duplicated/truncated `docs/PARSING.md` localisation section and added contract assertions.
- **R4/P3**: Record budget charged before every header, entry, comment and unknown append; precise at-limit EOF and over-limit cases.
- **R5/P2**: Restored `docs/DATA_CONTRACTS.md` protected `$KEY$` contract and removed duplicated source/snapshot/AST/entity sections; 11 normative documentation tests across five core docs.

Historical evidence is retained without modification:
- `harness/evidence/TASK-009-localisation-reader-resolver.md` (initial E-015-E-017 implementation and earlier candidate).
- `harness/evidence/TASK-009-review-followup.md` (R1-R4 and independent scoped CPU helper measurement).
- `harness/evidence/TASK-009-r5-document-integrity.md` (R5 and candidate failures/recovery).

The new actual-main evidence does not retroactively change their earlier head/test-merge/CI history.

## 3. Actual main push CI — verified from workflow and job logs

**Package and tooling:** https://github.com/Gandalem/stellaris-suppoter/actions/runs/38128971447

- Event: `push`; branch: `main`; head: `f9638850dfd514790cf90c194f9ff062e7819f12`; status completed; conclusion success.
- Ubuntu Python **3.11.17**: `python -m pytest` **279 passed**; `python -m ruff check .` success; `python scripts/check_harness.py` success (`harness_valid=true`).
- Windows Python **3.13.15**: `python -m pytest` **276 passed + 3 pre-existing intentional POSIX-specific skips**; Ruff success; harness success (`harness_valid=true`).
- The three Windows-only skips are the pre-existing POSIX surrogateescape inventory test and two POSIX-calibrated lexer memory/wall-clock assertions. No new localisation or documentation skip was introduced.
- Existing 50 localisation tests, 38 R1-R4 review cases and 11 normative document-integrity cases are part of the 279 collected items. Generator, inventory, lexer, parser and technology-adapter regressions remained in the suite.

**Documentation harness:** https://github.com/Gandalem/stellaris-suppoter/actions/runs/38128971437

- Event: `push`; branch: `main`; head: `f9638850dfd514790cf90c194f9ff062e7819f12`; completed **success**.
- Ubuntu: harness valid / job success.
- Windows: harness valid / job success.

These were verified on the **actual main merge commit**, not the previous PR test-merge. `check_harness.py` validates consistency/links and is not a substitute for product tests.

## 4. Acceptance and evaluation trace

- **TASK-002 synthetic corpus** is `done` (E-002 corpus). TASK-009's prerequisite TASK-007 is `done` from prior integration.
- **TASK-009** implementation exists on the above merged main commit. Required acceptance: fallback, references, cycles and duplicates have explicit results. The same code was tested against wholly authored synthetic fixtures.
- **E-015** Language fallback: `pass` — requested Korean, English fallback and ID fallback with chosen language/SourceRef provenance and reference language provenance.
- **E-016** Localisation cycle: `pass` — self/multi-key cycles, missing references and bounded depth/visits/scanned bytes/output.
- **E-017** Duplicates and dynamic text: `pass` — preserve duplicate occurrences, ambiguity, dynamic/unsupported expressions, raw quoted values, BOM/CRLF/multibyte byte spans and malformed input diagnostics.
- **F-006** acceptance (docs/REQUIREMENTS.md): deterministic Korean→English→ID fallback, explicit missing/cycle, no game dynamic execution. TASK-002/TASK-009 + E-015/016/017 + actual main code CI support setting `verified` **for the synthetic-supported implementation scope**.
- **F-005** domain adapters remain `in_progress` because non-technology domain coverage is unfinished. **TASK-010** remains `todo`; E-018/E-019 remain `not_run`; F-007 remains `planned`.

## 5. Proposed ledger transition in this separate closure PR

- TASK-009: `doing` → `done`.
- F-006: `in_progress` → `verified`.
- E-015/E-016/E-017: `pass` maintained, with this additional main-integration evidence.
- F-005: `in_progress` unchanged.
- TASK-010: `todo` unchanged; do **not** mark doing while this closure PR is open.
- `active_task` → `null`; `next_task` → `TASK-010`.
- `latest_game_version` stays `null`; `product_implemented` stays `false`.

These are **proposed on the closure branch only** until this separate PR is reviewed, actually merged, and its own main push CI succeeds. The base main at branch creation still had TASK-009=doing.

## 6. Scope and explicit limits

- Verification used project-authored **synthetic fixtures only**, not real Stellaris/DLC/mod/save files. Real installation compatibility and engine dynamic expression semantics remain **unverified**.
- No game root files were changed, no private source bytes/paths are included, and no migration/search/SQLite repository or TASK-010 functionality is implemented by this closure PR.
- Full test commands for the closure PR are `python -m pytest`, `python -m ruff check .` and `python scripts/check_harness.py`. Only their *actual* final closure-PR CI results should be cited in the PR body after completion. The main results above are from the implementation integration and must not be mislabelled closure PR checks.
- PR merge and existing review-thread resolution require separate reviewer/user action; this closure branch does neither.
