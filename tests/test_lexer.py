from __future__ import annotations

from pathlib import Path
import tracemalloc

import pytest

import stellaris_supporter.parsing.lexer as lexer_module
from stellaris_supporter.parsing.lexer import lex_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "corpus"


def kinds(result) -> list[str]:
    return [token.kind for token in result.tokens]


def test_lexical_edge_fixture_keeps_string_comment_and_operator_boundaries() -> None:
    source = (
        FIXTURES / "common" / "technology" / "02_demo_lexical_edges.txt"
    ).read_bytes()

    result = lex_bytes(source)

    assert result.ok
    assert result.diagnostics == ()
    assert b"".join(token.raw_bytes(source) for token in result.tokens) == source

    strings = [token for token in result.tokens if token.kind == "string"]
    assert len(strings) == 1
    assert strings[0].text == r'"literal # hash and { brace } and \"quoted\""'
    assert strings[0].span.line_start == 5

    assert kinds(result).count("comment") == 2
    assert [token.text for token in result.tokens if token.kind in {"gt", "lte", "gte", "lt"}] == [
        ">",
        "<=",
        ">=",
        "<",
    ]
    variables = [token for token in result.tokens if token.kind == "variable"]
    assert [token.text for token in variables] == ["@demo_cost"]


def test_braces_and_hash_inside_escaped_string_never_become_structure() -> None:
    source = b'key = "a # literal { } and \\"quoted\\"" # real comment\n'

    result = lex_bytes(source)

    assert result.ok
    string = next(token for token in result.tokens if token.kind == "string")
    assert string.raw_bytes(source) == b'"a # literal { } and \\"quoted\\""'
    assert kinds(result).count("comment") == 1
    assert kinds(result).count("lbrace") == 0
    assert kinds(result).count("rbrace") == 0


def test_bom_crlf_fixture_preserves_bytes_and_source_positions() -> None:
    source = (FIXTURES / "encoding" / "bom_crlf.txt").read_bytes()

    result = lex_bytes(source)

    assert result.ok
    assert b"".join(token.raw_bytes(source) for token in result.tokens) == source

    bom = result.tokens[0]
    assert bom.kind == "bom"
    assert bom.span.to_dict() == {
        "byte_start": 0,
        "byte_end": 3,
        "line_start": 1,
        "column_start": 1,
        "line_end": 1,
        "column_end": 1,
    }

    identifier = next(token for token in result.tokens if token.text == "demo_bom_crlf")
    assert (identifier.span.line_start, identifier.span.column_start) == (2, 1)

    string = next(token for token in result.tokens if token.kind == "string")
    assert string.text == '"# { stays text }"'
    assert (string.span.line_start, string.span.column_start) == (3, 12)
    assert kinds(result).count("comment") == 1
    assert kinds(result).count("lbrace") == 1
    assert kinds(result).count("rbrace") == 1


def test_crlf_counts_as_one_newline_for_exclusive_end_positions() -> None:
    source = b"alpha\r\nbeta\r\n"

    result = lex_bytes(source)

    alpha = result.tokens[0]
    newline = result.tokens[1]
    beta = result.tokens[2]
    assert alpha.span.to_dict() == {
        "byte_start": 0,
        "byte_end": 5,
        "line_start": 1,
        "column_start": 1,
        "line_end": 1,
        "column_end": 6,
    }
    assert newline.raw_bytes(source) == b"\r\n"
    assert (newline.span.line_start, newline.span.column_start) == (1, 6)
    assert (newline.span.line_end, newline.span.column_end) == (2, 1)
    assert (beta.span.line_start, beta.span.column_start) == (2, 1)


def test_invalid_utf8_is_explicit_and_preserves_original_error_bytes() -> None:
    source = (FIXTURES / "encoding" / "invalid_utf8.txt").read_bytes()
    before = bytes(source)
    bad = source.index(b"\xff")

    result = lex_bytes(source)

    assert not result.ok
    assert result.tokens == ()
    assert len(result.diagnostics) == 1
    diagnostic = result.diagnostics[0]
    assert diagnostic.code == "ENCODING_ERROR"
    assert diagnostic.span.byte_start == bad
    assert diagnostic.span.byte_end == bad + 1
    assert diagnostic.span.line_start == 2
    assert source == before


def test_unclosed_string_is_error_but_remaining_raw_bytes_are_preserved() -> None:
    source = (FIXTURES / "malformed" / "unclosed_string.txt").read_bytes()

    result = lex_bytes(source)

    assert not result.ok
    assert [item.code for item in result.diagnostics] == ["LEX_UNTERMINATED_STRING"]
    assert b"".join(token.raw_bytes(source) for token in result.tokens) == source
    string = next(token for token in result.tokens if token.kind == "string")
    assert string.span.byte_end == len(source)


