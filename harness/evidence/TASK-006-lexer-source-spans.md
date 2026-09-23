# TASK-006 lexer and source spans evidence

날짜: 2026-09-23  
기능 candidate: `2912d1c192e5f0033a82da5845841c43e8a0ee5b`  
기준 main: `1e0a8fcfbb9661362c85aa24bd54b4e134901107`  
GitHub Actions run: https://github.com/Gandalem/stellaris-suppoter/actions/runs/35798925924

## E-009 String and comment tokens

`tests/fixtures/synthetic/corpus/common/technology/02_demo_lexical_edges.txt`를 사용했다.

검증:
- escaped quoted string 전체가 하나의 string token.
- string 내부 `#`, `{`, `}`는 comment/brace token이 아님.
- 실제 source comments만 comment token.
- long comparison operators를 먼저 tokenization.
- variable token 원문 보존.
- 모든 token의 raw byte slice를 순서대로 결합하면 original bytes와 동일.

## E-010 Encoding and line offsets

`bom_crlf.txt`, `invalid_utf8.txt`, `unclosed_string.txt`와 직접 작성 synthetic bytes를 사용했다.

검증:
- UTF-8 BOM 3 bytes를 별도 token으로 보존.
- BOM 뒤 첫 실제 source byte를 line 1/column 1로 계산.
- CRLF는 line transition 1회.
- byte span은 0-based half-open.
- line/column은 1-based, end exclusive.
- invalid UTF-8은 tokenization을 성공시키지 않고 ENCODING_ERROR + invalid byte span.
- replacement character나 encoding fallback 없음.
- unclosed string은 LEX_UNTERMINATED_STRING.
- Korean multibyte characters는 columns를 codepoint 단위로 계산하고 byte span은 원래 UTF-8 길이를 유지.

## CI

| 환경 | 전체 pytest | lexer | Ruff | harness |
|---|---:|---:|---|---|
| Ubuntu / Python 3.11 | 109 passed | 9 passed | success | success |
| Windows / Python 3.13 | 108 passed + 1 existing POSIX-only inventory skip (109 collected) | 9 passed | success | success |

## 한계

이 단계는 lexer와 source spans만 검증한다. assignment/block AST, duplicate preservation, unsupported syntax semantics, brace/depth recovery는 TASK-007 책임이다. 실제 Stellaris files는 사용하지 않았다.
