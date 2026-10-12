# TASK-014 PR #28 R1-R2/P2 independent review follow-up

Date: 2026-10-12 Asia/Seoul. **Authored synthetic evidence only.** This records repair of two review-identified security/source-grounding defects in the *partial four-domain foundation* PR. The original [TASK-014-foundation.md](TASK-014-foundation.md) was retained without modification.

## Fixed review target and status

- Original independent [R1-R2 review](https://github.com/Gandalem/stellaris-suppoter/pull/28#pullrequestreview-5486005735) fixed PR head: `a4af5b4d73ceba6ee294c8fe9d43417b3c31d933`.
- Actual review base `main`: `526cad817a1fbde65fcb6d89758c9017d5b92bde`. Original PR test-merge: `9dc61b87672f0452d844cfebaa4a8cbd105e1674` (not actual main merge).
- Test-only reproduction head: `54580d23af7b941828b785cf343da682c29ed96e`. The source code was **still unmodified** at this head.
- Code repair head: `f57ba199e8ad39e4eddb95f3179ccad8d1987471`. Final code + synthetic-test candidate, before recording this follow-up: `6f58e5895b8c5430407dfd834c04ce4b4f0843d0`.
- PR #28 remains open/unmerged; TASK-014 `doing`, F-005 `in_progress`, E-027 `not_run`. No TASK-015 or later task started, no new domain adapters, no real game version or product-complete claim.

## Before fix: actual failing repro, not a hypothetical code reading

- [Test-only PR Package run #38194882412](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38194882412), Ubuntu Python 3.11: **8 failed, 527 passed**. Windows job was cancelled due to subsequent code commit; no claim of pre-fix Windows execution.
- `tests/test_domain_review_followup.py` was added first. The 8 red regression cases were:
  - R1 `cost=100` source with unchanged SourceRef but independently replaced `DomainField.value._source` yielding `raw_value=999`; old `verify_domain_candidate` **returned True**.
  - R1 independent `conditions[].value._source` tamper; old verify **returned True**.
  - R1 nested raw child backing tamper; old verify **returned True** (both field and condition projections tested).
  - R2 foreign empty `parse_bytes(b"")` against real `building_x` source; old adaptation **did not raise**.
  - R2 document items removed but full genuine tokens retained; old adaptation **did not raise**.
  - R2 invalid UTF-8 `b"\\xff"` plus foreign empty parse; old adaptation **did not raise**.
  - R2 token line/column SourceSpan tamper; old adaptation **did not raise**.
  - R2 AST line/column SourceSpan tamper; old adaptation **did not raise**.
- Other authored synthetic positive tests in the same run succeeded; this is not a claim of real-game acceptance.

## Repair and bounded design

- `src/stellaris_supporter/domain/generic.py`: source-grounded candidate verification now walks **all** `candidate.items`, `candidate.fields[].value`, `candidate.conditions[].value`, and nested `RawNodeRef.children`; structural dataclass equality alone is not trusted for `_source`.
- Public `adapt_domain` validates SHA/path/AST/token bounds and compares the **complete** provided `ParseResult` (ordered tokens, AST, diagnostics, `node_count`, byte spans **and** line/column coordinates) against **one bounded canonical `parse_bytes(source)` per input file**, not per candidate. Missing definitions, foreign parse results and altered coordinates reject with `ValueError`.
- A parser/lexer *hard resource stop* retains `blocked=True` and no candidates without retrying input at more permissive limits. `ENCODING_ERROR` is also blocked, including genuine invalid UTF-8 parser results.
- `verify_domain_candidate` still rebuilds a verified candidate, but uses a private already-bound adaptation helper after **one** source reparse instead of an unnecessary second full parse. An authored mock test asserts one canonical reparse for a file containing two definitions and one for a candidate verification.
- No persisted schema, technology adapter, CLI, SearchService, or game logic change. No extra full-file reparse in the per-field/child loop.

## After fix: exact CI and checkout evidence for code + test candidate

- [PR Package #38194991367](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38194991367): Ubuntu Python 3.11 **536 passed**, Windows Python 3.13 **533 passed + same 3 existing POSIX-specific skipped**, Ruff both `All checks passed!`; `python scripts/check_harness.py` both OS `harness_valid=true`.
- [PR Documentation #38194991373](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38194991373): Ubuntu and Windows harness both success.
- All four PR jobs independently checked out **temporary PR test-merge** `b4c777369064edfaec592295eb44c30a6c42657f` combining code head `6f58e5895b8c5430407dfd834c04ce4b4f0843d0` with actual base `526cad817a1fbde65fcb6d89758c9017d5b92bde`. This is **not** a real `main` merge.
- [Exact head *push* Package #38194986937](https://github.com/Gandalem/stellaris-suppoter/actions/runs/38194986937): Ubuntu **536 passed**, Windows **533 passed + 3 existing skipped**, Ruff/harness both OS success; both job checkout logs identify **`6f58e5895b8c5430407dfd834c04ce4b4f0843d0`** (not the PR test-merge).
- Added this evidence and ledger pointers in a subsequent documentation-only commit. **That newer PR head needs its own final Package/Documentation/checkouts to be checked and reported separately**; the earlier results above must not be misrepresented as that new head's CI.

## Remaining boundaries and reviewer gate

- Four synthetic adapters remain foundation only: component templates, buildings, districts, and pop jobs. No remaining domains, storage/index/CLI exposure, actual Stellaris installation, game version/DLC/mod semantics, engine calculations or full E-027 localisation/collision coverage are claimed.
- Independent technical re-review must target the *latest final head and matching final PR test-merge* after the documentation-only update's Ubuntu/Windows Package, Ruff, harness and Documentation CI succeed. A request for review is not itself formal GitHub APPROVED.
- Owner alone may merge. Do not auto-merge, modify `main`, resolve old review threads or begin TASK-015.
