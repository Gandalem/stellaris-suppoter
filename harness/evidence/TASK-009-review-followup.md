# TASK-009 PR #17 review follow-up — R1–R4

Date: 2026-10-11 (Asia/Seoul). PR: https://github.com/Gandalem/stellaris-suppoter/pull/17

- Baseline main: `e49ab75153d695b92614b2db3a0e54136f148e37`.
- Reviewed blocked head: `1a260d2c045410781eeb1fa8dfb76c8b44a226d0`.
- Reviewed previous PR test-merge: `b339d1a03fa546a71e210ab0a21cabc16400294a`.
- Technical review `5482649762`: COMMENTED; four threads left unresolved.
- Historical original evidence `TASK-009-localisation-reader-resolver.md`, including code head `c6fa591` and test-merge `83a0444`, is retained unchanged. This is a new counterexample → fix → revalidation record.

## R1 / P2 — quadratic entry-prefix regexp

**Before:** The previous `_ENTRY_PREFIX` regexp had two overlapping optional whitespace quantifiers around the optional decimal marker. On `b"demo:" + b" " * N` without a terminating quoted value, the regexp could take quadratic CPU time while the line stayed under its allowed 1 MiB budget.

**Fix:** In `src/stellaris_supporter/localisation/reader.py`, `_scan_entry_prefix` consumes key, colon, whitespace, optional marker and opening quote with a monotonically increasing character index. No overlapping regexp quantifier or backtracking remains. Existing byte ranges and Unicode columns still use the original code. L-prefixed valid keys remain valid.

**Structural regressions:** 16/32/64/128KiB malformed no-quote strings instrument indexed character accesses (at most length + 16); 32/64KiB full reader unknown/raw span checks; marker absent, zero and 0019 with 64KiB spaces; BOM/CRLF/LF/multibyte values; exactly 1 MiB versus one byte above the physical-line limit.

**Independent CPU microbenchmark, not whole-reader CI timing:** Standalone Linux 6.18.44 x86_64 / CPython 3.13.5, `time.process_time()`. The exact old regexp was copied into a separate isolated script and compared with a matching local forward scanner. Old: one run per size. New: five runs per size, median below. No network or game data.

| spaces after `demo:` | old regexp CPU s | forward scanner median CPU s | scanner indexed reads | input length |
|---:|---:|---:|---:|---:|
| 8,192 | 0.067510 | 0.000349 | 8,200 | 8,197 |
| 16,384 | 0.278008 | 0.000729 | 16,392 | 16,389 |
| 32,768 | 1.119182 | 0.001549 | 32,776 | 32,773 |
| 65,536 | 4.228101 | 0.002844 | 65,544 | 65,541 |

Doubling 32→64KiB produced `3.8× CPU cost in the old regex and near-linear work in the scanner. These are isolated helper measurements, **not** full package throughput or a Windows CPU benchmark. The CI regression uses indexed-read counts instead of absolute wall-clock thresholds.

## R2 / P2 — dynamic scope and unknown escape containment

**Before:** Fragmenting a value around ` $KEY$ ` before identifying bracket regions let `[Root.$demo_b$]` become `[Root.STATIC]` without dynamic diagnosis. Unsupported `\$demo_b$` could also be treated as an active static reference.

**Fix:** In `src/stellaris_supporter/localisation/resolver.py`, the resolver walks the **raw** quoted value forward. Bracket regions (including nested and escaped delimiters), icon/colour markup and unknown escaped-dollar tokens are classified/protected before static expansion. Protected source text is appended unchanged with `LOC_DYNAMIC_UNSUPPORTED` or `LOC_UNSUPPORTED_ESCAPE` and partial status. Supported `\"` and `\\` lexical escapes are still decoded. Outside a protected region, ` $KEY$ ` retains correct fallback, chosen language, SourceRef, cycle/missing/duplicate handling and visit/output budgets.

**Regressions:** bracketed, nested, repeated, unmatched and adjacent scopes; markup; unsupported escaped-dollar; escaped bracket and markup delimiters; static references before/after dynamic regions; supported backslash/quote escapes beside valid references; dynamic self-reference does not falsely become a cycle. Raw spans remain attached to the selected localisation entry; inner protected references create no false selections.

## R3 / P2 — PARSING Markdown corruption

**Before:** `docs/PARSING.md` duplicated its top-level title and localisation section, and contained the broken fragment `$KEY# 정적 파싱·현지화`.

**Fix:** Removed the repeated body and rewrote one complete localisation section: static `$KEY$` syntax, requested language → English → ID fallback, ambiguous duplicate definitions, dynamic-region protection, resource budgets, origin/source isolation and limits of synthetic-only evidence. `docs/DATA_CONTRACTS.md` is aligned. `test_r3_parsing_markdown_integrity_and_contract` asserts a single title and section, exact reference spelling and essential policy/limit text. Documentation harness alone would not detect the old corruption.

## R4 / P3 — record budget

**Before:** One physical line could append header + comment or entry + comment after only one record-budget check, and thus report complete=True above the cap.

**Fix:** `reserve_record` checks capacity immediately before **each** header, entry, comment or unknown append, including failure paths. Attempted overflow returns `LIMIT_EXCEEDED` and complete=False. Reaching exactly the configured count at EOF, even with trailing blank lines, is successful.

**Regressions:** header+comment with max_records=1, entry+comment with max_records=2, comment-only/unknown boundaries and exact-budget EOF cases. The default 100,000 record policy is unchanged.

## Verified code/test candidate

- Follow-up code, new test and repaired documentation head: `10dd9b721e13819cfa764ab30d6fe26e15ac2499`.
- Test-merge checkout: `889ef8b85321a45ebcb68a39fc48f1f0f24429e3` — CI integration candidate, **not actual main merge**.
- Package and tooling PR run `38126968416`: completed **success**.
  - Ubuntu / Python 3.11.17: **268 passed**.
  - Windows / Python 3.13.15: **265 passed + 3 prior POSIX-only skips** (inventory surrogateescape filename, lexer POSIX peak/wall-clock thresholds).
  - Existing 50 localisation tests + new 38 review scenarios all executed on both systems without new skips.
  - `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py`: success on both.
- Documentation harness PR run `38126968353`: Ubuntu and Windows success.
- Full suite includes existing generator, inventory, lexer, parser and technology-adapter regressions.

## Evaluation state and remaining limitations

E-015 fallback/source/language, E-016 cycle/limits and E-017 duplicates/dynamic/raw spans: historical synthetic passes retained. Each has this new evidence added; all passed on the stated review-follow-up code/test candidate.

TASK-009 remains `doing`, F-006 and F-005 remain `in_progress`, latest_game_version remains `null`. No PR merge, main modification, thread resolution, actual game input or TASK-010 implementation.

The CPU table covers a copied helper and regex in a separate Linux CPython process, not whole-package CPU profiling. Structural read/visit/scan/output budgets are tested, but no standalone peak-memory/RSS benchmark was conducted. Actual Stellaris installation grammar, dynamic engine semantics and unverified mod precedence remain outside this evaluation. An independent review and successful real main CI are required before task closure.
