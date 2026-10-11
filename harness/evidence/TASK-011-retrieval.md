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
