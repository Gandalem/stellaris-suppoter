# TASK-014 Phase A — authored synthetic trait/government/civic/origin adapters

Date: 2026-10-12 (Asia/Seoul). Base **actual main**: `762636db1ffef1ef66d032b5e55d485f26ab4a11`, PR #28 merged. Its actual `main` push Package run `38195940307` and Documentation run `38195940309` both succeeded on Ubuntu 3.11 and Windows 3.13. No open PR existed at start. Work branch: `task/TASK-014-domain-adapters-wave2`. **This is partial TASK-014; E-027 remains not_run.**

## Implemented authored grammars (not real game compatibility)

| Kind | Opt-in candidate path | Definition source and ID | Synthetic display-name localisation |
|---|---|---|---|
| trait | `common/traits/*.txt` | top-level literal `trait_id = { ... }` | `game_id` |
| government | `common/governments/*.txt` | direct child of `governments = { government_id = { ... } }`; wrapper is not an ID | unique literal `name` field |
| civic | `common/governments/civics/*.txt` | `civic = { key = civic_id ... }`; wrapper is not an ID | unique literal `name` field |
| origin | `common/governments/origins/*.txt` | `origin = { id = origin_id ... }`; wrapper is not an ID | unique literal `name` field |

Every path, wrapper, ID rule and naming rule above is an **authored synthetic fixture convention**, not a verified Stellaris version or directory. The baseline four kinds (`component_template`, `building`, `district`, `pop_job`) retain their DomainCandidate/Field/Diagnostic constructors and serialization semantics. No TechnologyCandidate disguise, SQLite migration, repository integration, CLI support, effective game value or engine calculation.

The `DomainSpec` registry added only `nested_identifier`, `literal_id_field`, and explicit `name_field` localisation policy. Candidate provenance for nested government definition and its ID/ordered fields uses the **inner pair SourceRef**, not the wrapper SourceRef. ID selectors refuse dynamic/duplicate/missing ID values. Missing, duplicate or dynamic `name` keys are `DOMAIN_UNRESOLVED_LOCALISATION_KEY` and `partial`, not a guessed ID-to-name mapping.

## Raw/provenance and R1/R2 safety regression

- Reuse the existing public `adapt_domain(parsed, source, context, kind)` R2 SHA/path/byte-span/token/line-column checks and one bounded canonical ParseResult comparison; all four kinds use the same service entrypoint, including nested government.
- Reuse existing `verify_domain_candidate` R1 checks on `items`, all `fields[].value`, all `conditions[].value` and nested `RawNodeRef.children`, plus candidate rebuild and exact source context. Forged equal-length backing (`100` → `999`), nested condition, field metadata and SourceRef/path/snapshot borrowing are negative tests. Existing `tests/test_domain_review_followup.py` is unchanged.
- Preserve duplicate fields and occurrences, duplicate definition ambiguity, distinct file SourceRefs and `find_domain_collisions` same-kind/snapshot isolation. No mod/file-order precedence. Unknown/unsupported operators, unclosed blocks and variable IDs remain partial/unhandled with diagnostics.
- Same bounded parser (16MiB, 100k tokens, depth 128, 100k AST nodes, 1k parser diagnostics), strict UTF-8, BOM/CRLF/Korean spans, bounded raw JSON output; canonical hard stops are blocked with no candidates. No write to game files or network access.

## Localisation authored synthetic tests

Existing `LocalisationCatalog` + `resolve_domain_name` + `resolve_localisation` cover KO/EN, KO→EN fallback, missing ID fallback, duplicate-key ambiguous, $KEY$ multistep references, cycle, `[Root.GetName]`/icon dynamic partial, scan budget, invalid localisation SHA and cross-snapshot rejection. Root translation SourceRef and dependent reference SourceRefs are separately asserted. Source files are authored fixtures in tests, not game data.

## Test first → implementation

