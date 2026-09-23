# TASK-008 Technology adapter

## 범위

작업 ID: TASK-008  
기능: F-005 Domain adapters  
평가: E-014 Technology extraction  
브랜치: task/TASK-008-technology-adapter  
기준 main: `959e3fc669c0927ed8eddec559bef055e155f253`

## 목표

- TASK-007의 ordered AST를 입력으로 사용한다.
- synthetic technology 정의에서 entity ID를 식별한다.
- prerequisites를 원래 순서와 source span과 함께 추출한다.
- 비용/가중치/조건/효과 등 아직 의미를 확정하지 않은 표현은 raw AST/source span으로 보존한다.
- unknown node와 duplicate field를 임의로 제거하거나 마지막 값으로 덮어쓰지 않는다.
- adapter 결과에 원본 파일/byte source reference를 연결할 수 있게 한다.
- AST 자체를 domain 의미에 맞춰 변형하지 않는다.

## E-014 Technology extraction

Synthetic demo-tech fixture에서:
- expected technology ID를 추출한다.
- prerequisites occurrence/order를 보존한다.
- raw expressions와 condition structure를 손실 없이 참조한다.
- source spans/refs가 original bytes로 역추적 가능하다.
- unsupported/duplicate fields는 명시적으로 보존하거나 diagnostic으로 남기며 invented semantics가 없어야 한다.

## 상태

TASK-007 main integration 완료 후 시작.  
TASK-008 doing.  
F-005 in_progress.  
E-014 not_run.  
F-004 verified.  
latest_game_version=null.


## 구현 candidate

기능 candidate: `7810f9972ee520dd8da716fcc84c3d5d6c70bb21`

구현:
- DATA_CONTRACTS SourceRef 필드에 맞춘 source context/ref.
- ordered raw node tree로 field/condition 구조 보존.
- duplicate field occurrence/order 보존.
- prerequisites target/raw/source ref 추출.
- unknown technology item raw 보존 + explicit warning.
- 같은 game_id를 파일 간 overwrite하지 않음.

검증:
- Package and tooling push run `35858794110`.
- Ubuntu: 159 passed, technology adapter 5 passed, Ruff/harness success.
- Windows: 159 collected, 156 passed + 기존 3 intentional skips, technology adapter 5 passed, Ruff/harness success.
- E-014 pass.

TASK-008은 review/main integration 전까지 doing 유지. F-005는 remaining domain adapters가 남아 in_progress 유지.

근거: [technology adapter evidence](../evidence/TASK-008-technology-adapter.md)


## PR #14 review follow-up

리뷰 기준 head `c7052a3879a24a7fd66fb60355a18188bab1cab4`에서 다음 경계가 재현됐다.

- R1: parser/lexer diagnostics와 truncation/completeness state가 adapter에서 사라짐.
- R2: comparison operator, variable, empty/number prerequisite를 confirmed technology ID로 승격.
- R3: nested subtree raw strings와 duplicated raw tree 때문에 memory/output 증폭.

follow-up code/test head: `e5f3a98ab2970f786e5f2b90262fa737c0325910`

수정:
- adapter input을 `ParseResult`로 올려 diagnostics/origin/completeness를 보존.
- parse error가 겹치는 candidate는 partial; normal empty와 error-produced empty AST를 구분.
- prerequisite extraction을 assignment block + non-empty identifier/quoted literal로 제한.
- unsupported prerequisite forms는 raw/source ref를 유지하고 warning + partial resolution.
- RawNodeRef는 subtree raw string을 저장하지 않고 source bytes + SourceRef를 공유.
- field value는 candidate ordered raw tree의 same node object를 참조.
- default serialization은 raw strings를 materialize하지 않으며 explicit raw output에는 byte budget 적용.

검증:
- PR Package run `35864909563`, test-merge `e5b1e18`.
- Ubuntu: 174 passed, technology adapter 20 passed, Ruff/harness success.
- Windows: 174 collected, 171 passed + 기존 3 intentional skips, technology adapter 20 passed, Ruff/harness success.
- Documentation harness run `35864909480`: Ubuntu/Windows success.

E-014 기존 pass는 유지하고 follow-up evidence를 추가했다. TASK-008 doing / F-005 in_progress 유지.

근거: [TASK-008 review follow-up](../evidence/TASK-008-review-followup.md)
