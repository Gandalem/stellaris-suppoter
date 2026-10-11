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
Initial state **not_run**. Tests in `tests/test_answers.py` exercise synthetic citation-spans (BOM/CRLF/field exact bytes/English references/cache), answer-abstention and version-isolation scenarios. These evals become pass only after actual successful CI logs are verified.

## Known limits
Literal script tokens are presented as script literals, **not** game-computed effective effects. No official game input, dynamic cost calculation, mod layering, real stable/beta observation or actual research probability. No cold-index/peak RSS or 10,000-entity end-to-end warm p95 certification; FTS5 performance comparison remains follow-up.
