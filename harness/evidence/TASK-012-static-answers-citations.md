# TASK-012 synthetic static answers and citations: candidate evidence

Starting `main`: `221e0044ab399f99ba1473bb1acf3ea22fd9014f` — PR #22 merged, Package main push `38138398050` and Documentation main push `38138398039`, Ubuntu/Windows all success. Baseline Ubuntu 409 passed, Windows 406 passed + existing 3 skips. No real Stellaris source is used.

## Implementation
- `answers.AnswerService.answer(Query, field=...)` delegates retrieval to SearchService and pins its returned snapshot before bounded repository row lookup. Never materialises `repository.entities()` for every answer.
- Typed AnswerEnvelope/AnswerContext/AnswerResult/AnswerFact with status, raw field expression, per-fact field+value SourceRefs, root localisation SourceRef and typed nested language selections.
- `SnapshotRepository.citation_bytes()` checks source kind/ID/path/hash, cached original bytes SHA, byte boundaries/UTF-8 and 1-based lines before serving an exact span.
- `AnswerService` checks fields are inside definition, value is inside field, field identifier/operator are actually in cited bytes, original cached value is returned literally, and snapshot ID never changes. It does not evaluate `@variables` or dynamic blocks.
- Missing results produce not_found; unsupported engine questions produce unsupported; duplicate definitions and unresolved expressions remain partial; cache/provenance mismatches yield error with no unverified answer.
- Resource limits: 64 facts, 512 bytes per raw expression, 256 citations, 64KiB output-materialization budget and SearchService's bounded query limit. No automatic migration.

## E-023 / E-024 / E-025
E-023/E-024/E-025 are **pass** for authored synthetic cases on the exact code candidate and CI detailed below.

## Known limits
Literal script tokens are presented as script literals, **not** game-computed effective effects. No official game input, dynamic cost calculation, mod layering, real stable/beta observation or actual research probability. No cold-index/peak RSS or 10,000-entity end-to-end warm p95 certification; FTS5 performance comparison remains follow-up.

## Verified synthetic candidate and CI

- Initial actual base main: `221e0044ab399f99ba1473bb1acf3ea22fd9014f`, itself PR #22's real merge and independently passing main Package `38138398050` plus Docs `38138398039` on Ubuntu/Windows.
- Verified **code/test candidate head**: `c6bb77ebc414089a5179f59ebc6e3c96debcd78c`.
- Actual **PR test-merge checkout**: `3dd13dc19d1eacebeab946af201fe054f5f1d59a` (four CI job logs matched; **not** a real main merge).
- PR Package: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38139133121 — Ubuntu Python 3.11 **428 passed**; Windows Python 3.13 **425 passed + 3 existing POSIX-only skips**; `python -m ruff check .` and `python scripts/check_harness.py` succeeded both OS (`harness_valid=true`).
- PR Documentation harness: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38139133188 — Ubuntu/Windows both success at same test-merge.
- Candidate exact-head Package push run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38139130213 — referenced for exact-head CI verification (its final status must be checked from GitHub Actions before claiming success).
- **19 newly passing authored synthetic pytest cases** compared with the original 409 Ubuntu regression baseline; 3 existing Windows skips unchanged; no test deleted/skipped.
- E-023 **pass, synthetic**: definition vs translation files, field-level exact value byte and CRLF/BOM line spans; Korean root with English nested reference and actual language; wrong line/offset, corrupt technology cache, independently corrupt English dependency cache.
- E-024 **pass, synthetic**: not_found, missing field without fabrication, `@demo_cost` observed as raw unsupported expression rather than a numeric cost, unsupported probability/combat/time/mod/condition questions, duplicate definitions, invalid typed query.
- E-025 **pass, synthetic**: distinct stable/beta snapshots and different static cost/name, explicit selection despite active pointer flips, active switch between search and formatting, cross-snapshot forged SearchHit rejection, game version unknown stays null.
- E-023..025 remain evidence-bound to this candidate only; TASK-012 is still **doing** and F-009 still **in_progress** until independent review and actual main integration. This evidence-only update will generate a new PR head and test-merge requiring another CI check.
