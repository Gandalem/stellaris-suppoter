# TASK-011 Retrieval Service

Feature F-008; evaluations E-020, E-021, E-022.
Dedicated branch `task/TASK-011-retrieval-service`; starting actual main `458743fb189edcd4aeeda4e51c72204071801c31`.

## Dependency
TASK-010 done and F-007 verified on main after PR #20 merged and Package 38134576804 / Documentation harness 38134576805 succeeded on both operating systems.

## Scope
Typed Query, SearchHit and SearchResponse; deterministic game ID/name/verified alias/prefix/substring/description lexical search. Snapshot-scoped bounded repository batch reads for rebuilding a reusable, ephemeral SQLite projection. Runtime FTS5 optional; non-FTS exact and short Korean substring paths always available. Preserve source refs, duplicate definitions and partial/unknown outcomes.

## Acceptance
E-020: exact ID, Korean/English names and evidence-backed aliases, collision, rank and stable ties.
E-021: NFC/NFD, casefold, spaces, short Korean, FTS available/unavailable, language and ID fallbacks.
E-022: SQL/FTS literals, limits and bad queries, snapshot isolation, bounded results and integrity fail-closed.

## Explicit exclusions
No game file mutation or parsing within SearchService, LLM, web, game effects, dynamic evaluation, automatic schema migration, cache-inclusive backup/restore, answer formatter or CLI search/show. Do not claim actual game/version validation.

## Test gate
`python -m pytest`; `python -m ruff check .`; `python scripts/check_harness.py`; Ubuntu 3.11 and Windows 3.13 Package and Documentation harness. Record actual test-merge SHA/head and nonblocking performance only if measured. Evals remain not_run until actual results verified.

TASK-011 remains doing and F-008 in_progress until independent review, merge and main CI.
