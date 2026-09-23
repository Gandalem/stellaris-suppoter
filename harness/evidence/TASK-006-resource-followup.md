# TASK-006 PR #12 resource follow-up evidence

날짜: 2026-09-23  
리뷰 기준 head: `6b54a19d1a0384f1eef04e95494e9b0ce050a16b`  
R1 follow-up head: `ba130da911b0082b858e06e9c04a008993540ca6`  
R2 CPU follow-up code head: `6bb62ee13a6c7790be4f62c861a00c93e470e55b`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/12

## 리뷰 반례

기존 lexer는 tokenization 전에 모든 character boundary의 line/column을 Python dict + tuple로 선할당하고 token list에도 자체 budget이 없었다.

리뷰에서 합성 입력으로 다음 위험이 재현됐다.
- 1 MiB ASCII comment 하나에서도 position object가 character 수만큼 생성.
- 1 MiB `{}` flood에서 매우 많은 Token/SourceSpan 생성.
- 4 MiB comment가 제한된 subprocess memory에서 raw MemoryError로 종료.

기존 E-009/E-010의 token/span correctness 성공은 삭제하지 않는다. 이 문서는 resource-boundary 후속 검증이다.

## 수정

### Streaming positions

전역 `_position_map()`을 제거했다. lexer는 현재 `line/column` cursor만 보유하고 token text가 소비될 때 span end를 계산한다.

- CRLF 한 newline 규칙 유지.
- UTF-8 multibyte column은 decoded codepoint 기준 유지.
- BOM zero-column-width contract 유지.
- comment/whitespace/string/scalar의 긴 구간은 Python byte-by-byte position object 생성 없이 처리.

### Explicit budgets

`lex_bytes()`:
- `max_bytes` 기본 16 MiB.
- `max_tokens` 기본 100,000.
- bool/non-int 및 non-positive limits는 명시적으로 거부.
- byte budget은 UTF-8 decode/validation 이전에 검사.
- token budget은 다음 Token/SourceSpan 생성 이전에 검사.
- token budget이 이미 소진됐으면 긴 다음 string/token을 scan하지 않음.
- 초과 시 `LIMIT_EXCEEDED`; partial tokens가 있을 수 있으나 `ok=false`이며 성공으로 취급하지 않음.

### Resource regressions

추가 tests:
- 1 MiB single comment.
- 1 MiB single whitespace.
- 1 MiB single string.
- POSIX CPython tracemalloc: 1 MiB comment peak < 16 MiB.
- byte limit over-boundary rejects before UTF-8 validation.
- byte exact-boundary accepted.
- 1 MiB `{}` flood with max_tokens=64 allocates exactly 64 tokens then fails.
- token exact-boundary accepted.
- invalid limit types/values.
- token budget exhausted before scanning a large next string.
- large parameter cases use short explicit pytest ids so test infrastructure does not stringify 1 MiB values into node ids.

## R2 escape-dense string CPU follow-up

재검토에서 quoted string scanner가 각 escape마다 closing quote를 suffix 전체에서 다시 찾을 수 있어 escape-dense 입력에서 제곱 시간에 가까운 증가가 확인됐다.

수정:
- quote와 backslash를 `_STRING_BOUNDARY_RE` 하나로 검색.
- `_scan_quoted_string()`은 찾은 boundary 이후로 cursor를 단조 증가시킨다.
- backslash는 기존 의미대로 자신과 다음 byte를 함께 건너뛰므로 escaped quote/backslash parity contract를 유지한다.
- 남은 suffix 전체의 quote search를 escape마다 반복하지 않는다.

추가 regression:
- 1 MiB급 escape-dense string의 원문 보존/정상 종료.
- POSIX CI에서 4 MiB escape-dense string의 bounded wall-clock regression (`< 5s`).
- Windows는 wall-clock threshold 자체는 환경 편차 때문에 intentional skip하고 기능 회귀는 실행한다.

R2 code head `6bb62ee13a6c7790be4f62c861a00c93e470e55b`의 PR test-merge `3ba4326` 검증:
- Package PR run `35805472084`.
- Ubuntu / Python 3.11: 124 passed, lexer 24 passed, Ruff/harness success.
- Windows / Python 3.13: 124 collected, 121 passed + 3 intentional skips, Ruff/harness success.
  - inventory surrogateescape filename regression.
  - POSIX-only tracemalloc threshold.
  - POSIX-only escape-dense wall-clock threshold.
- Documentation harness PR run `35805472091`: Ubuntu/Windows success.

## CI

Package push run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35804610541

| 환경 | 전체 pytest | lexer | Ruff | harness |
|---|---:|---:|---|---|
| Ubuntu / Python 3.11 | 122 passed | 22 passed | success | success |
| Windows / Python 3.13 | 120 passed + 2 intentional skips (122 collected) | 21 passed + 1 POSIX-only resource skip | success | success |

Windows intentional skips:
1. existing inventory surrogateescape filename regression.
2. lexer tracemalloc peak threshold calibrated for POSIX CPython.

Documentation harness PR run 35804614559:
- Ubuntu success.
- Windows success.

## 상태

E-009/E-010 pass 유지. TASK-006은 reviewer 재검토와 실제 main merge/push CI 전까지 doing. F-004는 TASK-007/E-011~013가 남아 in_progress. latest_game_version=null.
