# TASK-013 authored synthetic CLI vertical integration — candidate evidence

- Initial actual main merge: `422f6aa06849b2c210905d75bfe47a32e62f0bf4` after PR #24 owner merge.
- Prerequisite real main push CI: Package `38144498887` Ubuntu 448 passed, Windows 445 passed + original 3 skipped; Ruff/harness both OS succeeded; Documentation `38144498941` both succeeded.
- Branch `task/TASK-013-cli-vertical-slice`. E-026 **not_run** until actual new CI succeeds. Existing TASK-012/R1-R6 evidence preserved.
- New synthetic corpus created only under pytest temporary directories. No actual game files, saves or proprietary translations included.
- Planned command path: `init` exclusive TOML → `doctor` existing service → scoped inventory SHA/live capture → parse/adapt/localisation → `SnapshotRepository.stage_from_results` → exact manifest `activate` → `SearchService.search` → `AnswerService.answer(exact_game_id=True)` → bounded snapshot listing.
- Capture and activation preserve physical path, origin SHA and previous active on exception. Source read uses O_NOFOLLOW where present; OS hostile same-path TOCTOU not completely eliminated.
- No source code task done, F-011 verified, or E-026 pass claim here. Final pytest/Ruff/harness and Package/Docs CI IDs, exact head/test-merge, pass/fail cases and residual risks must be appended only after execution.
