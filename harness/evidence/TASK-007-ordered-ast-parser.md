# TASK-007 ordered AST parser evidence

날짜: 2026-09-23  
기준 main: `1c8247ee2eea330b6444de33fdc2cb03a82abb91`  
기능 candidate: `b475f72394494d83a427f8b04bdc3761b83da95b`  
Package and tooling push run: 35815674467

## 구현

- lexer token order를 보존하는 ordered AST parser.
- AST node: scalar, pair, block, unknown.
- duplicate pair를 overwrite하지 않고 occurrence 순서대로 보존.
- mixed scalar/pair block의 원래 순서 보존.
- 각 node가 original byte span을 유지하고 source slice를 재구성 가능.
- unsupported operator-like expression은 known pair semantics로 만들지 않고 `UnknownNode` + `PARSE_UNKNOWN_SYNTAX`.
- unclosed block은 partial AST를 유지하되 `PARSE_UNCLOSED_BLOCK` error.
- parser 기본 limits: depth 128, nodes 100,000, diagnostics 1,000.
- configurable recursion depth는 256 이하만 허용.
- depth 초과는 balanced raw region을 `UnknownNode`로 보존하고 `PARSE_DEPTH_LIMIT`.
- node budget 초과는 `PARSE_NODE_LIMIT`으로 중단.
- lexer diagnostic은 origin=lexer로 ParseResult에 전달.

## E-011 Ordered duplicate AST

`01_demo_collision.txt`:
- duplicate `value = first`, `value = second` 둘 다 유지.
- 순서 유지.
- `mixed = { alpha beta key = gamma }`에서 scalar alpha, scalar beta, pair key=gamma 순서 유지.
- pair raw byte span이 원문과 일치.

결과: pass.

## E-012 Unknown script syntax

`unsupported_operator.txt`:
- `mystery ^= 42`를 known assignment/comparison으로 해석하지 않음.
- 하나의 unknown node로 source span 보존.
- raw bytes가 정확히 `mystery ^= 42`.
- diagnostic `PARSE_UNKNOWN_SYNTAX`.
- `mystery` 또는 `^`를 key로 하는 invented pair가 생성되지 않음.

결과: pass.

## E-013 Malformed and deep script

`unclosed_block.txt` 및 합성 deep/node-flood bytes:
- outer unclosed block은 `closed=False` + `PARSE_UNCLOSED_BLOCK`.
- depth limit 초과 영역은 recursion을 계속 확장하지 않고 raw unknown region으로 보존.
- max_nodes=10에서 정확히 10 nodes까지만 생성 후 `PARSE_NODE_LIMIT`.
- invalid UTF-8 lexer error는 parse success로 바뀌지 않고 `ENCODING_ERROR` 유지.
- invalid parser limit type/value는 explicit exception.

결과: pass.

## CI

Package and tooling run 35815674467:
- Ubuntu / Python 3.11: 140 passed; parser 10 passed; Ruff/harness success.
- Windows / Python 3.13: 140 collected, 137 passed + 3 intentional skips; parser 10 passed; Ruff/harness success.
- Windows skips는 기존 inventory surrogateescape 및 lexer POSIX-only tracemalloc/wall-clock tests이며 parser tests는 skip 없이 실행됐다.

## 상태

E-011/E-012/E-013 pass.  
TASK-007은 review/main integration 전까지 doing.  
F-004는 TASK-007 main integration 전까지 in_progress.  
latest_game_version=null.
