# TASK-010 actual main integration, acceptance, and closure evidence

Date: 2026-10-11 (Asia/Seoul). Scope: authored synthetic fixtures; no actual game installation was inspected.
Source PR: https://github.com/Gandalem/stellaris-suppoter/pull/19
Independent final technical re-review: https://github.com/Gandalem/stellaris-suppoter/pull/19#pullrequestreview-5483037276
Closure proposal: separate branch `chore/TASK-010-main-integration-closure`; PR review and merge remain owner-controlled.

## 1. Actual merge gate (not a PR test-merge)

- PR #19 state was independently rechecked as `closed / merged=true`.
- Final reviewed implementation head: `1e42ba768e358796006f62052da6eca043d48c85`.
- Reviewed base: `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c`.
- Final PR test-merge candidate: `225259c9ef702af476313abefbf1c4bf2a7a5979` (not actual main).
- **Actual merge commit on main:** `0eee7f42ab7d580c89b99aa3b9aa5912bfae10a6` (2026-10-11T10:59:06Z). At the beginning of this closure, `refs/heads/main` matched that SHA.
- The review recorded `COMMENTED`, not an independently granted GitHub `APPROVED`. The reviewer removed the prior technical hold on the exact head after verifying R1–R5.

## 2. R1–R5 final resolution basis

- **R1 physical live source binding:** `stage` records private, game-root-relative physical location and root fingerprint, and `activate` compares them before rehashing live bytes. Synthetic same-content copy, changed original, different root, symlink/reparse and duplicate logical source negative cases reject. This does not close hostile same-path filesystem TOCTOU.
- **R2 raw Unicode preservation:** identity metadata remains NFC-strict; separate bounded storage JSON preserves raw localisation/technology Unicode codepoints, including decomposed Hangul/Latin, BOM/CRLF, and exact SourceRef byte spans.
- **R3 policy identity bounds:** policy JSON has a 1,048,576-byte maximum, depth 32 and 10,000 visited-item budget, snapshot wrapper +128 bytes, and immutable stored `policy_json`. Too-large/mutated policy cases fail closed without changing active.
- **R4 cache/source consistency:** SQLite `CHECK(cache_sha256=file_sha256)` and read-path SourceRef/DB file/cache SHA comparison with blob rehash reject poisoned cache pointers (`SOURCE_CHANGED`) rather than cite an unrelated source.
- **R5 document and read-path tests:** ADR-012/013 remain in one valid table, documentation integrity assertions stay enabled; repeated full SQLite `quick_check` was removed from read-only hot paths while opening/writing/backup retains full checks. Synthetic read-only preflight benchmark is not a retrieval p95 or peak-RSS measurement.
- Historical review and fault-injection details are retained without edits in `harness/evidence/TASK-010-sqlite-snapshots.md` and `harness/evidence/TASK-010-review-followup.md`.

## 3. Real main push CI, checked from jobs and logs

Package and tooling: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38133902254

- Event `push`, branch `main`, head `0eee7f42ab7d580c89b99aa3b9aa5912bfae10a6`; completed/success.
- Ubuntu `ubuntu-latest`, Python **3.11.17**, SQLite **3.45.1**: `python -m pytest` **359 passed**; `python -m ruff check .` success; `python scripts/check_harness.py` success (`harness_valid=true`).
- Windows `windows-latest`, Python **3.13.15**, SQLite **3.50.4**: **356 passed, 3 skipped**; Ruff and harness success (`harness_valid=true`).
- Three existing Windows-specific skips: POSIX `surrogateescape` filename inventory case, POSIX-calibrated lexer tracemalloc peak threshold, and POSIX-calibrated lexer wall-clock regression threshold. No new storage-test skip was added.

Documentation harness: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38133902283

- Event `push`, same **actual main merge SHA**, completed/success; Ubuntu Python 3.11 and Windows Python 3.13 harness jobs both succeeded.
- These are real implementation main-push CI results, **not** new closure-PR results. The separate closure PR must still pass its own Package and Documentation harness on both OS before merging.
- `check_harness.py` confirms ledger/file-link consistency only, not product runtime semantics; the 359/356 pytest counts are the synthetic product regression suite.

## 4. TASK-010 / F-007 acceptance and E-018–E-019

- TASK-010 prerequisites TASK-004, TASK-005, TASK-008 and TASK-009 are `done`; the typed storage implementation and synthetic fixture-based tests are in actual main.
- **E-018 remains `pass`:** deterministic content/snapshot identity, SQLite v1 typed schema, duplicate game_id occurrences, scoped foreign keys, raw localisation/TechnologyCandidate/SourceRef round-trips, schema version rejection, path/policy/manifest bounds and cache-source consistency negative cases.
- **E-019 remains `pass`:** staging `building→ready|partial|failed`, atomic `BEGIN IMMEDIATE` active-pointer activation, previously active snapshot preserved on faults/cancellation/writer lock/cache corruption/live-source change; no incomplete snapshot returned as active.
- SourceRef traces snapshot ID, logical source ID, relative path, file SHA-256 and original byte/line span. Localisation provenance remains distinct from definition provenance. `source_bytes` checks SourceRef, SQLite source/cache metadata, and SHA-256-addressed original-byte cache before returning bytes.
- Reproducible tests include injected failures and R1–R5 negative regressions; the implementation version in actual main passed the platform matrix above.
- Accordingly this **separate closure PR proposes** TASK-010 `doing→done` and F-007 `in_progress→verified` **only for implemented synthetic snapshot storage**. E-018/E-019 retain `pass` with added actual-main evidence.

## 5. Explicit limits and adjacent state

- No real Stellaris installation, beta/stable channel combination, enabled DLC/mod load semantics, or effective-game-state compatibility was verified.
- No automatic SQLite DB migration or cross-v1 upgrade; incompatible schema is safely rejected.
- SQLite backup covers the DB, **not** a complete cache-inclusive backup/restore workflow; required cached source bytes must be preserved separately.
- No peak RSS benchmark, no retrieval-service 10,000-entity warm p95 measurement, and no proof against hostile same-path filesystem TOCTOU or untested Windows ACL races.
- Only snapshot-backed synthetic storage is verified: `latest_game_version=null`, `product_implemented=false`. F-005 remains `in_progress`; F-006 stays `verified`; TASK-011 remains `todo`, F-008 `planned`, E-020–022 `not_run`.
- This closure PR does **not** implement search/FTS, create a TASK-011 branch, merge itself, change review threads or branch protections.

## 6. Closure PR acceptance gate

- Require closure-PR head and real test-merge SHA, Package and tooling Ubuntu/Windows pytest/Ruff/harness, and Documentation harness Ubuntu/Windows results.
- Do not treat closure-PR CI as actual main integration. TASK-011 may start on a separate branch **only after the closure PR actually merges to main and subsequent main-push Package and Documentation harness succeed**.
