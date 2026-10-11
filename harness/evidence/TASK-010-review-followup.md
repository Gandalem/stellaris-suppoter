# TASK-010 PR #19 R1–R5 independent-review follow-up

Date: 2026-10-11 (Asia/Seoul). **Synthetic corpus and temporary directories only.**
PR: https://github.com/Gandalem/stellaris-suppoter/pull/19
Review that requested changes: https://github.com/Gandalem/stellaris-suppoter/pull/19#pullrequestreview-5482958006

- Original reviewed head: `d4fddd5425ce71a5a689e5740550d6a2c7b0e25e`.
- Unchanged base/main: `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c` (PR #18 actual main merge).
- **Verified code/test/doc candidate head:** `e3c598b92de53a54baa2bb0bf708a60f457dba9f`.
- **Exact PR test-merge checkout:** `9d4fcdaf77226687dd1f033fb5f4b5eb52e339cb` (**not** an actual main merge).
- The final evidence-only head is different by construction; verify that head's PR test-merge and CI in the [PR #19 description](https://github.com/Gandalem/stellaris-suppoter/pull/19). This file deliberately does not claim to know its own Git commit SHA.

## R1/P2 — fix physical live-source target substitution

Before: `stage()` recorded only `source_files.live_required`. `activate(sources=...)` accepted a freshly provided `SourceFileInput` with the same logical source key/hash/size but a different `live_path`. Identical original bytes in `origin.txt` and `copy.txt` allowed activation after the staged original changed, by validating the copy instead.

Fix: `cache.live_source_relative_path()` validates absolute physical path under the explicitly configured game_root; checks ancestors and all path components for links/reparse points; `verify_live_source()` returns the actual root-relative path after SHA-256 recheck. SQLite `source_files` now stores **private** `live_relative_path` and `live_root_sha256` (hash of canonical root spelling), with a CHECK tying the optional fields to live_required. Stage validates and persists this binding; activation requires matching physical root and root-relative path **before** re-reading the original file, and rejects a supplied alternate path even if bytes match. The public logical key `(source_kind,source_id,relative_path)` remains separate from physical root-relative path, so base/mod logical namespaces are not assumed identical to the game-root layout. Personal absolute paths and root fingerprint do not enter snapshot identity or public evidence.

New synthetic regression cases: `test_r1_stage_target_cannot_be_swapped_for_same_hash_copy` parameterized base/mod, `test_r1_stage_binding_survives_reopen_and_never_leaks_absolute_root`, `test_r1_same_relative_target_under_different_game_root_is_rejected`, `test_r1_symlink_target_cannot_be_bound_or_revalidated` parameterized stage/activation, `test_r1_duplicate_logical_source_ids_are_not_rescued_by_different_live_paths`. Expected and observed: changed staged file or any path/root substitution fails closed; previous active retained; normal binding survives reopen; duplicates do not silently merge.

Residual: this is path identity and content integrity, not a cross-platform inode pin or a proof against a hostile process racing replacement at the same pathname. Windows symlink privilege restrictions use a synthetic reparse-point simulation fallback instead of skipping a test. Only paths within the configured game_root are supported; unknown external mod roots are not guessed.

## R2/P2 — raw Unicode versus canonical identity

Before: `canonical_json()` required every string to be NFC. Its use in `_as_json()` prevented lossless persistence of valid localisation reader values with decomposed Korean Jamo or Latin `e + U+0301`; the failure occurred in storing JSON after a successful reader.

Fix: identity/metadata `canonical_json()` continues to require NFC without transforming inputs. New `storage_json()` uses the same ordered UTF-8 JSON encoder **without any codepoint normalisation**, with 1MiB per-record output bound, nesting bound 280 and item budget 100,000. `repository._as_json()` uses this lossless storage path; entity-key hashing that contains raw game IDs also uses bounded lossless JSON. The source SHA-256 and SourceRef byte positions remain derived from original bytes, not from display-normalised text.

New regression: `test_r2_lossless_localisation_codepoints_bom_crlf_and_source_spans` (NFC Korean, decomposed Hangul Jamo, Latin combining), `test_r2_raw_and_display_are_distinct_without_normalising_combining_marks`, `test_r2_technology_raw_decomposed_unicode_roundtrip`, `test_r2_identity_metadata_remains_nfc_strict`. Expected and observed: codepoint sequences and original byte spans round-trip unmodified, including BOM/CRLF and raw-vs-display lexical escape differences; non-NFC **identity metadata** remains rejected. Technology raw values are represented by their existing SourceRef/cache, not an invented eager raw_value field.

## R3/P2 — policy identity resource bounds

Before: `analysis_context` and `dlc_state` could cause unbounded `policy_json` and snapshot ID JSON materialisation although ordinary candidate JSON used a per-record 1MiB bound.

Fix: `MAX_POLICY_JSON_BYTES=1,048,576` UTF-8 bytes for complete policy JSON; `MAX_POLICY_JSON_DEPTH=32` and `MAX_POLICY_JSON_ITEMS=10,000` visits (including keys). The snapshot-ID wrapper permits **at most an additional 128-byte content_hash envelope**, preserving the prior canonical algorithm. Early minimum-codepoint-count rejection precedes expensive Unicode normalization/encoder work; the actual JSON encoder iterates chunks with a strict byte budget. The repository checks bounded policy size before DB insertion and persists the **exact immutable `identity.policy_json` that produced the fingerprint**, instead of rereading a caller-owned mutable mapping. No cutoff or truncation-success is used; excess causes `LIMIT_EXCEEDED` with previous active untouched.

New regression: `test_r3_policy_json_exact_byte_boundary_and_deterministic_sha`, `test_r3_over_budget_policy_rejected_before_db_insert_and_active_retained`, `test_r3_policy_metadata_resource_limits` (oversized string, nested metadata, item-count), `test_r3_mutable_policy_mapping_cannot_change_row_after_identity_calculation`. Expected and observed: exactly 1MiB accepted; +1 byte rejected; overly deep/item-heavy input rejected; canonical ID is stable for unchanged input; mutated policy cannot change the stored identity or active pointer.

Residual: JSON output is strictly bounded, but the API takes an already constructed Python Mapping and the encoder can materialise bounded chunks; no peak-RSS constant-space guarantee for arbitrary caller objects is claimed. This is not a 512MiB aggregate in-memory benchmark.

## R4/P2 — source-file versus cache pointer consistency

Before: `source_bytes()` matched the SourceRef SHA against `source_files.file_sha256` and read whatever valid cache blob `cache_sha256` referenced. A DB pointer redirected from `AAAA` to an unrelated valid `BBBB` could therefore return wrong bytes.

Fix: SQLite v1 `source_files.cache_sha256` now has `CHECK(cache_sha256=file_sha256)`. `source_bytes()` explicitly enforces SourceRef SHA = file SHA = cache SHA **before** `BlobCache.read`, which also hashes the actual bytes. Routine read-only schema checking remains lightweight, allowing the query boundary to produce an explicit `SOURCE_CHANGED` for this logical inconsistency. Read errors never rewrite `active_snapshot`.

New regression: `test_r4_schema_constraint_and_source_bytes_reject_cache_pointer_swap` stages `AAAA`/`BBBB` in the same snapshot: ordinary SQL UPDATE is blocked by CHECK; corruption is then deliberately injected using SQLite's `PRAGMA ignore_check_constraints=ON`; fetching the original A SourceRef fails with `SOURCE_CHANGED` and leaves active unchanged. `test_r4_historical_valid_snapshot_remains_queryable_after_other_corruption` confirms an old valid snapshot's bytes remain retrievable while another snapshot's cache pointer is corrupted. No silent repair or aliasing.

## R5/P3 — documentation and measured cost (non-blocking)

- Fixed the blank line separating `ADR-012` from `ADR-013` in `docs/DECISIONS.md` without altering either decision; `test_r5_adr_012_and_013_share_one_markdown_table` enforces row continuity. The existing normative heading inventory test remains unchanged; a provisional new heading triggered that test and was corrected without changing thresholds or skipping it.
- Previously `check_schema()` ran `PRAGMA quick_check` on every connection, including normal read-only queries. Now full integrity checks remain at initial DB preflight, write connections and backup verification; repeated read-only lookups still check schema version, required tables/columns, metadata and FK but omit full-page quick_check. Untrusted bytes and per-row cache pointer integrity have separate validation.
- `scripts/bench_storage_schema.py` reports observational **7-sample medians** after warmup for a temporary synthetic SQLite DB with 0, 1,000 and 5,000 diagnostic rows. It is non-gating and neither a real-game corpus nor an indexed search warm-p95 benchmark.

| Synthetic diagnostic rows | DB bytes | Ubuntu full/check-light (ms) | Windows full/check-light (ms) |
|---:|---:|---:|---:|
| 0 | 94,208 | 0.2677 / 0.1642 | 0.3147 / 0.1822 |
| 1,000 | 303,104 | 1.0059 / 0.1538 | 1.0797 / 0.1634 |
| 5,000 | 1,134,592 | 4.0632 / 0.1520 | 4.1400 / 0.1625 |

Observed repository empty-query medians with 5,000 synthetic rows: Ubuntu **0.5877ms**, Windows **1.1441ms**. These are noisy hosted-runner microbenchmarks, not a guaranteed latency or TASK-011 search p95 result.

## Exact verified cross-platform CI (code/test/doc candidate)

- [Package and tooling PR run 38133251652](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38133251652) — **success**, checked out `9d4fcdaf77226687dd1f033fb5f4b5eb52e339cb` on both OS.
  - Ubuntu Python **3.11.17**, SQLite **3.45.1**: `collected 359`, **359 passed**, Ruff **all checks passed**, harness valid.
  - Windows Python **3.13.15**, SQLite **3.50.4**: `collected 359`, **356 passed + existing 3 intentional POSIX-only skips**, Ruff **all checks passed**, harness valid. New review cases had **zero skips**.
  - All required `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py` ran on both clean GitHub workers; the optional synthetic benchmark step also completed and emitted the timings above.
- [Documentation harness PR run 38133251707](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38133251707) — **success Ubuntu/Windows** at the same head.
- [Head push Package run 38133247585](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38133247585) — **success** at exact code/test head.
- Baseline package CI `38131642474` (Ubuntu 337, Windows 334+3 intentional skips) and prior original evidence remain preserved. Relative to the original 337 cases, **22 newly collected R1–R5 cases** were added; no existing test deleted, skipped or loosened.
- No local independent full-suite execution is claimed: this environment could not resolve github.com for git clone. The above are observed GitHub Actions clean-setup results.

## Remaining gates and risk honesty

- Existing historical [TASK-010 E-018/E-019 evidence](TASK-010-sqlite-snapshots.md) stays intact. E-018/E-019 remain `pass` with this additional verified negative-case evidence. No real Stellaris installation, DLC, mods, savegame or private filesystem data was read or published.
- The new v1 SQLite columns/CHECK are mandatory for freshly built DBs. Reopening an earlier unmerged v1 layout **refuses** incomplete schema; no migration is silently performed. Recovery still needs source blobs alongside SQLite backup.
- Root binding checks and symlink/reparse defense have residual OS-level race and permission limitations. This is not a formal adversarial filesystem proof.
- TASK-010 **doing**, F-007 **in_progress**, TASK-009 **done**, F-006 **verified**, F-005 **in_progress**, E-020/021/022 **not_run**, latest_game_version **null**, product_implemented **false**. Not merged. Independent technical re-review and actual main integration CI still required; R1–R4 green CI alone is **not** merge approval. Existing review threads are not resolved and TASK-011 is not started.
