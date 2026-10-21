# TASK-014 — official authored-synthetic domain coverage closure proposal

Date: **2026-10-12 (Asia/Seoul)**. This Evidence is authored on a **separate, initially unmerged documentation/ledger-only closure PR** from verified real main `aed7e11fae9d19bae62401fa69eaa35b9a841c6b`. The ledger transitions in this PR are **proposed**, not changes already applied to `main`, until owner merge and subsequent main CI.

## Actual source PR #35 merge and external evidence

- [C3 PR #35](https://github.com/Gandalem/stellaris-suppoter/pull/35): **closed / merged=true**, reviewed and merged **source head** `e76d4e6684d8b501bf837b8cc77db6b241a05e67`, previous main/base `b3533f8c97e106adbf7d94119aac2d612f61040f`.
- Real main merge/current source for this closure branch: **`aed7e11fae9d19bae62401fa69eaa35b9a841c6b`**. The earlier PR candidate **test-merge `4277b5d9038c49e9cd99f9319cee73f7b85ec04d` was not this real merge**.
- [Final technical review #5492209616](https://github.com/Gandalem/stellaris-suppoter/pull/35#pullrequestreview-5492209616) inspected final C3 head, accepted the 13-kind A–F authored synthetic matrix, and found **no new merge-blocking code defects**. GitHub review state **`COMMENTED` by connected PR-owner account `Gandalem`**, **not** an independent formal third-party **`APPROVED`**. The owner subsequently merged #35.
- C3 candidate [PR Package CI #38258352159](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38258352159): **Ubuntu 927 passed**, **Windows 924 passed + the original 3 skips**, Ruff/harness both OS success. [PR Documentation #38258352128](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38258352128): both OS success. All **four** PR checkout logs = temporary test-merge `4277b5d9038c49e9cd99f9319cee73f7b85ec04d`; final C3 head [push Package #38258244457](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38258244457) both OS success with exact source-head checkout. These are supplementary review proof, **not** a substitute for the next main integration gate.

## NEW actual main integration, all four job checkout SHA logs verified

Two workflows ran from a **main push** at exactly **`aed7e11fae9d19bae62401fa69eaa35b9a841c6b`**. Both returned **`completed/success`** on GitHub Actions; all four actual job logs were fetched and inspected.

| Workflow | OS / Python | Actual job ID | Full pytest | Ruff | Harness | Actual checkout |
|---|---|---|---|---|---|---|
| [Package and tooling #38263803353](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38263803353) | Ubuntu 3.11 | `114860757083` | **927 passed** | `All checks passed!` | `harness_valid=true` | `aed7e11fae9d19bae62401fa69eaa35b9a841c6b` |
| [Package and tooling #38263803353](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38263803353) | Windows 3.13 | `114860757591` | **924 passed, 3 pre-existing skipped** | `All checks passed!` | `harness_valid=true` | same exact merge SHA |
| [Documentation harness #38263803250](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38263803250) | Ubuntu 3.11 | `114860757190` | N/A (harness-only job) | N/A | `harness_valid=true` | same exact merge SHA |
| [Documentation harness #38263803250](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38263803250) | Windows 3.13 | `114860757579` | N/A (harness-only job) | N/A | `harness_valid=true` | same exact merge SHA |

No CI rerun or waiver was used for this gate; **four real main checkouts** were verified. Existing 3 Windows skips predate C3 and were neither added nor expanded; no test deletions. No new installed-game smoke test or release/publishing job was performed.

## E-027 — all-thirteen-kind authored synthetic A–F acceptance

`E-027` fixture `all-domains` and [C3 Evidence](TASK-014-e027-phase-c3.md) describe **13 explicitly opt-in authored synthetic domain kinds**: `component_template`, `building`, `district`, `pop_job`, `trait`, `government`, `civic`, `origin`, `tradition`, `ascension_perk`, `event`, `scripted_trigger`, `scripted_effect`.

- **A — normal static definitions:** DomainKind-specific root, explicit key/id, wrapper or nested group, event namespace; byte-accurate identifier, fields and raw conditions, original AST/source order, nested raw children, repeated cost 100/200/300 and field occurrence, SourceRef span/source_sha/snapshot/path, correct `synthetic_static` support.
- **B — error and unsupported input:** unknown AST and operators, unclosed block, unsupported wrapper, dynamic/missing ID/expression, quoted fake definitions and comments; preserve partial/unhandled/blocked instead of invented `complete=True` or engine interpretation.
- **C — duplicates/collisions:** same-file definition occurrences and exact independent source, same-kind cross-file collision, different-kind identical ID separation, cross-snapshot refusal and ambiguous targets without invented mod priority.
- **D — localisation:** explicit verified name key versus game ID, Korean/English, English fallback, missing/double/dynamic/cyclic translations, SourceRef/dependency/budget/snapshot limits. Scripted trigger/effect intentionally have `localisation_key=None`; no invented ID/name/title translation.
- **E — source/provenance integrity:** R1 `items`, `fields[].value`, `conditions[].value`, nested `RawNodeRef.children` separate backing and borrowed SourceRef rejection, original bytes and SHA; R2 complete canonical ParseResult binding, foreign/empty/truncated AST/token/line-column manipulation and changed source SHA/path/snapshot rejection. Event qualified ID suffix and scripted dynamic `PairNode.key_span` exact-source regressions retained.
- **F — resource/regressions:** lexer/parser bytes/tokens/nodes/depth, shared diagnostic budget 999/1000/1200 representative paths, parser+adapter warning combination, `LIMIT_EXCEEDED` hard block, raw serialization limit, invalid UTF-8, BOM/CRLF/Korean byte spans; original Technology/SQLite/Search/CLI suite preserved.

C3 added **158 authored synthetic parameterized cases** to the existing **769 Ubuntu baseline**: **927 actual successful full-suite pytest cases on new main** (Windows 924 passed + 3 pre-existing skipped). Original foundation/Wave2/Wave3/Wave4/Wave5 test and evidence records remain unchanged. C3's initial test-only Ubuntu pytest 927 already passed; a *test helper-only* Ruff UP012 issue was corrected before final PR CI. **No product-code fix was necessary in C3**; no fabricated before-fix test failure.

### Scope boundaries and residual technical risks

- `E-027=pass`, `F-005=verified`, `TASK-014=done` mean **only the thirteen authored synthetic static adapter contracts described above**, with identified unsupported structures and immutable provenance. No real Stellaris installation, installed grammar, DLC/mod order, game engine execution, economic/combat calculation, version compatibility, multi-domain SQLite/CLI exposure, or overlay integration was verified.
- Therefore `latest_game_version=null` and `product_implemented=false` remain unchanged. `TASK-015` (static reference graph and CLI `refs`) remains `todo`; `F-011` remains `in_progress` until refs/diff gates.
- Prior R1/R2 full-source/buffer-binding protections are retained. [P3 Issue #34](https://github.com/Gandalem/stellaris-suppoter/issues/34) tracks optional, **non-blocking**, source/snapshot/path/SHA-bound reparse reuse (32 canonical reparses for 32 separate candidates); no security validation removed or TASK-019/E-035 performance result claimed.
- Current observed `main protected=false` and readable rulesets `[]`; detailed protection endpoint may be 403 due to integration permissions. Owner may later introduce staged PR-only changes, precise Package/Documentation required checks and truly independent approvers after runner permissions review; **no repository settings modified**.

## Proposed official ledger transitions and **mandatory further gate**

After all real PR #35 main integration steps above succeeded, this **closure PR proposes**:
- `harness/tasks.json`: TASK-014 **`doing → done`**, keep all prior evidence and append this closure proof.
- `harness/features.json`: F-005 **`in_progress → verified`** **for authored synthetic scope only**, keep all earlier source evidence.
- `harness/evals.jsonl`: E-027 **`not_run → pass`**, append source matrix and this real main integration proof only; every other E-ID unchanged.
- `harness/state.json`: `active_task=null`, `next_task=TASK-015`; retain `latest_game_version=null`, `product_implemented=false`, and historical notes.

**Important:** This file itself does not merge anything. The closure PR **must pass its own exact-head push / PR test-merge Ubuntu & Windows Package pytest/Ruff/harness and Documentation jobs**, pass independent ledger/technical review, then the **owner** must actually merge. A **different new actual main push** from that closure commit must again pass the four real jobs with the true closure-merge checkout SHA. **Only then** TASK-015 may change from todo to doing and implementation may begin on another dedicated branch. Any failure or absent merge pauses the next task.
