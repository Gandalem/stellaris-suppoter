# TASK-011 retrieval — candidate implementation and evaluation gate

Date 2026-10-11 Asia/Seoul; all fixtures are authored synthetic data.
Starting actual main: `458743fb189edcd4aeeda4e51c72204071801c31` (PR #20 merged).
Prerequisite main CI: Package [38134576804](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38134576804) and Documentation harness [38134576805](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38134576805), Ubuntu/Windows success.

## API and design
- `retrieval.py`: typed Query, SearchService, SearchResponse/Hit/Diagnostic/Context, VerifiedAlias. ID exact, normalized name exact, explicit verified alias exact, prefix, substring, description lexical; stable kind/game_id/path/occurrence/key tie-break and match_reason.
- Normalise **search copies only**: NFC, casefold and whitespace; preserve original game_id, display name, raw Unicode bytes and SourceRef. Alias must be explicitly supplied and checked against verified cached source bytes; no invented synonyms.
- Repository `search_snapshot` selects active once (or explicit ready/partial), `iter_search_rows` reads one snapshot in batches of 128; regular full `entities()` is not in query path. An ephemeral private in-memory projection is built per snapshot and reused, with a 64 MiB projection-input budget and safe rebuild failure. Schema v1 and existing snapshots are unchanged.
- FTS5 availability checked during projection creation; always retain literal parameter-bound non-FTS path for two-character Korean, LIKE wildcards and exact queries. FTS query is a quoted literal and errors fall back to lexical path.
- Distinguish definition SourceRef from selected name/alias/description SourceRef; verify referenced cache bytes and maintain snapshot pinning. Duplicated IDs return distinct entity keys with ambiguous diagnostics. Unresolved/partial translation and absent data are not turned into fabricated facts.
- Input length 512, result limit 1–100, snapshot ID/kind/language validation and SQL parameter binding. Escaped LIKE wildcard chars; no SQLite extension loading, external process, model or network.

## E-020/E-021/E-022
Initial state `not_run`. Synthetic tests in `tests/test_retrieval.py` have been submitted for PR CI execution; do not claim pass until actual results are available.
Local repo execution was not possible through git clone because network DNS access to github.com was unavailable. The GitHub Actions PR run is the authoritative subsequent test record, not an actual main merge.

## Residual scope
No actual Stellaris files, no game rule execution, no formal performance p95 or peak RSS measurement, no automatic SQLite migration or cache-inclusive full restore. Ephemeral index cold-build cost and 64 MiB budget require measured follow-up; user queries do not dynamically modify source or v1 schema.


## Verified synthetic PR candidate before evidence-only commits

- Code/test head: `7d6ccd580ae56ba07327ba2bbea09e2cc3a7d78a`.
- Actual PR test-merge checkout: `8b0eddcaab6d7db716bb10a5334080e968d1ef80`; Ubuntu/Windows Package and Documentation logs all confirmed this SHA, not an actual main merge.
- PR Package CI: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38135547105 — Ubuntu Python 3.11.17 / SQLite 3.45.1 **393 passed**; Windows Python 3.13.15 / SQLite 3.50.4 **390 passed + unchanged POSIX-only 3 skipped**; Ruff and harness pass both.
- PR Documentation harness: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38135547080 — Ubuntu/Windows success.
- Code head push Package CI: https://github.com/Gandalem/stellaris-suppoter/actions/runs/38135543614 — both OS completed/success.
- Prior baseline: 359 Ubuntu cases. New: 34 synthetic retrieval cases; no existing tests deleted and no new skip. Windows existing skips: surrogateescape inventory, POSIX calibrated lexer tracemalloc and lexer wall-clock thresholds.
- **E-020 = pass** for exact ID/Korean/English/verified alias, ordered ranking, duplicate ID, SourceRef and snapshot/active-switch isolation.
- **E-021 = pass** for two-letter Korean, NFC/NFD, casefold, whitespace, FTS enabled and disabled, English and ID fallback.
- **E-022 = pass** for punctuation and SQL/FTS literals, LIKE escaping, empty/512/513-length queries, invalid limit/kind/language/snapshot, not_found, many aliases/limit and cache pointer corruption.
- TASK-011 remains doing / F-008 remains in_progress until independent review, real merge and main push CI.

## Non-gating synthetic SQL-only performance baseline

- `scripts/bench_retrieval.py` was executed as an optional CI step on both OS for 100 / 1,000 / 10,000 synthetic in-memory projection rows; one initial query and 25 warm queries per workload. Each CI job printed raw timings, runtime, OS/CPU environment and corpus hash.
- Synthetic corpus SHA256: 100 `99a9f8fe241bee1753cc41b487c3b991bfa3424aa711130925aa59a05fbdb96a`; 1,000 `db687bda61d80d3666fc701c2159e3d3e891d2a229c69bbf0985ad11d51f38d9`; 10,000 `fafd58421fd3915f1c05449c2f50f4796c88ec6dd64cafada32f4b1a1c4ffca4`.
- Observed 10,000-row warm p95 milliseconds (Ubuntu / Windows): ID exact 3.595 / 4.149; Korean exact 4.729 / 6.060; short Korean substring 41.997 / 44.500; prefix 42.626 / 43.657; lexical description 24.838 / 25.703.
- These are SQL projection microbenchmarks, NOT full end-to-end SearchService latency, cold projection construction time, actual game corpus, FTS-on/off comparative latency or peak RSS. The official 10,000-row warm p95 acceptance remains TASK-019; it has NOT been certified by these readings.
