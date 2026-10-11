# TASK-009 localisation reader / resolver evaluation evidence

Date: 2026-10-11  
Feature: F-006  
Task: TASK-009  
Evaluations: E-015, E-016, E-017  
Baseline main: `e49ab75153d695b92614b2db3a0e54136f148e37`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/17

## Integration prerequisite

PR #16 merged to main as `e49ab75153d695b92614b2db3a0e54136f148e37` (actual merged=true). Issue #9 closed/completed. Main Package CI `38125171893`: Ubuntu 180 passed, Windows 177 passed + 3 existing skips, Ruff/harness success. Main Documentation harness `38125171970`: Ubuntu/Windows success.

## Implementation and preservation policy

- Dedicated localisation reader, **not** generic YAML: strict UTF-8, BOM, LF/CRLF, language headers, key, optional numeric marker kept as string metadata, escaped quoted strings, comments and EOF without newline.
- Source bytes are shared; entry/header/comment/unknown spans point into original file. Byte spans are 0-based half-open; line/column are 1-based. Duplicate `(language,key)` occurrences are retained in order.
- `SourceContext` requires safe relative path + SHA-256 matching the original bytes. Context snapshot/source kind/source ID are checked when dereferencing; cross-snapshot catalog merging is rejected.
- Reader diagnostics distinguish bad UTF-8, invalid header, unclosed string, unsupported syntax, source hash mismatch and resource limit; unsupported lines remain unknown spans.
- Resolver selection is requested language → English → original ID. Duplicate definitions yield `ambiguous` and do not pick last-wins. Missing translation yields `unresolved` with ID fallback.
- Static `$KEY$` expansion uses bounded traversal and one shared output buffer; missing reference, self/multi-key cycle, ambiguous referenced definition, dynamic scope/format tag and unsupported escapes remain explicit `partial`.
- Per-reference provenance keeps selected key, language and SourceRef in order. Technology source ref stays distinct and unchanged in `TechnologyLocalisedName`.
- The task does not implement SQLite, search, CLI indexing, engine evaluation, actual Stellaris file compatibility or unspecified load precedence.

## Resource limits (before work or output)

- Reader: max 16 MiB file, 1 MiB per physical line, 100000 entries, 100000 total records (including header/comment/unknown), 1000 diagnostics.
- Catalog: at most 100000 entries and 1000 diagnostics.
- Resolver: max recursion depth **64** (cannot configure above this), 4096 visits, 8 MiB scanned source bytes, 1 MiB expanded UTF-8 output, 100 diagnostics.
- Limit exhaustion cannot return `resolved`; diagnostic is `LIMIT_EXCEEDED`, `partial` and `truncated=true` or reader/catalog `complete=false`.
- Decoding lexical escape runs via streaming `StringIO`, not per-escape retained token lists; all entries share immutable source bytes.
- Structural regression asserts visit/scan/output budgets and verifies original spans; this is **not** a claim of a measured peak memory benchmark.

## E-015 — Language fallback: pass (synthetic)

- Korean translation selected when available with `language_used=korean` and Korean SourceRef.
- English selected when Korean or another requested language is absent, `fallback=english` with English SourceRef.
- No Korean or English yields ID fallback, `LOC_MISSING_TRANSLATION`, `unresolved`.
- Different values of same key across languages are isolated, English direct lookup is not labelled fallback.
- Static reference selected via English fallback while main value is Korean carries per-reference language and SourceRef.

## E-016 — Localisation cycle: pass (synthetic)

- One-, two- and three-key cycles explicitly produce `LOC_CYCLE` and `partial` without looping.
- Existing synthetic corpus two-key reference cycle is tested.
- Missing referenced key preserves original dollar token and emits `LOC_MISSING_REFERENCE`.
- Deep chain, explicit max visits, repeated expansion, output bytes, scanned-byte budget and diagnostic budget return bounded `LIMIT_EXCEEDED` with incomplete/partial state.
- `max_depth=200` is explicitly rejected, not allowed to crash Python recursion.

## E-017 — Duplicates and dynamic text: pass (synthetic)

- Existing English duplicate key and cross-file Korean duplicate key remain ordered; resolution is `ambiguous` without implicit precedence.
- Referencing a duplicate target gives `LOC_DUPLICATE_REFERENCE`; no arbitrary selected text.
- `[Root.GetName]`, icon/colour markup, unmatched dollar, unsupported escape are preserved and marked partial; no game script evaluation.
- UTF-8 BOM, CRLF, Korean/multibyte values, escaped quote/backslash, optional marker, trailing comments, EOF without newline have exact SourceRef byte ranges.
- Invalid UTF-8, malformed headers, unclosed quotes, trailing unsupported syntax, missing header, source hash/path mismatch all explicitly fail.
- Large 50,000-pair escape input, 20,000-character Korean value, 5,000 repeated references, 1,000 malformed lines, limited record/entry/catalog size are tested with bounded invariants.
- Technology adapter integration test retains original technology definition SourceRef separately from Korean translation SourceRef; cross-snapshot pairing is rejected.

## Verified PR code+test CI (head c6fa591)

Test source: `tests/test_localisation.py` (50 new tests).  
PR head: `c6fa59143df0f1921fc6d2e7c9fb4557db85ad5a`.  
PR test-merge: `83a044412bdb59eb1b07069b41e7886295860a5a`.

- Package and tooling PR run `38125860266`: Ubuntu Python 3.11, **230 passed**, Ruff success, `scripts/check_harness.py` success.
- Same run Windows Python 3.13, **227 passed + 3 original intentional POSIX-only skips**, Ruff success, `scripts/check_harness.py` success.
- New localisation 50 tests executed without skips on **both** platforms.
- Documentation harness PR run `38125860274`: Ubuntu/Windows success.
- Commands verified in actual PR CI logs: `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py`.
- Harness validator reports `harness_valid=true`; it is ledger consistency, not a substitute for product tests.

## Task and feature state

- E-015/E-016/E-017: pass with this evidence on the TASK-009 PR branch.
- TASK-009 remains `doing` pending independent review, actual merge and main push CI.
- F-006 remains `in_progress` pending integration conditions.
- F-005 remains `in_progress` (other domain adapters outstanding).
- latest_game_version remains `null`; no actual installation/file version was inspected.

Historical evidence is retained unchanged. PR is **not merged**.
