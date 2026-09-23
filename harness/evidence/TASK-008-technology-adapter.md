# TASK-008 technology adapter evidence

날짜: 2026-09-23  
기준 main: `959e3fc669c0927ed8eddec559bef055e155f253`  
기능 candidate: `7810f9972ee520dd8da716fcc84c3d5d6c70bb21`  
Package and tooling push run: `35858794110`

## 구현

- ordered AST를 입력으로 받는 technology domain adapter.
- file-level source context에서 DATA_CONTRACTS의 SourceRef 필드를 구성.
- top-level identifier assignment + block을 technology candidate로 추출.
- technology block의 모든 AST item을 ordered `RawNodeRef`로 보존.
- field occurrence를 tuple로 보존해 duplicate field를 overwrite하지 않음.
- raw field value와 field/node source span을 유지.
- prerequisites block의 scalar occurrence를 순서대로 별도 prerequisite record로 노출하면서 raw value/source ref도 보존.
- potential/weight/nested modifier 등 block 구조를 raw ordered child tree로 보존.
- unknown technology item은 raw node를 유지하고 `ADAPTER_UNKNOWN_ITEM` warning.
- 같은 game_id가 다른 파일에 존재해도 adapter 결과를 key overwrite하지 않음.
- adapter는 AST를 수정하거나 게임 의미를 실행하지 않음.

## E-014 Technology extraction

Synthetic `00_demo_normal.txt`:
- 4개 technology ID를 source order로 추출.
- `demo_prism_lattice`의 fields: area, tier, cost, prerequisites, potential, weight 순서 보존.
- cost raw expression `@demo_cost` 유지.
- prerequisite `"demo_echo_theory"`의 raw value, target ID, source ref 보존.
- potential 및 weight/modifier nested condition structure가 ordered raw child tree로 보존.
- candidate/field/value SourceRef byte range가 original bytes와 일치.

Synthetic `01_demo_collision.txt`:
- duplicate field `value = first`, `value = second` 두 occurrence와 순서 보존.
- mixed block의 scalar/pair item order 보존.
- normal/collision 파일의 동일 `demo_prism_lattice` ID가 서로 다른 source ref를 가진 두 candidate로 유지됨.

Inline unknown fixture:
- unknown item raw span 유지.
- 뒤 정상 field를 삼키지 않음.
- explicit adapter warning을 생성.

결과: E-014 pass.

## CI

Package and tooling push run `35858794110`:
- Ubuntu / Python 3.11: 159 passed; technology adapter 5 passed; Ruff/harness success.
- Windows / Python 3.13: 159 collected, 156 passed + 기존 3 intentional skips; technology adapter 5 passed; Ruff/harness success.
- Windows skips are the existing POSIX-only inventory/lexer checks; technology adapter tests run without skips.

## 상태

E-014 pass.  
TASK-008은 reviewer re-check/main integration 전까지 doing.  
F-005는 technology vertical slice 이후 remaining adapters가 남아 있으므로 in_progress.  
F-004 verified 유지.  
latest_game_version=null.
