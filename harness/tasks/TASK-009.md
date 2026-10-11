# TASK-009 Localisation reader/resolver

Task: TASK-009  
Feature: F-006  
Evaluation IDs: E-015, E-016, E-017  
Base main: `e49ab75153d695b92614b2db3a0e54136f148e37`  
Branch: `task/TASK-009-localisation-reader-resolver`

## Scope

Dedicated source-preserving reader and deterministic bounded resolver for synthetic Stellaris-like localisation:

- UTF-8 strict/BOM, LF/CRLF, language headers, keys, optional marker, quoted value and lexical escapes, comments/blank lines/EOF.
- Ordered duplicate entries, raw byte SourceRefs, line and column, distinct raw/display values, explicit unknown spans and diagnostics.
- Requested language → English → ID fallback, duplicate ambiguity and no invented precedence.
- Supported static `$KEY$` references only; explicit cycles, missing/ambiguous references, unsupported dynamic forms.
- Resource bounds on file/line/items/diagnostics and resolver depth/visits/scanned bytes/output.
- SourceContext hash/path/snapshot validation and technology-localisation SourceRef separation.

Out of scope: real game installation, DB schema, search/CLI integration, effective mod precedence, actual game scripting semantics.

## Evaluations

E-015 Language fallback: pass, including language/SourceRef of selected references.  
E-016 Localisation cycle: pass, self/multi-key, missing and bounded expansion.  
E-017 Duplicates and dynamic text: pass, retained raw/spans/markup, encoding and resource negative tests.

All evaluation evidence: [TASK-009 localisation reader/resolver](../evidence/TASK-009-localisation-reader-resolver.md).

## CI

PR #17 candidate code/test head `c6fa59143df0f1921fc6d2e7c9fb4557db85ad5a`.  
Test-merge `83a044412bdb59eb1b07069b41e7886295860a5a`.

- Package PR run `38125860266`: Ubuntu 230 passed; Windows 227 passed + 3 existing intentional skips. New localisation 50 tests passed both.
- Ruff and `scripts/check_harness.py`: both OS success.
- Documentation harness PR run `38125860274`: both OS success.

## Status

TASK-009 remains **doing** until reviewed/merged and actual main push CI succeeds.  
F-006 **in_progress**, F-005 **in_progress**, latest_game_version **null**.  
No main merge, original game file use, or review thread changes.
