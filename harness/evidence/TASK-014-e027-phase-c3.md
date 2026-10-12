# TASK-014 Phase C3 — E-027 all-thirteen-domain synthetic acceptance matrix

Date: 2026-10-12 Asia/Seoul. This is an **authored-synthetic coverage assessment**, not support for a real Stellaris build, DLC, mod load order, game calculations, SQLite multi-domain search or final overlay.

## Gate and source scope

- Starting main/PR #33 actual owner merge: **`b3533f8c97e106adbf7d94119aac2d612f61040f`**, checked against all four actual push CI jobs in `harness/evidence/TASK-014-main-integration-after-pr33.md`.
- Branch: `task/TASK-014-domain-adapters-wave6-e027`, strictly separate from the merged C2 branch. Do not modify `main` directly or merge automatically.
- [Tests-only integration matrix](https://github.com/Gandalem/stellaris-suppoter/blob/task/TASK-014-domain-adapters-wave6-e027/tests/test_domain_e027_matrix.py) reuses the existing `DOMAIN_REGISTRY` and original public `DomainCandidate/DomainField/DomainDiagnostic/SourceRef`. **No product code change** was necessary in the first real synthetic execution. Earlier foundation, Wave2, Wave3, Wave4 and Wave5 security/ID/localisation tests were not removed, edited or skipped.
- E-027 harness definition: fixture `all-domains`, feature `F-005`, expected `IDs, fields, names, conditions and sources are correct; support gaps explicit`. **Keep formal E-027 `not_run` on this unmerged PR**; a branch candidate's passing suite does not satisfy owner merge + new true-main CI + independent review conditions for `pass`.

## Thirteen explicitly authored grammar policies

| DomainKind | Synthetic ID/source policy | Localisation policy |
|---|---|---|
| component_template | wrapper `component_template`, static unique `key` | `id_key` |
| building | static top-level pair ID | `id_key` |
| district | static top-level pair ID | `id_key` |
| pop_job | static top-level pair ID | `id_key` |
| trait | static top-level pair ID | `id_key` |
| government | direct child ID inside `governments`, root path constrained | unique static `name` |
| civic | `civic` wrapper with unique static `key` | unique static `name` |
| origin | `origin` wrapper with unique static `id` | unique static `name` |
| tradition | `traditions` group with child unique static `id`, wrapper/group not IDs | unique static `name` |
| ascension_perk | `ascension_perk` wrapper with unique static `id` | unique static `name` |
| event | file-local verified `namespace=authored`, `country_event` explicit `id=authored.1`; parent and nested event not conflated | unique static `title` |
| scripted_trigger | static top-level pair ID; nested dynamics partial, raw effects not executed | **none**, no invented key |
| scripted_effect | static top-level pair ID; nested dynamics partial, raw effects not executed | **none**, no invented key |

All paths and grammar forms remain **investigation candidates authored by tests only**, not game installation observations.

## E-027 evaluation coverage and evidence mapping

The new `tests/test_domain_e027_matrix.py` executes a single **13-kind parameterized matrix** and representative 999/1000/1200 diagnostic stress paths alongside all pre-existing suites:

| Acceptance category | New cross-kind tests and retained prior tests | Expected guarantee |
|---|---|---|
| A — valid definitions | registry exact-set, top-level/wrapper distinction, raw ID and byte span, field/condition/order, repeated cost 100/200/300 and occurrence, nested raw AST, whole-snapshot collection | 13 unique kinds, no calculated engine results, source-bound `synthetic_static` |
| B — errors/unsupported | unsupported operator, unknown AST, unclosed block, fake string/comment, dynamic/unresolvable ID, unhandled unsupported roots; event namespace rules and scripted `@dynamic` value/key remain covered | fail closed as partial/unhandled/blocked, never silent `complete=True` for unsupported syntax |
| C — duplicates/collisions | same-file 2 occurrences with different original cost, same-kind cross-file grouping, snapshot/path/SHA isolation, cross-kind same ID not collision | do not infer last definition wins or mod priority |
| D — localisation | all non-scripted kinds' KO/EN name resolution and fallback, source provenance, missing/duplicate/dynamic/cycle, resolver scan budget, cross-snapshot refusal; scripted `None` policy | never manufacture scripted key from ID/name/title |
| E — provenance attacks | 13 kinds independent field/condition/nested child `RawNodeRef._source` tampering and original unmodified backing, whole source canonical R2 empty/coordinate-tampered AST/token, sha mismatch, changed bytes, verified SourceRefs | original byte spans, SHA, path and snapshot preserved without bypass |
| F — resources/regressions | 13 kinds BOM/CRLF/Hangul, full raw output byte budget, parser max-tokens/nodes/depth/invalid UTF-8, event/gov/root/scripted representative shared 999/1000/1200 warning limits, parser+scripted combined budget; **all earlier lexer/Technology/SQLite/Search/CLI suites** | hard `LIMIT_EXCEEDED` returns zero candidates when exhausted; otherwise documented partial status |

**Existing per-kind edge tests remain necessary**: original detailed event namespace conflicts, conditional parser limits and 1200 clean definitions, previous scripted single-candidate 1200-warning budget, field-loan R1, foreign ParseResult R2 and localisation resolver depth/cycle guards are included in the **whole pytest**, not replaced with artificial common behaviour where policies differ.

## Actual test-first execution before product changes

- Test-only `tests/test_domain_e027_matrix.py` was authored against **unchanged product implementation** based on actual main. Initial head `c030335ff9a581a325f6ce28aa4d65926458fd12`, [Package push #38257520996](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38257520996), **Ubuntu pytest 927 passed**, up from actual main baseline **769** (i.e. **158 new parameterized test instances**). **No genuine new product defect appeared**; we therefore do **not** invent a red-stage failure.
- That first workflow run was **not green**: Ruff flagged one optional UTF-8 encoding argument in the **new test helper** (`UP012`), so the Ubuntu job failed in lint *after pytest succeeded*. Follow-up commit `116f9c15e8d5fd72ecc72104596163675f9aeee3` removes only the redundant helper argument. No product code or assertions changed, no skips or deletions.
- Final exact head, PR test-merge checkout SHA, job IDs, Ubuntu/Windows full pytest + Ruff + harness + Documentation outcome, and final head-push success must be appended in a SHA-pinned **PR review request comment once actual CI completes**. Pre-final evidence never invents values.
- No E-027 formal result, TASK-014 closure or F-005 verification may be claimed from a single branch CI run; actual **owner-merged C3 head**, independent technical review, and *new main* cross-OS Package+Documentation must be verified.

## Nonblocking P3 and branch protection recommendations

- [P3 Issue #34](https://github.com/Gandalem/stellaris-suppoter/issues/34) tracks 32 canonical reparses for 32 independently verified candidates; potential read-only, bounded, **SHA/path/source/snapshot-bound context** must preserve R1 direct independent backing and R2 whole-byte ParseResult binding and resource limits. The 32-candidate synthetic microbench is *not* TASK-019/E-035 p95, peak RSS or FTS5.
- `main` is **`protected=false`**, visible repository rulesets **`[]`**; individual protection endpoint returned 403. Recommend owner-managed protection in staged order: confirm actual GitHub Actions job names and permissions; create PR-only requirement and required Package/Documentation checks; provision external reviewer capacity before requiring approvals; review runner/service accounts and exceptional bypasses; verify a sample PR can still merge under the policy. No settings changed without owner approval.
- PR #33 original R1/P2 review thread remains for owner inspection; use original [blocking review](https://github.com/Gandalem/stellaris-suppoter/pull/33#pullrequestreview-5491123354), [final technical hold release](https://github.com/Gandalem/stellaris-suppoter/pull/33#pullrequestreview-5491330176), exact before/after 20-failed/749-pass → 769-pass CI in previous evidence. **No unilateral thread resolution**.

## E-027 / TASK-014 / F-005 gating

At C3 PR submission: TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`, TASK-015–022 `todo`, active_task=next_task `TASK-014`, latest_game_version `null`, product_implemented `false`. Once C3 undergoes independent technical review, **owner merger**, and **new actual main full CI** with all acceptance gaps resolved, prepare a **separate closure PR** proposing E-027 `pass`, F-005 `verified`, TASK-014 `done` for the *authored synthetic scope only*. Real game version must remain null until separately verified.
