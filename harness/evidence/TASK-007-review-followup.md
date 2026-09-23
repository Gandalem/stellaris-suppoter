# TASK-007 parser review follow-up evidence

날짜: 2026-09-23  
리뷰 기준 head: `5824d213480b21bb3b1e4d62fefd26aa64296eab`  
R1-R3 code/test follow-up head: `24ea1dc2b2048cbf132f85b9d0f0ddf0464479c6`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/13

## 리뷰 반례

초기 TASK-007 candidate의 ordered duplicate AST 기본 동작은 유지됐지만 다음 경계가 추가로 재현됐다.

- compact unsupported operators: `mystery^=42`, `mystery!=42`가 정상 pair로 확정됨.
- value-context unsupported expression: `x = y ^= z`가 여러 정상 pair로 분해됨.
- unsupported typed block: `color = rgb { 1 2 3 }`가 scalar pair + 별도 block으로 정상 처리됨.
- unknown expression의 missing value가 부모 `}`를 소비해 후속 sibling scope를 변경함.
- `max_depth=256`을 허용했지만 200-level input에서 raw `RecursionError`가 발생함.

기존 E-011 ordered duplicate success와 이전 E-012/E-013 실행 기록은 삭제하지 않는다. 이 문서는 추가 반례와 수정 후 현재 판정을 연결한다.

## R1 unsupported syntax context

수정:
- identifier key가 unsupported operator-like suffix를 포함한 채 known binary operator와 연결되면 전체 expression을 `UnknownNode`로 보존.
- scalar value 뒤 같은 line에 operator-like token + binary operator가 이어지면 전체 value expression을 unknown으로 보존.
- scalar value 뒤 같은 line에 block이 이어지는 typed-block form은 전체 raw region을 unknown으로 보존.
- quoted key/value 내부 operator 문자에는 이 검사를 적용하지 않음.
- normal mixed scalar/pair block 동작은 기존 E-011 회귀로 유지.

회귀:
- `mystery^=42`
- `mystery^ = 42`
- `mystery!=42`
- `x = y ^= z`
- `color = rgb { 1 2 3 }`
- quoted key `"mystery^" = 42`
- quoted value `x = "^= != { }"`

결과: unsupported forms는 `PARSE_UNKNOWN_SYNTAX` + exact raw span, quoted forms는 정상 pair.

## R2 enclosing brace recovery

`_consume_raw_value()`은 다음 significant token이 `rbrace`면 소비하지 않고 해당 index를 반환한다.

회귀:
`root = { mystery ^= } after = 1`

검증:
- root block `closed=True`.
- unknown raw bytes는 `mystery ^=`까지만 포함.
- 부모 `}`는 enclosing sequence가 처리.
- `after = 1`은 document-level sibling으로 유지.
- 잘못된 `PARSE_UNCLOSED_BLOCK`이 추가되지 않음.

## R3 supported depth boundary

재귀형 구현에서 실제 Python frame 여유를 고려해 configurable `max_depth` 상한을 기본값과 같은 128로 제한했다.

- `max_depth=128`: 128-level input parse success.
- 해당 AST의 `to_dict()` 및 JSON serialization success.
- 129-level input with max_depth=128: raw exception 대신 `PARSE_DEPTH_LIMIT`.
- `max_depth=129` 및 이전 unsafe setting `max_depth=256`: parsing 전에 explicit `ValueError`.
- node/diagnostic budgets와 기존 default-depth behavior는 유지.

이 변경은 Python recursion limit을 제품 계약으로 가정하지 않고, 현재 recursive parser가 양쪽 CI에서 검증한 안전한 설정 범위를 명시적으로 제한한다.

## CI

PR Package run `35818193879`, test-merge `c23a35e`:
- Ubuntu / Python 3.11: 151 passed, parser 21 passed, Ruff/harness success.
- Windows / Python 3.13: 151 collected, 148 passed + 3 existing intentional skips, parser 21 passed, Ruff/harness success.
- Windows skips는 기존 inventory surrogateescape 및 lexer POSIX-only resource thresholds이며 TASK-007 follow-up tests는 skip 없이 실행됐다.

Documentation harness PR run `35818193854`:
- Ubuntu success.
- Windows success.

## 상태

E-011 기존 pass 유지.  
E-012는 R1 follow-up까지 포함해 pass 재확정.  
E-013은 R2/R3 follow-up까지 포함해 pass 재확정.  
TASK-007은 reviewer re-check/main integration 전까지 doing.  
F-004는 in_progress.  
latest_game_version=null.