def test_multibyte_characters_advance_columns_by_codepoint_not_byte() -> None:
    source = 'name = "한글"\n'.encode()

    result = lex_bytes(source)

    string = next(token for token in result.tokens if token.kind == "string")
    assert string.text == '"한글"'
    assert (string.span.column_start, string.span.column_end) == (8, 12)
    assert string.span.byte_end - string.span.byte_start == len('"한글"'.encode())


def test_long_operators_win_before_single_character_operators() -> None:
    source = b"a>=1 b<=2 c>3 d<4"

    result = lex_bytes(source)

    operators = [
        token.kind
        for token in result.tokens
        if token.kind in {"gte", "lte", "gt", "lt"}
    ]
    assert operators == ["gte", "lte", "gt", "lt"]


def test_numbers_identifiers_and_variables_keep_original_text() -> None:
    source = b"42 -3 +4.5 .75 alpha @cost"

    result = lex_bytes(source)

    significant = [
        (token.kind, token.text)
        for token in result.tokens
        if token.kind != "whitespace"
    ]
    assert significant == [
        ("number", "42"),
        ("number", "-3"),
        ("number", "+4.5"),
        ("number", ".75"),
        ("identifier", "alpha"),
        ("variable", "@cost"),
    ]


@pytest.mark.parametrize(
    ("source", "expected_kind"),
    [
        (b"#" + b"x" * (1024 * 1024 - 1), "comment"),
        (b" " * (1024 * 1024), "whitespace"),
        (b'"' + b"x" * (1024 * 1024 - 2) + b'"', "string"),
    ],
)
def test_large_single_token_inputs_do_not_need_per_character_position_objects(
    source: bytes,
    expected_kind: str,
) -> None:
    result = lex_bytes(source, max_bytes=len(source), max_tokens=2)

    assert result.ok
    assert len(result.tokens) == 1
    assert result.tokens[0].kind == expected_kind
    assert result.tokens[0].span.byte_end == len(source)


def test_large_comment_peak_python_allocation_is_bounded() -> None:
    source = b"#" + b"x" * (1024 * 1024 - 1)

    tracemalloc.start()
    try:
        result = lex_bytes(source, max_bytes=len(source), max_tokens=2)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()

    assert result.ok
    assert peak < 24 * 1024 * 1024


def test_input_byte_limit_stops_before_utf8_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = b"x" * 65

    def unexpected_validation(_: bytes) -> None:
        raise AssertionError("validation must not run after byte-budget rejection")

    monkeypatch.setattr(lexer_module, "_validate_utf8", unexpected_validation)

    result = lex_bytes(source, max_bytes=64, max_tokens=10)

    assert not result.ok
    assert result.tokens == ()
    assert [item.code for item in result.diagnostics] == ["LIMIT_EXCEEDED"]


def test_input_byte_limit_accepts_exact_boundary() -> None:
    source = b"#" + b"x" * 63

    result = lex_bytes(source, max_bytes=64, max_tokens=2)

    assert result.ok
    assert len(result.tokens) == 1


def test_token_limit_stops_before_allocating_the_next_token(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    source = b"{}" * (512 * 1024)
    real_make_token = lexer_module._make_token
    created = 0

    def counting_make_token(*args, **kwargs):
        nonlocal created
        created += 1
        return real_make_token(*args, **kwargs)

    monkeypatch.setattr(lexer_module, "_make_token", counting_make_token)

    result = lex_bytes(source, max_bytes=len(source), max_tokens=64)

    assert not result.ok
    assert len(result.tokens) == 64
    assert created == 64
    assert [item.code for item in result.diagnostics] == ["LIMIT_EXCEEDED"]
    assert result.diagnostics[0].span.byte_start == 64


def test_token_limit_accepts_exact_boundary() -> None:
    source = b"{}{}"

    result = lex_bytes(source, max_bytes=len(source), max_tokens=4)

    assert result.ok
    assert len(result.tokens) == 4


@pytest.mark.parametrize(
    ("max_bytes", "max_tokens", "error_type"),
    [
        (0, 1, ValueError),
        (1, 0, ValueError),
        (True, 1, TypeError),
        (1, False, TypeError),
    ],
)
def test_lexer_limits_require_positive_integers(
    max_bytes: int,
    max_tokens: int,
    error_type: type[Exception],
) -> None:
    with pytest.raises(error_type):
        lex_bytes(b"x", max_bytes=max_bytes, max_tokens=max_tokens)
