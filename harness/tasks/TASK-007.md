# TASK-007 Ordered AST parser

## 범위

작업 ID: TASK-007  
기능: F-004 Lossless script parsing  
평가: E-011, E-012, E-013  
브랜치: task/TASK-007-ordered-ast-parser  
기준 main: `1c8247ee2eea330b6444de33fdc2cb03a82abb91`

## 목표

- lexer token order를 보존하는 ordered AST를 구현한다.
- duplicate assignments와 scalar/assignment mixed blocks에서 순서와 모든 occurrence를 보존한다.
- unknown/unsupported syntax는 invented semantics 없이 raw span과 diagnostic으로 남긴다.
- malformed braces와 excessive nesting은 bounded recovery로 처리한다.
- parser resource budget을 적용해 depth/node/diagnostic runaway를 방지한다.
- AST node와 diagnostic은 original source byte span을 유지한다.

## E-011 Ordered duplicate AST

Synthetic duplicate-mixed fixture에서:
- duplicate key가 overwrite되지 않음.
- 원래 occurrence 순서가 유지됨.
- block 안의 scalar와 assignment가 섞여 있어도 원래 순서가 유지됨.
- source span으로 원문을 역추적 가능해야 함.

## E-012 Unknown script syntax

Synthetic unknown-syntax fixture에서:
- unsupported operator/expression을 성공한 알려진 의미로 오인하지 않음.
- raw source span을 보존함.
- explicit diagnostic을 생성함.
- 이후 파싱을 가능한 범위에서 bounded하게 계속함.

## E-013 Malformed and deep script

Synthetic malformed-depth fixture에서:
- unclosed/mismatched brace가 false successful parse가 되지 않음.
- excessive nesting이 명시적 limit diagnostic으로 중단됨.
- recovery 및 diagnostic 수가 budget 안에 제한됨.
- lexer의 byte/token limits와 충돌하지 않는 parser-side bounds를 둠.

## 상태

TASK-006 main integration 완료 후 시작.  
E-011/E-012/E-013 not_run.  
TASK-007 doing.  
F-004 in_progress.  
latest_game_version=null.


## 구현 candidate

기능 candidate: `b475f72394494d83a427f8b04bdc3761b83da95b`

구현:
- ordered scalar/pair/block/unknown AST.
- duplicate pair와 mixed scalar/pair block 순서 보존.
- original byte span 및 raw source slice 보존.
- unsupported operator-like expression은 `UnknownNode` + `PARSE_UNKNOWN_SYNTAX`.
- unclosed block은 `PARSE_UNCLOSED_BLOCK`.
- default parser limits: depth 128, nodes 100,000, diagnostics 1,000.
- configurable max_depth는 현재 recursive implementation에서 128 이하만 허용.
- depth limit 초과는 bounded raw unknown region + `PARSE_DEPTH_LIMIT`.
- node limit 초과는 `PARSE_NODE_LIMIT`.
- lexer diagnostics는 parse result에 origin=lexer로 전달.

검증:
- Package and tooling push run 35815674467.
- Ubuntu/Python 3.11: 140 passed, parser 10 passed, Ruff/harness success.
- Windows/Python 3.13: 140 collected, 137 passed + 기존 3 intentional skips, parser 10 passed, Ruff/harness success.
- E-011/E-012/E-013 pass.

TASK-007은 reviewer re-check 및 main integration 전까지 doing 유지. F-004도 main integration 전까지 in_progress 유지.

근거: [ordered AST parser evidence](../evidence/TASK-007-ordered-ast-parser.md)


## PR #13 review follow-up

리뷰에서 compact unsupported operators, value-context unsupported expression/typed block, unknown recovery의 parent rbrace consumption, unsafe configurable max_depth=256이 재현됐다.

follow-up code/test head: `24ea1dc2b2048cbf132f85b9d0f0ddf0464479c6`

수정:
- unsupported operator-like suffix가 붙은 key를 normal pair로 확정하지 않음.
- scalar value 뒤 같은 line의 unsupported operator chain 및 typed block을 full raw unknown region으로 보존.
- quoted key/value 내부 operator text는 normal scalar/string 처리.
- unknown missing value에서 parent `}`를 소비하지 않음.
- configurable `max_depth` 상한을 128로 제한하고 128-level parse/to_dict/JSON serialization을 양 OS에서 검증.
- 129-level input은 `PARSE_DEPTH_LIMIT`, max_depth >128은 parsing 전 explicit ValueError.

검증:
- PR Package run 35818193879 / test-merge `c23a35e`.
- Ubuntu: 151 passed, parser 21 passed, Ruff/harness success.
- Windows: 151 collected, 148 passed + 기존 3 intentional skips, parser 21 passed, Ruff/harness success.
- Documentation harness run 35818193854: Ubuntu/Windows success.

E-011 기존 pass 유지. E-012/E-013은 follow-up evidence를 포함해 pass 재확정. TASK-007은 reviewer re-check 및 main integration 전까지 doing 유지.

근거: [review follow-up evidence](../evidence/TASK-007-review-followup.md)
