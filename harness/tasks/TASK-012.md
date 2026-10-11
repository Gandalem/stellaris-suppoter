# TASK-012 — Static answers and citations

Feature F-009; evaluations E-023, E-024, E-025.
Base: PR #22 actual main merge `221e0044ab399f99ba1473bb1acf3ea22fd9014f`, Package `38138398050` and Documentation `38138398039` main-push CI successful both OS.
Branch: `task/TASK-012-static-answers-citations`.

## Scope
- Deterministic `AnswerService.answer(Query, field=...)` wraps existing SearchService and pins its returned snapshot context.
- `AnswerEnvelope`, typed `AnswerFact` and per-result cited facts, raw expressions, provenance and diagnostics.
- Repository `answer_entity(snapshot_id,entity_key)` bounded point lookup; `answer_snapshot_context` returns branch/version/context; `citation_bytes` verifies cached bytes, SHA and original UTF-8 byte/line ranges.
- Root translation and nested static reference selections are distinct from definition and field references; no game engine evaluation.

## Acceptance
- E-023 synthetic value-level exact byte span and lines, BOM/CRLF/UTF-8, English dependency and cache tampering.
- E-024 no invented cost/probability/effects; not_found/unsupported/partial/duplicates and missing field.
- E-025 strict stable/beta and snapshot isolation even after active changes mid-query; version unknown remains null.
- Limits: field 512 source bytes, 64 facts, 256 citations and 64KiB bounded materialised field text; query limits inherited from SearchService.

## Exclusions
No TASK-013 CLI, other game adapters, engine, dynamic evaluation, LLM, network, real game input or schema migration. Runtime semantic correctness, 10k end-to-end p95 and peak RSS are unverified.

## Required checks
`python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py`; Ubuntu Python 3.11, Windows 3.13 and Documentation harness on both. Evaluation status stays not_run pending actual CI evidence. TASK-012 doing/F-009 in_progress until independent review and real main integration.
