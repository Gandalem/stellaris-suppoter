# TASK-013 — actual main integration and official closure proposal

Date: 2026-10-12 (Asia/Seoul). **This document belongs to an unmerged closure PR.** The implementation is already merged; ledger changes here are proposals until a separate owner merge.

## Main integration: verified independently from PR test-merge

- Implementation PR: https://github.com/Gandalem/stellaris-suppoter/pull/25
- Before implementation merge, actual main: `422f6aa06849b2c210905d75bfe47a32e62f0bf4`.
- Independently reviewed and merged PR head: `381c667ffd3246e0ebc2e6ec8ec1bfb2463f30f0`.
- PR state: **closed / merged=true**, merged 2026-10-11 15:10:24 UTC.
- Actual `main` merge: **`8d77794c95d3fe39e3b66f0a8e402efec5a10966`**, parents exactly `422f6aa06849b2c210905d75bfe47a32e62f0bf4` and `381c667ffd3246e0ebc2e6ec8ec1bfb2463f30f0`. Starting main for this closeout branch equals that SHA.
- Earlier PR **test-merge** `83e220a50613a2e821c5c53d3a778ca5976d1ec1` is **not** the main merge.
- Previous blocking review https://github.com/Gandalem/stellaris-suppoter/pull/25#pullrequestreview-5483720276 and final https://github.com/Gandalem/stellaris-suppoter/pull/25#pullrequestreview-5483789153: R1–R5/P2 technical hold cleared. Final review type **COMMENTED**, not independent formal GitHub `APPROVED`; review threads were not resolved here. Actual merge made by owner.

## Real main push CI for exact implementation merge

- Package and tooling **[38150169069](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38150169069)** at `main` push exact `8d77794c95d3fe39e3b66f0a8e402efec5a10966`: Ubuntu Python 3.11 **509 passed**; Windows Python 3.13 **506 passed, three pre-existing skipped**; Ruff both OS success; `python scripts/check_harness.py` both OS `harness_valid=true`.
- Documentation harness **[38150169206](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38150169206)**: Ubuntu/Windows succeeded.
- Four actual main push job checkout logs explicitly fetched and checked out `8d77794c95d3fe39e3b66f0a8e402efec5a10966` (not temporary PR test-merge).
- Existing baseline maintained; synthetic E-026 `pass` preserves [TASK-013-cli-vertical-slice.md](TASK-013-cli-vertical-slice.md) and [TASK-013-review-followup.md](TASK-013-review-followup.md); these are not real-game engine claims.

## Implemented synthetic CLI acceptance (TASK-013 scope)

- Six commands: **`init`, `doctor`, `index`, `search`, `show`, `snapshots`**.
- End-to-end synthetic subprocess/console entrypoint: configuration creation without overwrite; doctor environment diagnostics; inventory → verified parser/adapter/localisation → snapshot staging → checked atomic activation; ID/Korean/English retrieval; exact-ID static field/value `SourceRef` citations; bounded snapshot status listing and JSON/error statuses.
- Source trees remain **read-only**: inventory path guards, SHA checks and verified live file capture. Separate private configuration/SQLite/cache are expected writable. Interrupted/staging/cancellation/security/resource failures preserve the previous active snapshot; partial requires explicit consent, and parser/resolver hard resource limits remain non-bypassable.
- R1: unsafe `--allow-partial` parser/lexer/resolver resource exhaustion blocked (exit 4), including previous partial reuse.
- R2: inventory filters supported technology `.txt` and Korean/English `.yml` for file/byte/hash budget; non-target files retain directory traversal/path/link safety checks.
- R3: TOML `query_chars/max_results` enforced alongside absolute 512 chars/100 hit service ceiling, correctly mapping 2/4.
- R4: complete text `snapshots` columns active, ready/partial/building/failed, context, branch, unknown version, timestamps, pagination/truncated.
- R5: raw control/Bidi characters escaped at human-readable terminal text boundaries only; JSON/source bytes and SourceRefs retain semantics.
- No `refs` or `diff`, live engine calculations, inferred DLC/version/mod effects, or unverified gameplay output.

## Evidence boundary, remaining risks and official ledger proposal

- No real Stellaris installation or DLC/mod compatibility verified. No full enemy same-path TOCTOU proof, cold index time, 10k full-service p95, peak RSS, FTS5 improvement, or actual research/combat/effective cost computation claim.
- P3: read-only search/show/snapshots may create missing DB; source read vs cache/SQLite error code differentiation needs separate review; neither is a TASK-014 adapter acceptance requirement.
- Propose **TASK-013 `doing→done`**, E-026 **`pass` retained (synthetic)** and `active_task=null`, `next_task=TASK-014`; **F-011 stays `in_progress`** because TASK-015 `refs` and TASK-016 `diff` remain `todo`.
- TASK-014 remains `todo`, F-005 `in_progress`, E-027 `not_run`, F-013 `in_progress`, latest_game_version `null`, product_implemented `false`; previous successful state/evidence retained.
- **Gate:** owner-reviewed closeout PR must pass its own Ubuntu+Windows Package/Ruff/harness and Documentation CI, then actually merge to main. That new `main` merge needs its own successful Package/Documentation push CI before TASK-014 can be marked `doing` or any TASK-014 implementation branch created. No automatic merge or direct main change.
