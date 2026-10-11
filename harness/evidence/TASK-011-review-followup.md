# TASK-011 PR #21 independent technical review R1–R4 follow-up

Date: 2026-10-11 (Asia/Seoul); authored synthetic fixtures only.

- Review: https://github.com/Gandalem/stellaris-suppoter/pull/21#pullrequestreview-5483148737
- Starting review code head: `c523cfe100a274132de8c5d3d894cbe8804bd722`
- Unchanged base/main: `458743fb189edcd4aeeda4e51c72204071801c31`
- Implemented only within PR #21; no SQLite v1 schema migration, game reads/writes, new PR or TASK-012.

## R1 / P2 — dynamic localisation protected from verified name/description

**Before:** `retrieval._safe_name` rejected only `$`, `[`, `]`; raw `§Y합금§!` and `£energy£ 합금 설명` were erroneously eligible for name/description projection because reader's `has_unsupported_escape` is not a dynamic-tag detector. Static resolver had already classified these as `LOC_DYNAMIC_UNSUPPORTED` / partial.

**After:** search-only source gate excludes raw `$`, brackets, icon `£`, colour `§`; only `LocalisationResolution.resolution="resolved"` with verified unique stored root and reference provenance may promote an expanded `$KEY$` name. Unsupported escape remains excluded, no dynamic code is executed. When Korean name cannot be verified, an available static English name or game ID is used with original partial status/diagnostics (not a verified Korean exact match). Dynamic description cannot enter lexical search.

**Synthetic regressions:** `test_r1_protected_markup_never_becomes_verified_name` (five parameter sets: §, £, bracket, escaped dollar, valid $KEY$ expansion) and `test_r1_unsupported_icon_description_not_indexed`. Expected/observed on passing CI: four protected strings do not return verified exact name; valid expansion returns `name_exact` with static ref; icon description is not searchable.

## R2 / P2 — alias SourceRef↔entity binding

**Before:** `VerifiedAlias` merely verified entity exists in projection, SourceRef snapshot matches and alias literal occurs in that arbitrary source span. `demo_a` could claim `demo_b`'s definition as its alias evidence.

**After:** explicit alias source must be either **exact same definition SourceRef** or the exact persisted entry/value span of a **unique language/key localisation row whose key equals the entity's game ID**. Cross-file localisation is allowed under this typed relationship; unrelated key/definition/file/snapshot and byte-span forgeries are rejected as `SOURCE_CHANGED`. If game ID duplicates exist, shared localisation evidence cannot silently resolve one entity. This is an explicit curated lexical alias, not a proof of an in-game synonym/engine ordering and no alias is generated automatically.

**Synthetic regressions:** `test_r2_other_entity_definition_cannot_prove_alias`, `test_r2_other_localisation_key_cannot_prove_alias`, `test_r2_cross_snapshot_alias_ref_is_rejected`, `test_r2_forged_byte_span_not_valid_alias_evidence`. Expected/observed in passing CI: each counterfeit alias returns error diagnostic `SOURCE_CHANGED`; prior `test_e020_explicit_verified_alias_and_source_ref` still succeeds.

## R3 / P2 — entire resolved static chain survives search

**Before:** `LocalisationResolution.reference_source_refs` / `reference_selections` were persisted in `localisation_json` but `SearchHit` held only the root `localisation_source_ref`; dependent entries such as `demo_suffix` could not be cited.

**After:** per-snapshot ephemeral projection retains root + ordered `reference_selections` and selection language for every resolved static name. Each root and dependency is validated against a unique stored (key,language,entry SourceRef) and checked against verified cache bytes. `SearchHit` appends typed `localisation_reference_source_refs`, `localisation_reference_selections`, `match_reference_source_refs`, `match_reference_selections`, preserving prior fields and their meaning. Not-found/duplicate/cyclic/dynamic/partial expansions are never promoted to resolved static names; selection from English through Korean's static reference keeps actual English language evidence.

**Synthetic regressions:** `test_r3_multilevel_static_reference_provenance` (2-level Korean static chain, full SourceRefs and exact match), `test_r3_corrupted_nested_reference_cache_is_error` (cache SHA tampering -> `SOURCE_CHANGED`), `test_r3_missing_duplicate_cycle_refs_are_not_fabricated` (3 parameters, no verified name, English fallback, partial), `test_r3_selected_reference_language_preserved_across_files` (Korean root + English referenced entry with language=english). The old exact/short-Korean/metacharacter/snapshot tests remain intact.

## R4 / P3 — FTS5 branch

The old query always included exhaustive description `LIKE '%term%'`, then added another FTS5 `MATCH` joined to the identical LIKE predicate. It could add no candidates beyond the base LIKE scan and could not demonstrate a speedup. **The redundant FTS SQL query/insertion branch is removed** while retaining FTS5 runtime capability probing and safe, parameterized LIKE fallback for Korean two-character and metacharacter queries. Document no measured FTS acceleration; future formal query-plan, FTS-on/off end-to-end and memory profiling remain separate. The existing 10k SQL-only benchmark is non-gating and its schema is updated for the additional ephemeral `ref_selections` field.

## Validation and scope

The old E-020/E-021/E-022 synthetic pass evidence is preserved at `harness/evidence/TASK-011-retrieval.md`. **16 additional parametrized synthetic cases** (baseline Ubuntu 393 collected -> expected 409) are introduced with no existing test deletion/skip; checks must verify both OS before final review. Baseline Windows had 3 pre-existing POSIX-only skips.

Initial follow-up code/test candidate `4b51644873826cbf9f1465f1416b4ca0b492751b`; Ubuntu Package push run `38136848796`: 409 passed, Ruff and harness success; Windows and subsequent final PR CI will be referenced in PR #21 once verified. No head/test-merge or CI success will be inferred for subsequent evidence-only commits.

**Unverified:** real Stellaris files/versions, installed-game semantics or real alias rules, FTS performance benefit, peak RSS/cold build, full-service 10k p95, DB/cache-inclusive recovery, user mod priority and unsupported dynamic expressions. TASK-011 remains doing/F-008 in_progress; F-005 in_progress, TASK-010 done/F-007 verified, latest_game_version null, product_implemented false. PR not merged; independent technical re-review required.
