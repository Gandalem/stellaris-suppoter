# TASK-009 / PR #17 R5 normative contract follow-up

Date: 2026-10-11 (Asia/Seoul)  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/17  
R5/P2 review: https://github.com/Gandalem/stellaris-suppoter/pull/17#pullrequestreview-5482735102

## Context and historical evidence

- Baseline main: `e49ab75153d695b92614b2db3a0e54136f148e37`.
- Blocked R5 review head: `679c327c5b2c940c8a886d6b088b3008e0b62599`.
- All four earlier R1-R4 findings were technically verified as addressed in the review. No product code or existing regression tests were modified for R5.
- Earlier `harness/evidence/TASK-009-localisation-reader-resolver.md` and `harness/evidence/TASK-009-review-followup.md` remain unchanged. Their previous SHAs and CI runs are historical facts, not the final R5 candidate.

## R5/P2 — reproduction and repair

**Before:** In the GitHub PR head `679c327`, `docs/DATA_CONTRACTS.md` had 98 lines. Its first `LocalisationResolution` paragraph ended with the malformed `\`$KEY# 데이터 계약 v1`. The source, snapshot, AST/diagnostics and entity/localisation sections appeared twice; the second duplicate contract had also lost the exact protected-reference syntax. The document harness still passed, exposing a gap between link/ledger checks and semantic Markdown integrity.

**Repair:** On the *same PR #17 branch*, removed only the duplicate document introduction and repeated normative sections, restoring a single `LocalisationResolution` contract. The document has 58 lines, exactly one top title, and the ordered sections `출처`, `스냅샷`, `AST·진단`, `엔티티·관계·현지화`, `질의·답변` and `저장 구조` once each. Existing `SourceRef`, snapshot, query, storage and schema-version sections remain intact.

The restored contract explicitly distinguishes:
- requested language → English → original ID, `fallback=none|english|id` and actual selected language/source.
- `resolved` as fully statically resolved, `partial` as unsupported/incomplete/limited, `unresolved` as missing requested/English translation and ID fallback, `ambiguous` as undetermined duplicate precedence.
- Static `$KEY$` expansion **only outside** protected bracket, icon/colour and unsupported-escape regions; protected raw text and references inside are not rewritten or selected as static references. The game engine's dynamic text is not executed.
- Reference selection provenance, the original technology/source separation, diagnostic codes, bounded visit/depth/scan/output limits, `truncated` and `LIMIT_EXCEEDED`.
- This describes in-memory TASK-009 contracts, not a completed TASK-010 DB persistence schema.

## Prevention: normative Markdown regression

Added `tests/test_normative_document_integrity.py` with **11 pytest cases** in addition to existing tests. It validates all five current core normative documents: `docs/DATA_CONTRACTS.md`, `docs/PARSING.md`, `docs/REQUIREMENTS.md`, `docs/ARCHITECTURE.md`, `docs/TESTING.md`.

Structural checks: exact ordered unique top and section headings, no embedded repeated title, paired inline backtick delimiters outside fenced code, balanced code fences. Semantic checks: mandatory source/snapshot/localisation/reference contract text, exact `$KEY$` syntax, protected-region restriction, requested→English→ID fallback, `partial/unresolved/ambiguous/truncated` meaning, and resource limits; plus architecture and testing command/contract anchors.

Negative tests inject the R5 broken `$KEY# 데이터 계약 v1` string, duplicate source section, remove required protected-reference syntax, break PARSING's inline reference code, and remove a crucial semantic clause while leaving Markdown syntactically valid. The guard fails these mutations by design. The previous R3 test for PARSING remains.

## Actual test progression (no hidden failures)

Initial candidate CI `38128230307` failed on pytest collection: a test-file generation replacement string containing dollar/backtick characters was interpreted by the editing script as substitution syntax, accidentally duplicating test source. The file was restored from the preceding known-good GitHub blob, without weakening existing tests.

Next candidate CI `38128294499` ran 278 passing tests and one new guard failure: the guard initially did not count valid inline-code closing backticks directly following a literal backslash. Changed the guard to count single backticks regardless of preceding backslash, still excluding fenced blocks and checking semantic anchors. No normal document was changed to hide that false positive.

These candidate failures were real and fixed before claiming success; prior CI results remain visible in GitHub.

## Verified final code + test candidate

- Code/docs/test head: `eb5b68b377e7ba6566173543faf0a784de575b21`.
- PR CI test-merge checkout: `03718d748bda4ba12ba708d3268a5c142cd4c53d` (not an actual merge to main).
- Package and tooling PR run `38128348984`: both OS **success**.
  - Ubuntu Python 3.11.17: **279 passed**.
  - Windows Python 3.13.15: **276 passed + existing 3 intentional POSIX-only skips**.
  - `tests/test_normative_document_integrity.py`: **11 passed**, both OS.
  - Existing localisation 50 tests and R1–R4 follow-up 38 tests retained, both OS without newly skipped tests.
  - `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py`: success on both OS.
- Documentation harness PR run `38128348992`: Ubuntu/Windows success.
- Historical main base and code tested are explicitly distinguished from PR test-merge candidate.

## State and constraints

- E-015/E-016/E-017 remain `pass` with original evidence retained. This file adds R5 repair/protection evidence without retroactively changing those test results.
- TASK-009 stays `doing` until independent review, actual main merge and successful main push CI.
- F-005/F-006 stay `in_progress`, TASK-010 stays `todo`, latest_game_version remains `null`.
- No actual Stellaris/game/DLC/mod files read or modified. No real-game syntax compatibility or engine behaviour asserted.
- No PR auto-merge, existing review thread resolution, branch protection change, storage schema implementation or DB migration.
- Final evidence/ledger-only head gets a subsequent PR CI; the final CI IDs and test-merge SHA are recorded in the PR body to avoid self-referential Git SHA claims in committed evidence.

**R5 technical re-review is still required.** A green CI and COMMENTED review are not formal GitHub required approval or completed integration.
