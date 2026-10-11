# TASK-013 — CLI vertical slice

Starting main `422f6aa06849b2c210905d75bfe47a32e62f0bf4` after actual PR #24 closure merge and main Package/Docs CI.
Branch `task/TASK-013-cli-vertical-slice`; status `doing`, feature F-011 `in_progress`, evaluation E-026 initially `not_run`.

## Scope and contracts
- `init`: write one private TOML config with explicit game_root, disjoint data_dir, network off, exclusive atomic publication.
- `doctor`: retain TASK-003 runtime/config/FTS behavior and JSON exit contract; no game indexing.
- `index`: scan only technology script and korean/english localisation subtrees; hash and safely recapture exact source bytes and live paths; deterministic snapshot policy; parse/adapter and localize; `stage_from_results`, then `activate(..., sources=...)` with explicit partial consent.
- `search`: Query/SearchService ID, Korean/English, short and tricky literals, snapshot isolation and limit 1..100.
- `show`: exact game ID using AnswerService's optional exact_game_id mode; retain SourceRef and R1-R6 verification.
- `snapshots`: bounded read-only listing with stable order and active marker.
- JSON stdout single schema_version 1 object, stderr for warnings/traceback-free sanitized errors, consistent documented exit 0/2/3/4/5/6/130. No provider calls.

## E-026 acceptance
Use authored synthetic game directory, subprocess `python -m stellaris_supporter` and console script to run init→doctor→index→search→show→snapshots. Assert raw field bytes/lines and Korean/English/ID, source files unchanged, repeat index same ID, active preserved on failure, duplicate ID, partial security refusal, cache damage, bad args, missing snapshot, text/JSON, Windows/LInux path quoting, and limits. Never skip old tests to pass. E-026 now has synthetic `pass` on PR #25 candidate CI (Ubuntu 486 passed, Windows 483 passed + existing 3 skips; Ruff/harness/Documentation both OS), linked in `harness/evidence/TASK-013-cli-vertical-slice.md`. TASK-013 remains `doing` and F-011 remains `in_progress` pending independent technical review and real main integration.

## Exclusions and limitations
No `refs`/`diff`/`ask`/`sync`/`simulate`/`serve`, no extra domain adapters, model, game engine, automatic migrations or unapproved network. Actual Stellaris game content, OS-level hostile path replacement completeness and end-to-end 10k p95/peak RSS are unverified. TASK-013 stays doing/F-011 in_progress through the implementation PR; F-011 also spans TASK-015/016.