- **Red synthetic tests-only head:** `dc35af3cb92f08fe3d2685ec8a7a690217cae60e`. [Ubuntu Package run #38196372857](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38196372857): **44 wave-2 cases failed** because four domain kinds were not yet in `DOMAIN_REGISTRY`; existing **536 passed**. This is a real CI red result, not hypothetical. Do not interpret initial expected failures as shipping regression.
- **First green code + 44 tests head:** `3c902cd4a8b28b38d7a218072ff979fd699d80e1`; Ubuntu job on [head push run #38196486796](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38196486796) reported **580 passed**, Ruff and harness passed. Subsequent commits can cancel older whole workflow runs, so this is not a claim of full two-OS success of that superseded head.
- Added further authored tests for government inner child order/unsupported nodes, missing/dynamic/duplicate name key, cross-kind ID isolation, and file SHA/path attacks. The final test counts must be taken from exact final CI, not inferred by README/docs.

## Non-gating call-count and timing observations

`scripts/bench_domain_wave2.py` constructs 32 authored synthetic trait candidates from one in-memory file, repeats three times, reports corpus SHA, platform/Python, adaptation canonical parse calls, full per-candidate verification parse calls, and wall-clock samples. It is invoked on Ubuntu/Windows from Package workflow with `continue-on-error: true`; this is an observational microbenchmark to show the known repeated per-candidate reparse cost, not TASK-019 E-035/10,000-entity p95, measured game compatibility, or a performance guarantee.

## Independent PR and remaining work

PR head, exact test-merge SHA, the final head *push* CI and PR Package/Documentation checkout IDs should be audited from their live GitHub runs and posted as a dated PR review comment. This evidence file is committed **before final SHA/PR CI exists** and must not claim as-yet-unrun checks as successes.

Phase B: tradition and ascension-perk adapters; Phase C: event (namespace/nested ID), scripted triggers/effects and full E-027 source/localisation matrix. TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`, TASK-015 through TASK-022 `todo`, `latest_game_version=null`, `product_implemented=false`. Owner merge and actual main CI are external gates; no automatic merge, release or game data upload.

## Verified implementation PR revision (recorded after live CI, before this evidence append)

**Original verified Phase A implementation head** `ab0dc4766a4d70e17bd6bf9b76a3f63778dfc3b4`; baseline actual `main` `762636db1ffef1ef66d032b5e55d485f26ab4a11`. Open PR: [#29](https://github.com/Gandalem/stellaris-suppoter/pull/29), `merged=false`. Its **temporary PR test-merge** at that revision is `ed5828f349af4aef526cd5e440206ab41ec2ca78` (**not** actual main merge).

- [Exact head push Package run #38196838471](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38196838471): Ubuntu Python 3.11 **597 passed** and Windows Python 3.13 **594 passed + pre-existing 3 POSIX-only skips**; Ruff and harness success both. Head push job logs checked out exactly `ab0dc4766a4d70e17bd6bf9b76a3f63778dfc3b4`.
- [PR Package run #38196863506](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38196863506): Ubuntu **597 passed**, Windows **594 passed + existing 3 skipped**, Ruff `All checks passed!`, `python scripts/check_harness.py` `harness_valid=true` on both OS. Both jobs actually checked out `ed5828f349af4aef526cd5e440206ab41ec2ca78`.
- [PR Documentation run #38196863486](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38196863486): Ubuntu and Windows harness passed; both actual job checkouts are **the same** `ed5828f349af4aef526cd5e440206ab41ec2ca78`.
- New authored synthetic cases: **61 pytest cases** above actual main baseline (536 → 597 Ubuntu, 533 → 594 Windows). No existing test deletion/new skip. Existing R1/R2 regression file remains intact. E-027 remains `not_run` because Phase B/C scopes are not implemented.
- Targeted **non-gating microbenchmark** at PR test-merge, 32 synthetic trait definitions / three repeats / corpus SHA `93b9f81e462537ab4f5d599108b9164a4b149f0fca3df80d76273e75fa9c4136`: Ubuntu 3.11: median adapter **6.791ms**, median verification of all 32 **209.806ms**; Windows 3.13: median adapter **5.845ms**, verification **172.133ms**. Canonical parses per iteration **1** for adapt vs **32** for per-candidate verification on both. Observation only; no hardware-normalised latency guarantee or TASK-019 evaluation.
- **SHA caveat:** adding this evidence section creates a **newer documentation-only PR head and newer test-merge**. Recheck that new head's push and PR CI; publish the final exact SHA/checkouts in the review request comment. Do not attribute the revision-locked CI above to the subsequent SHA without running it.
