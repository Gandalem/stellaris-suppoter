# TASK-014 official closure readiness — PROPOSAL ONLY (not a closure PR)

**This is a non-executing checklist.** Nothing in this file changes task, feature, evaluation or release status. No user-approved auto-merge or direct main edit.

## Sequential hard gates

1. C2 real-main integration: [PR #33](https://github.com/Gandalem/stellaris-suppoter/pull/33) actually merged as `b3533f8c97e106adbf7d94119aac2d612f61040f`; real main Ubuntu/Windows Package #38256524518 and Documentation #38256524387 success, all four checkout SHA verified. **Satisfied**.
2. C3 all-13-domain matrix: dedicated branch `task/TASK-014-domain-adapters-wave6-e027`, `tests/test_domain_e027_matrix.py`, full A–F matrix and original regressions. New candidate main-equivalent CI, exact head-push and PR test-merge not treated as owner merge. **Independent technical review and owner merge pending** at initial plan creation.
3. Post-C3 owner-merged **new actual main commit**: verify precise merge SHA and four real Ubuntu/Windows Package/Documentation checkout logs, complete successful pytest + Ruff + harness + Documentation. Any CI failure blocks closure proposal.
4. Resolve any independent technical-review **blocking** defects via same PR before owner merge, without force push, bypassing CI or suppressing tests. Preserve reviewer `COMMENTED` vs true third-party `APPROVED` distinction.
5. Then create a **new, documentation/ledger-only TASK-014 closure PR**, no direct main writes:
   - `harness/tasks.json`: TASK-014 `doing -> done`, append C3 and actual new-main integration evidence, preserve TASK-013 and TASK-015–022 records.
   - `harness/features.json`: F-005 `in_progress -> verified` **only for authored synthetic scoped adapter coverage**, preserve evidence and F IDs.
   - `harness/evals.jsonl`: E-027 `not_run -> pass` with exact verified 13-domain A–F evaluation, actual main CI and raw-backing evidence. No other E/F-ID reassignments.
   - `harness/state.json`: active_task `null`, next_task `TASK-015`, retain `latest_game_version=null`, `product_implemented=false`. Mark only after all gates.
   - new session and `harness/evidence/TASK-014-main-integration-closure.md` linking final real main SHA, actual workflows and job checkout SHAs.
6. Closure PR requires its own Ubuntu/Windows Package and Documentation CI, harness integrity, independent ledger review, **owner merge and new main integration CI** before TASK-015 implementation begins.

## Stop/go

- No C3 owner merge or new main CI => **E-027 remains not_run, TASK-014 doing, F-005 in_progress**.
- Successful synthetic coverage => **no verified installed game version, DLC, mods or engine interpretation**. Do not claim a production implementation, real compatibility or TASK-019 performance acceptance.
- P3 parse reuse is tracked separately in [Issue #34](https://github.com/Gandalem/stellaris-suppoter/issues/34), and is **not a C3 merge block** absent a reproduced security/resource problem.
