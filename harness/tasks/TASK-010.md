# TASK-010 Schema and deterministic snapshots

Task: TASK-010  
Feature: F-007  
Evaluations: E-018, E-019  
Development branch: `task/TASK-010-sqlite-snapshots`  
Base main: `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c` (PR #18 actual merge)

## Gates confirmed before starting

- [PR #18](https://github.com/Gandalem/stellaris-suppoter/pull/18): `merged=true`, commit `d2be6af6795f7bf2b5e5e2ae1be4672f00d6618c`.
- Actual main push Package CI `38130135720`: Ubuntu/Windows success; main Documentation harness `38130135692` both OS success.
- TASK-004, TASK-005, TASK-008, TASK-009 all `done`.
- TASK-009 stays `done`, F-006 `verified` (synthetic), F-005 `in_progress`.
- TASK-010 set `doing` only on its dedicated development branch.

## Proposed implementation

- `storage/identity.py`: typed source inputs and policy; NFC-required, case-preserving and collision-rejecting POSIX relative paths; sorted content hash and canonical UTF-8 JSON snapshot identity; independent of clock, absolute temp roots, discovery order.
- `storage/schema.py`: eight relational SQLite v1 tables with snapshot-scoped composite FK/PK and indexes, game_id duplicates allowed, strict future/old schema rejection, FK ON.
- `storage/cache.py`: private SHA-256 content-addressed immutable cache; temporary write, fsync, SHA verification, atomic rename, safe directory policy, optional live-source check under declared game root.
- `storage/repository.py`: staging `building→ready|partial|failed` and separate active settings pointer. SQLite WAL/FULL/250ms busy timeout, `BEGIN IMMEDIATE` around staging and activation write transactions. Before activation verify cache hashes, source manifest, current live files and FK; abort without changing prior active if any step fails. Explicit recovery of abandoned building state. Public typed technology/localisation result boundary retains diagnostics.
- Preserve TechnologyCandidate payload, per-field source ref, duplicate game IDs, localisation entry raw/display/byte spans and selected translation provenance without writing game files.
- `search_documents` is a future indexed storage boundary only, not FTS/ranking/query functionality. Full SQLite migration support is not claimed: v1 creation, foreign-version refusal and backup API are implemented.

## Acceptance and verification plan

- E-018: repeat identity across order/root/time; changed bytes/path/schema/parser/adapter/policy/context; Unicode/case collisions; technology+localisation round-trip; duplicate game ID; source blob and origin hashes; FK and snapshot isolation.
- E-019: first/second activation, partial approval, staging exceptions, cancellation, before-commit rollback, concurrent writer lock, source changed, missing/corrupted cache, disk failure simulation, incompatible schema, restart/abandoned building, backup.
- Existing localisation 50, R1-R4 38, normative docs 11, and parser/technology/inventory regression tests must remain unchanged.
- Required commands on both Ubuntu/Python 3.11 and Windows/Python 3.13: `python -m pytest`, `python -m ruff check .`, `python scripts/check_harness.py`; Documentation harness.
- Synthetic fixtures only, no actual Stellaris files or user directories.

## Work and merge state

This development branch proposes TASK-010=`doing`, F-007=`in_progress`. E-018/E-019 remain `not_run` until successful CI and evidence links, when only those evaluation statuses may change to `pass`. Neither TASK-010=done nor F-007=verified is permitted before independent technical review, actual main merge and its main CI. PR #19 is not auto-merged and review threads are untouched.
