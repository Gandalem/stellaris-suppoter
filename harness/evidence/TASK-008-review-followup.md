# TASK-008 review follow-up evidence

날짜: 2026-09-23  
리뷰 기준 head: `c7052a3879a24a7fd66fb60355a18188bab1cab4`  
R1-R3 code/test follow-up head: `e5f3a98ab2970f786e5f2b90262fa737c0325910`  
PR: https://github.com/Gandalem/stellaris-suppoter/pull/14

기존 E-014 synthetic normal/collision 성공 기록은 유지한다. 이 문서는 추가 반례 R1-R3와 수정 후 재검증을 연결한다.

## R1 parse error and completeness propagation

초기 adapter는 `DocumentNode`만 받아 parser/lexer diagnostic과 completeness를 잃었다.

수정:
- `adapt_technologies()` 입력을 `ParseResult`로 변경.
- lexer/parser diagnostics를 `TechnologyAdaptResult.diagnostics`로 전달하고 origin을 보존.
- candidate span과 겹치는 parse diagnostics를 candidate에도 연결.
- parser error 또는 unclosed subtree가 있는 candidate는 `resolution="partial"`.
- result에 `complete`를 추가해 정상 empty input과 error-produced empty AST를 구별.
- 정상적으로 추출된 다른 candidate는 유지 가능하되 global parse/lexer error가 있으면 result.ok/complete가 성공으로 바뀌지 않음.

회귀:
- unclosed block -> `PARSE_UNCLOSED_BLOCK` 보존, candidate partial.
- missing field value -> `PARSE_MISSING_VALUE` 보존, candidate partial.
- nested unsupported expression -> `PARSE_UNKNOWN_SYNTAX` 보존, candidate partial.
- invalid UTF-8 -> candidates empty이지만 `ENCODING_ERROR`, ok=false, complete=false.
- lexer token limit -> `LIMIT_EXCEEDED` 보존, complete=false.
- normal empty file -> diagnostics empty, ok=true, complete=true.

## R2 prerequisite extraction contract

지원하는 prerequisite reference는 다음 조건으로 제한한다.

- field name is `prerequisites`.
- operator is assignment `=`.
- value is a block.
- each extracted target is a non-empty literal identifier or quoted string.

그 외 표현은 raw field/source span을 유지하되 relation-like prerequisite record로 확정하지 않는다.

회귀:
- `prerequisites > { "other" }`
- `prerequisites < { "other" }`
- `prerequisites >= { "other" }`
- `prerequisites <= { "other" }`

위 비교식은 prerequisite record를 생성하지 않고 `ADAPTER_UNSUPPORTED_PREREQUISITES_OPERATOR` warning + partial resolution.

- `prerequisites = { @ref }`
- `prerequisites = { "" }`
- `prerequisites = { 123 }`

위 값은 target_game_id로 승격하지 않고 `ADAPTER_UNRESOLVED_PREREQUISITE` warning + partial resolution.

정상 `prerequisites = { "quoted_id" bare_id }`는 원래 순서/raw/source ref와 함께 두 reference를 생성한다.

## R3 retained raw memory and serialization budget

초기 adapter는 각 AST node마다 subtree 전체 raw string을 저장했고 field value tree와 candidate item tree도 별도로 생성했다.

수정:
- `RawNodeRef`는 raw string을 저장하지 않고 immutable source bytes + SourceRef span을 공유.
- `raw` / `raw_value`는 필요 시 slice를 materialize하는 non-cached property.
- candidate의 ordered raw tree를 한 번만 만들고 `TechnologyField.value`는 그 tree의 같은 node object를 참조.
- default `to_dict()`는 raw subtree strings를 materialize하지 않고 source refs를 직렬화.
- explicit `include_raw=True`는 shared byte budget을 요구하며 기본 1 MiB를 초과하면 `AdapterSerializationLimitError`; silent truncation이나 MemoryError 의존이 아님.
- adapter dataclasses는 slots를 사용해 per-node object overhead도 줄임.

회귀:
- 256 KiB payload + depth 80 synthetic input에서 모든 RawNodeRef가 같은 source bytes object를 공유.
- field value가 candidate item raw tree의 동일 node object를 참조.
- default JSON metadata output is smaller than input and contains no retained subtree raw copies.
- explicit raw serialization with 1 KiB budget fails deterministically with `AdapterSerializationLimitError`.
- small explicit raw serialization succeeds.

## CI

PR Package run `35864909563`, test-merge `e5b1e18`:
- Ubuntu / Python 3.11: 174 passed; technology adapter 20 passed; Ruff/harness success.
- Windows / Python 3.13: 174 collected, 171 passed + 3 existing intentional skips; technology adapter 20 passed; Ruff/harness success.
- Windows skips are the existing POSIX-only inventory/lexer tests; technology adapter follow-up tests run without skips.

Documentation harness PR run `35864909480`: Ubuntu/Windows success.

## 상태

- TASK-007 done / F-004 verified 유지.
- TASK-008 doing.
- E-014 기존 pass 기록 유지 + R1-R3 follow-up evidence 추가.
- F-005 in_progress.
- latest_game_version=null.
