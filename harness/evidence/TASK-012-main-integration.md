# TASK-012 actual main integration and synthetic closure proposal

Date: 2026-10-11 (Asia/Seoul). Source: authored synthetic fixtures only. This is a **closure PR proposal**, not an actual merge of this ledger update.

## Verified actual implementation merge

- Source PR: https://github.com/Gandalem/stellaris-suppoter/pull/23
- Reviewed final head: `7d95a50a22d29d6cbea2f2af24aecd78321ff444`, verified equal to the merged head. PR #23: `closed / merged=true`, merged at `2026-10-11T13:26:51Z`.
- Previous base/main: `221e0044ab399f99ba1473bb1acf3ea22fd9014f`.
- **Real main merge**: `ec9d4d2b7bd77bb5ff4839a738c1cf79967ff2d1` (parents `221e0044ab399f99ba1473bb1acf3ea22fd9014f`, `7d95a50a22d29d6cbea2f2af24aecd78321ff444`). Verified `main` pointed to this SHA before creating closure branch.
- Source-PR temporary **test-merge** `3e99c5413929a1a5447dd3cdbb19c2989e9b6134` is not real main.
- Final independent technical review: https://github.com/Gandalem/stellaris-suppoter/pull/23#pullrequestreview-5483469820 — prior R1–R6 P2 technical holds cleared. Review state is **COMMENTED**, not formal GitHub `APPROVED`. Owner actually merged source PR; no automated merge was performed here.

## Verified real main push CI (not temporary PR CI)

- **Package and tooling**: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38143205499 — `main` `push`, exact SHA `ec9d4d2b7bd77bb5ff4839a738c1cf79967ff2d1`; Ubuntu Python 3.11 **448 passed**, Windows Python 3.13 **445 passed, 3 pre-existing skips**; `python -m ruff check .` succeeds on both; `python scripts/check_harness.py` returns `harness_valid=true` both OS.
- **Documentation harness**: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38143205537 — same real main SHA, Ubuntu/Windows both jobs completed successfully.
- Four CI jobs successful. All previous regression tests retained; six R6 synthetic cases included, along with R1–R5 follow-ups. These runs validate the merged implementation and pre-closure ledger, not the yet-unmerged closure PR.

## Source and citation correctness (synthetic verified scope)

- Immutable `snapshot_id` fixed across retrieval and formatting, SQLite v1 unchanged, bounded `answer_entity(snapshot_id,entity_key)` without loading all entities.
- Every technology fact uses its own field and value SourceRef, validated against original cached SHA-256, snapshot/source-kind/source-ID/relative path/file hash, UTF-8 boundaries, exact byte ranges and physical line numbers. Parser AST binds field name, operator, ordered occurrence, direct-child value spans and parent definition.
- **R1** blocked borrowing valid field refs from another file; **R2** rejected substring-label, operator, occurrence or field/value span forgery; **R3** preserved exact technical name lookup even when the name contains unsupported-computation keywords; **R4** added answer-wide 64 facts, 256 citations and accounted 64KiB payload limits, with a bounded verified source cache; **R5** retained separately typed match/display provenance (independent match language remains unknown when not supplied by retrieval); **R6** compared original parser root technology ID to candidate JSON/SQLite row/SearchHit IDs and kinds, verified source coordinates, occurrence and deterministically recomputed entity key. Malformed source binding fails closed (`SOURCE_CHANGED` and no results).
- Translation root SourceRef stays separate from technical definition SourceRef. Ordered dependent `$KEY$` source refs and actual selection languages are retained, including Korean root/English dependent synthetic case. Cache corruption or forged snapshot produces `error`, no unverified facts.
- E-023 `pass`: field-level byte-accurate citations, BOM/CRLF, original vs localisation provenance, corrupt nested reference and forged ID/ref cases; E-024 `pass`: no fabricated unknown ID/probability/dynamic or computed costs, distinct unsupported/not_found/partial/ambiguous; E-025 `pass`: stable/beta and active snapshot isolation, unknown game version remains unknown. **Pass means synthetic evaluation only.**
- Previous evidence remains unchanged: `harness/evidence/TASK-012-static-answers-citations.md`, `harness/evidence/TASK-012-review-followup.md`.

## Limits and unsupported semantics

- No installed game content used; no game-engine execution, research probability, combat win rate, real research completion time, calculated effective cost, mod applied effects, actual condition truth, inferred patch version or dynamic-expression execution.
- No real Stellaris version or installation compatibility claim; `latest_game_version=null`, `product_implemented=false`.
- Answer 64KiB is an **accounted payload** budget, not a full serialized JSON or process RAM cap. The 24MiB verified retained blob cache is not a peak-RSS measurement; large-scale cold index time, 10k full SearchService p95, FTS5 on/off acceleration, and hostile same-path TOCTOU remain unverified.

## Closure proposal and strict TASK-013 gate

- **This closure PR proposes** TASK-012 `doing→done`, F-009 `in_progress→verified` **for the implemented synthetic scope only**; E-023/024/025 retain `pass`, prior evidence kept and actual-main integration evidence appended.
- Proposes `active_task=null`, `next_task=TASK-013`; TASK-013 stays `todo`, F-011 stays `planned`, E-026 stays `not_run`, F-005 stays `in_progress`. Previous TASK-003/TASK-011 and features retain completed/verified state.
- No functional code change, new CLI, game file read, schema migration, automatic merge, review-thread resolution, protection change or direct `main` write.
- Separate closure PR requires independent owner review, its **own actual test-merge** Package/Ruff/harness/Docs Ubuntu+Windows checks, then an actual owner merge and **subsequent real main push Package/Docs success** before any TASK-013 branch/implementation may start.
