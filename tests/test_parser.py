from __future__ import annotations

from pathlib import Path

import pytest

from stellaris_supporter.parsing.parser import (
    BlockNode,
    PairNode,
    ScalarNode,
    UnknownNode,
    parse_bytes,
)

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "corpus"


def _walk(items):
    for item in items:
        yield item
        if isinstance(item, PairNode) and item.value is not None:
            yield item.value
            if isinstance(item.value, BlockNode):
                yield from _walk(item.value.items)
        elif isinstance(item, BlockNode):
            yield from _walk(item.items)


def test_ordered_ast_preserves_duplicate_assignments_and_mixed_block() -> None:
    source = (
        FIXTURES / "common" / "technology" / "01_demo_collision.txt"
    ).read_bytes()

    result = parse_bytes(source)

    assert result.ok
    top_pairs = [item for item in result.document.items if isinstance(item, PairNode)]
    duplicate = next(item for item in top_pairs if item.key_text == "demo_duplicate_fields")
    assert isinstance(duplicate.value, BlockNode)

    fields = duplicate.value.items
    assert [item.key_text for item in fields if isinstance(item, PairNode)] == [
        "value",
        "value",
        "mixed",
    ]

    first, second, mixed = [item for item in fields if isinstance(item, PairNode)]
    assert isinstance(first.value, ScalarNode)
    assert isinstance(second.value, ScalarNode)
    assert first.value.text == "first"
    assert second.value.text == "second"

    assert isinstance(mixed.value, BlockNode)
    assert len(mixed.value.items) == 3
    assert isinstance(mixed.value.items[0], ScalarNode)
    assert isinstance(mixed.value.items[1], ScalarNode)
    assert isinstance(mixed.value.items[2], PairNode)
    assert mixed.value.items[0].text == "alpha"
    assert mixed.value.items[1].text == "beta"
    assert mixed.value.items[2].key_text == "key"
    assert isinstance(mixed.value.items[2].value, ScalarNode)
    assert mixed.value.items[2].value.text == "gamma"

    assert first.raw_bytes(source) == b"value = first"
    assert second.raw_bytes(source) == b"value = second"
    assert mixed.raw_bytes(source) == b"mixed = { alpha beta key = gamma }"


def test_unknown_operator_is_preserved_without_invented_pair_semantics() -> None:
    source = (FIXTURES / "malformed" / "unsupported_operator.txt").read_bytes()

    result = parse_bytes(source)

    assert not result.ok
    assert [item.code for item in result.diagnostics] == ["PARSE_UNKNOWN_SYNTAX"]
    unknown = next(item for item in _walk(result.document.items) if isinstance(item, UnknownNode))
    assert unknown.raw_bytes(source) == b"mystery ^= 42"
    assert [token.text for token in unknown.tokens] == ["mystery", "^", "=", "42"]

    pairs = [item for item in _walk(result.document.items) if isinstance(item, PairNode)]
    assert not any(item.key_text in {"mystery", "^"} for item in pairs)


def test_unclosed_block_is_explicit_error_with_partial_ast_preserved() -> None:
    source = (FIXTURES / "malformed" / "unclosed_block.txt").read_bytes()

    result = parse_bytes(source)

    assert not result.ok
    assert "PARSE_UNCLOSED_BLOCK" in [item.code for item in result.diagnostics]
    root_pair = next(
        item
        for item in result.document.items
        if isinstance(item, PairNode) and item.key_text == "demo_unclosed_block"
    )
    assert isinstance(root_pair.value, BlockNode)
    assert root_pair.value.closed is False
    assert root_pair.value.raw_bytes(source).startswith(b"{")
    assert root_pair.value.raw_bytes(source).endswith(b"}")


def test_depth_limit_stops_recursive_ast_growth_but_preserves_raw_region() -> None:
    source = b"a = {" * 20 + b"x = 1" + b"}" * 20

    result = parse_bytes(source, max_depth=4)

    assert not result.ok
    assert [item.code for item in result.diagnostics] == ["PARSE_DEPTH_LIMIT"]
    unknown = next(item for item in _walk(result.document.items) if isinstance(item, UnknownNode))
    assert unknown.raw_bytes(source).startswith(b"{")
    assert unknown.raw_bytes(source).endswith(b"}")
    assert result.node_count < 20


def test_node_limit_stops_before_unbounded_ast_allocation() -> None:
    source = b"item " * 100

    result = parse_bytes(source, max_nodes=10)

    assert not result.ok
    assert result.node_count == 10
    assert [item.code for item in result.diagnostics] == ["PARSE_NODE_LIMIT"]
    assert len(result.document.items) == 10


def test_lexer_error_is_carried_into_parse_result() -> None:
    source = (FIXTURES / "encoding" / "invalid_utf8.txt").read_bytes()

    result = parse_bytes(source)

    assert not result.ok
    assert result.document.items == ()
    assert len(result.diagnostics) == 1
    assert result.diagnostics[0].code == "ENCODING_ERROR"
    assert result.diagnostics[0].origin == "lexer"


@pytest.mark.parametrize(
    ("name", "value", "error_type"),
    [
        ("max_depth", 0, ValueError),
        ("max_depth", 257, ValueError),
        ("max_nodes", 0, ValueError),
        ("max_diagnostics", False, TypeError),
    ],
)
def test_parser_limits_are_explicit(name: str, value: object, error_type: type[Exception]) -> None:
    kwargs = {name: value}
    with pytest.raises(error_type):
        parse_bytes(b"x", **kwargs)
