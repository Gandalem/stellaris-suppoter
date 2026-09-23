# TASK-006 Lexer and source spans

## 범위

작업 ID: TASK-006  
기능: F-004 Lossless script parsing  
평가: E-009, E-010  
브랜치: task/TASK-006-lexer-source-spans  
기준 main: `1e0a8fcfbb9661362c85aa24bd54b4e134901107`

## 구현

- byte-oriented UTF-8 lexer.
- token: BOM, whitespace, comment, braces, assignment/comparison operators, quoted string, number, identifier, variable.
- `>=`, `<=`를 단일 연산자보다 먼저 인식.
- string 안의 `#`, `{`, `}`를 syntax/comment로 해석하지 않음.
- backslash escaped quote 처리.
- original source를 token span으로 완전히 재구성 가능.
- byte span: 0-based half-open.
- line/column: 1-based, exclusive end.
- CRLF를 하나의 newline으로 계산.
- UTF-8 BOM은 별도 token으로 보존하고 다음 실제 source byte는 1:1에서 시작.
- invalid UTF-8은 replacement 없이 `ENCODING_ERROR`.
- unclosed quoted string은 `LEX_UNTERMINATED_STRING`.

## E-009

Synthetic lexical-edge fixture에서:
- comment 2개.
- quoted string 1개.
- string 내부 hash/brace가 별도 token이 되지 않음.
- escaped quote가 string을 조기 종료하지 않음.
- >, <=, >=, < operator 순서가 정확함.
- @demo_cost가 variable token.
- token raw byte concat이 input bytes와 정확히 동일.

## E-010

Synthetic encoding fixture에서:
- BOM bytes 0..3 별도 token.
- CRLF source position 보존.
- line 2 identifier가 정확히 line 2/column 1.
- string 내부 hash/brace 보존.
- invalid UTF-8의 첫 invalid byte에 ENCODING_ERROR.
- invalid bytes를 U+FFFD로 바꾸거나 다른 encoding으로 추측하지 않음.
- multibyte UTF-8 column은 byte 수가 아니라 codepoint 기준.
- unclosed string은 EOF까지 raw bytes 보존 + explicit error.

## 검증

기능 candidate `2912d1c192e5f0033a82da5845841c43e8a0ee5b`  
GitHub Actions run 35798925924:

- Ubuntu/Python 3.11: 109 passed, lexer 9 passed, Ruff/harness success.
- Windows/Python 3.13: 109 collected, 108 passed + 기존 POSIX-only inventory 1 skipped, lexer 9 passed, Ruff/harness success.

첫 구현 run에서 product tests는 통과했으나 Ruff style 3건이 발견돼 import/encode 표기만 수정한 뒤 위 candidate에서 재검증했다.

## 상태

E-009 pass.  
E-010 pass.  
TASK-006은 review/main integration 전까지 doing.  
F-004는 TASK-007 AST parser가 남아 in_progress.


## PR #12 resource follow-up

리뷰에서 기존 per-character `_position_map()`과 무제한 token accumulation의 메모리 증폭이 재현되어 TASK-006을 계속 doing으로 유지한다. 기존 E-009/E-010 문자열/span 성공 기록은 보존한다.

보완 정책:
- 위치 계산을 streaming line/column cursor로 전환해 문자별 dict/tuple을 만들지 않음.
- lexer 기본 `max_bytes=16 MiB`, `max_tokens=100,000`.
- byte limit은 UTF-8 validation 전에 적용.
- token limit은 다음 Token/SourceSpan 생성 전에 적용.
- 초과 시 partial success가 아니라 `LIMIT_EXCEEDED`.
- 긴 단일 comment/whitespace/string과 short-token flood 회귀를 추가.


## PR #12 resource follow-up 검증

리뷰에서 재현된 per-character position map 및 unbounded token growth를 보완했다.

최종 follow-up head: `ba130da911b0082b858e06e9c04a008993540ca6`

구현:
- 문자마다 `dict[offset] -> (line,column)`을 만들던 position map 제거.
- token이 소비될 때만 streaming line/column cursor 갱신.
- 긴 whitespace/comment/scalar/string 탐색은 regex/bytes.find 등 C-backed search 사용.
- 기본 `max_bytes=16 MiB`, `max_tokens=100,000`.
- byte limit은 UTF-8 validation 전에 적용.
- token limit은 다음 Token/SourceSpan 생성 및 긴 다음 token scan 전에 적용.
- 초과는 `LIMIT_EXCEEDED`; input truncation을 성공으로 처리하지 않음.
- 1 MiB comment/whitespace/string, token flood, 정확한 boundary, invalid limit type/value 회귀 추가.
- POSIX CPython에서 1 MiB comment의 tracemalloc peak가 16 MiB 미만인지 회귀 검사.
- 대형 parametrized bytes에 고정된 짧은 pytest id를 지정해 test collection/log 자체의 불필요한 대형 표현 생성을 피함.

검증:
- Package push run 35804610541
  - Ubuntu/Python 3.11: 122 passed, lexer 22 passed, Ruff/harness success.
  - Windows/Python 3.13: 122 collected, 120 passed + 2 intentional skips; lexer 21 passed + POSIX-only allocation probe 1 skipped; Ruff/harness success.
- Windows skips:
  - 기존 inventory surrogateescape filename POSIX-only.
  - lexer tracemalloc peak threshold POSIX CPython-only.
- Documentation harness PR run 35804614559: Ubuntu/Windows success.

기존 E-009/E-010 문자열/span evidence는 보존한다. 자원 반례와 이번 수정은 별도 follow-up evidence로 연결하며 TASK-006은 reviewer 재검토/main integration 전까지 `doing` 유지한다.

근거: [resource follow-up evidence](../evidence/TASK-006-resource-followup.md)


## Main integration

PR #12는 `9c9f1111cc672c05e1e848e14a1c2537574d55a2`에서 기술 검토를 통과한 뒤 main merge commit `1c8247ee2eea330b6444de33fdc2cb03a82abb91`로 병합됐다.

실제 main push 검증:
- Package and tooling run 35815351949
  - Ubuntu/Python 3.11.16: 130 passed, lexer 30 passed, Ruff/harness success.
  - Windows/Python 3.13.15: 130 collected, 127 passed + 3 intentional skips; lexer 28 passed + 2 intentional skips; Ruff/harness success.
- Documentation harness run 35815351946: Ubuntu/Windows success.

최종 상태:
- TASK-006: done.
- E-009/E-010: pass 유지.
- F-004: TASK-007/E-011~013이 남아 in_progress.
- latest_game_version: null 유지.

근거: [main integration evidence](../evidence/TASK-006-main-integration.md)
