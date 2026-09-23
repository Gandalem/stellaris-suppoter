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
