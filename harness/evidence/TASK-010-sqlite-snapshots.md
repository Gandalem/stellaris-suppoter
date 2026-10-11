# TASK-010 SQLite deterministic snapshots — E-018 and E-019 evidence

Date: 2026-10-11 (Asia/Seoul)  
Implementation PR: https://github.com/Gandalem/stellaris-suppoter/pull/19  
Branch: `task/TASK-010-sqlite-snapshots`  
Starting actual main: `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c` (PR #18 actual merge).  
Source game/version: unknown; `latest_game_version=null`.

## 1. Dependency integration gate

PR #18 merged on main as `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c`, and main push Package and tooling `38130135720` and Documentation harness `38130135692` were both completed successfully on Ubuntu and Windows. TASK-004/005/008/009 all `done`; F-006 `verified` within authored synthetic corpus, F-005 `in_progress`. TASK-010 was set `doing` on the new dedicated branch. No later task implementation is included.

## 2. Implemented typed repository contracts

- `src/stellaris_supporter/storage/identity.py`: bounded `SourceFileInput`/`SourceDescriptor`/`SnapshotPolicy`/`SnapshotIdentity`, strict SHA-256 manifest, no hidden time/root/random inputs; path separator canonicalisation to `/` with Unicode NFC requirement, case preserved and cross-Windows casefold collision rejected.
- Canonical JSON: UTF-8, key sorted, compact separators, `ensure_ascii=False`, finite restricted types, explicit depth/optional byte limit. Sorted content fields `(source_kind,source_id,relative_path,file_sha256)` form SHA-256 `content_hash`; content + schema/parser/adapter/policy/context/version/DLC/mod identity fields form SHA-256 snapshot ID. Clock, created_at, absolute roots, temp paths and discovery order excluded. Numeric marker and game version are distinct.
- `src/stellaris_supporter/storage/schema.py`: eight relational SQLite v1 tables `snapshots`, `source_files`, `entities`, `localisation_entries`, `relations`, `search_documents`, `diagnostics`, `settings`. Composite snapshot-scoped PK/FK + indexes; duplicate game_id/translation definitions not overwritten. Separate `candidate_json` and `localisation_json` retain original technology fields, occurrence, SourceRefs and translation resolution/provenance without substituting translation origin for script origin. `null`, `false`, `0`, `[]` are distinct. Relations preserve unresolved prerequisite IDs; full graph resolution and FTS ranking are not implemented.
- `src/stellaris_supporter/storage/cache.py`: private data_dir content-addressed SHA-256 bytes cache. Temp file → write/fsync → hash verify → same-folder atomic rename (POSIX parent directory fsync) → read/hash verify; reused identical bytes never erase per-source SourceRef identity. Reject symlinks/reparse-point inputs, unsafe paths, changed/missing/corrupt blobs. Game root stays read-only.
- `src/stellaris_supporter/storage/repository.py`: stage `building→ready|partial|failed` (active is a separate settings pointer). Exclusive bounded writer transaction controls staging; cache source checks and source manifest/SourceRef validation precede ready. `activate` uses `BEGIN IMMEDIATE` to check ready/partial policy, cache SHA/size, current live-source manifest, FK and cancellation before updating pointer atomically. Old active stays accessible while staging, and all failure paths preserve its pointer. Explicit `recover_interrupted` marks abandoned building records failed only when the operator is sure no other writer is active; no silent recovery-as-ready.
- `stage_from_results` forwards technology adaptation/localisation reader diagnostics and `complete` state so an invalid encoding/limit producing an empty AST is not silently indexed as normal empty. Original `SourceContext` bytes/SHA/source IDs/snapshot are rechecked. Nested reference spans are validated against manifest and snapshot.
- Schema opens existing DB in read-only preflight, refuses unknown past/future schema, checks PRAGMA user_version/settings schema_version, foreign_keys and quick_check, and does not automatically migrate or reset user data. Consistent DB-only backup uses SQLite backup API; cache blobs must accompany external recovery.
- Runtime settings: SQLite `foreign_keys=ON`, `journal_mode=WAL`, `synchronous=FULL`, `busy_timeout=250` milliseconds, bounded writer lock failure. File max 16 MiB, total bytes 512 MiB, files 50,000, indexed entity+loc+relation records 100,000, diagnostics 10,000, per-record JSON 1 MiB; no arbitrary huge raw subtree serialization. Source manifest source descriptor operations bounded by count rather than quadratic rescans.

## 3. E-018 — Snapshot identity and schema: pass (authored synthetic data)

Test source: `tests/test_storage_snapshots.py` (parameterized scenarios). Baseline pre-TASK-010 suite had 279 tests; current implementation candidate collected **337**, or **58 additional pytest cases**, no existing tests deleted.

Verified cases:
- canonical JSON bytes/key order, `null/false/0/[]` distinct, changed parser/adapter/schema/policy/context/bytes/path changes identity.
- unchanged/sorted/reversed corpus and different private temp roots produce stable identity. Windows backslash paths normalise to the same canonical identity; case/NFC differences are not silently merged. Duplicate source keys and inventory hash mismatch reject.
- typed technology fields, unresolved prerequisite relations, localisation duplicate definitions, BOM/CRLF/Korean raw byte span, selected/source-provenance separation all survive SQLite round-trip with source cache checks.
- duplicate technology game_id in two files yields two distinct entity_keys and occurrences; explicit old/new snapshot reads retain independent entity/source locations and historical bytes.
- SHA/cross-snapshot forged SourceRefs and localised document/bytes mixing reject; invalid UTF-8 reader diagnostics persist as partial instead of quiet success.
- SQLite tables, PRAGMA version, foreign key integrity, backup and schema version protection validated. Structural manifest descriptor counter verifies scaling with 128 synthetic source files.

## 4. E-019 — Atomic snapshot activation: pass (authored synthetic fault injection)

Verified cases:
- first ready snapshot active, second staged snapshot not automatically active, switching active pointer transactionally while previous snapshot remains retrievable.
- `partial` activation refused by default and allowed only when explicitly requested; even with allow_partial source forgery/hash mismatch is still fatal.
- building stage callback exception, cancellation after building, injected SQLite trigger INSERT failure, synthetic disk-full `OSError` cache failure produce failed/incomplete staging and leave prior active/queryable data.
- failure/cancellation in activation before commit rolls back active settings pointer.
- previous active is readable through a separate connection while writer is staging; concurrent stage writer is rejected with explicit finite `SQLITE_BUSY`. Database locked before activation also leaves the previous active intact and allows retry.
- changed current source file during stage or after stage before activation refuses new snapshot; game-root file is not written by repository.
- deleted/corrupted source cache prevents activation. No partial approval may bypass source security checks. Earlier valid cache and snapshot rows are never silently pruned by repository.
- process-level simulated `KeyboardInterrupt` leaves building state; explicit recovery after reopen marks failed without changing active. Reopening after successful commit preserves active pointer and data.
- unknown new user_version rejects write on reopen; backup API preserves a consistent active pointer and passes SQLite integrity_check; unsafe paths/symlinks and overlapping game/data roots are rejected.
- SQLite runtime PRAGMA actual FK/WAL/FULL/busy_timeout checks executed on both OS.

## 5. Verified code/test candidate CI (before final evidence-only commits)

**Code/test/docs candidate head:** `7a72588dad8b298a4c3b52befef964484baedc10`.  
**PR test-merge checkout (not actual main merge):** `8df521765fd6b81b3c15f4fd492ff22dc8181614`.

- [Package and tooling PR run 38131453597](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38131453597): Ubuntu + Windows **success**.
  - Ubuntu / Python **3.11.17**, SQLite **3.45.1**: **337 passed**, Ruff and harness success, `harness_valid=true`.
  - Windows / Python **3.13.15**, SQLite **3.50.4**: **334 passed + the pre-existing 3 POSIX-specific skips**, Ruff/harness success.
  - Both Package job logs checked out exact PR test-merge `8df521765fd6b81b3c15f4fd492ff22dc8181614`.
  - Commands `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py` executed in actual PR CI. The three existing Windows skips concern inventory surrogateescape and two POSIX-only lexer memory/wallclock thresholds; **new SQLite tests had no skips**.
- [Documentation harness PR run 38131453587](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38131453587): Ubuntu and Windows **success**.
- Intermediate candidate failures are **not erased**: early Ubuntu fixture mismatch tests initially failed; then 328/325 tests passed but Ruff identified six import/UTC style issues, corrected. Later incremental CI runs were cancelled by concurrency when new commits arrived. Only successful results above justify evaluation passes.

## 6. Remaining limitations and honest claims

- Tests use **only authored synthetic bytes** inside temporary private data directories. Actual Stellaris installation, DLC/mod, game parser dynamic meaning, game version and user device filesystem behavior remain unverified. No actual game original files were modified.
- E-018/E-019 exercise fail injection and cross-platform CI, not a measured peak RSS benchmark nor empirical proof of perfect crash/power-loss durability on every filesystem. File/DB are different atomic domains; the repository explicitly verifies cache existence before activation.
- Windows ACL/reparse-point and directory race risk cannot be completely removed with high-level Python path APIs; there is residual TOCTOU between live recheck and transaction commit. Tests narrow that risk and fail closed in synthetic checks, but this is not full adversarial OS-level penetration assurance.
- Automatic DB migration from old/new schema is intentionally **unsupported**; safety is refusal and consistent DB backup, not claimed migration success. Cache-aware full restore automation remains future operations work.
- Strict v1 schema and optional source-bound outputs are for TASK-010; TASK-011 FTS/ranking/search, TASK-012 citations, TASK-013 CLI index/search and advanced domain adapters remain unimplemented.
- No separately run local full-suite test or private game-data test is claimed; evidence from actual GitHub Actions Ubuntu/Windows clean setup logs. PR review and actual main push CI are **not yet done**, so TASK-010 remains `doing`, F-007 `in_progress`, F-005 `in_progress`, F-006 `verified`, E-018/E-019 proposed `pass` with this evidence, `latest_game_version=null`, `product_implemented=false`.
- The final evidence-and-ledger-only commit changes the PR head and requires its own PR package/documentation CI recheck. Record those runs and the **exact final test-merge SHA in the PR body** to avoid self-referential hashes in this evidence file.
