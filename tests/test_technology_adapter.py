from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pytest

from stellaris_supporter.domain import (
    AdapterSerializationLimitError,
    SourceContext,
    adapt_technologies,
)
from stellaris_supporter.domain.technology import RawNodeRef
from stellaris_supporter.parsing import parse_bytes

FIXTURES = Path(__file__).parent / "fixtures" / "synthetic" / "corpus"
NORMAL_PATH = Path("common/technology/00_demo_normal.txt")
COLLISION_PATH = Path("common/technology/01_demo_collision.txt")


def _context(relative_path: Path, source: bytes) -> SourceContext:
    return SourceContext(
        snapshot_id="synthetic-task-008",
        source_kind="synthetic",
        source_id="synthetic-corpus",
        relative_path=relative_path.as_posix(),
        file_sha256=hashlib.sha256(source).hexdigest(),
    )


def _inline_context(source: bytes) -> SourceContext:
    return _context(Path("common/technology/inline.txt"), source)


def _adapt(relative_path: Path):
    source = (FIXTURES / relative_path).read_bytes()
    parsed = parse_bytes(source)
    assert parsed.ok
    result = adapt_technologies(parsed, source, _context(relative_path, source))
    return source, result


def _adapt_inline(source: bytes, **parse_kwargs):
    parsed = parse_bytes(source, **parse_kwargs)
    result = adapt_technologies(parsed, source, _inline_context(source))
    return parsed, result


def _walk_raw(nodes: tuple[RawNodeRef, ...]):
    for node in nodes:
        yield node
        yield from _walk_raw(node.children)


def test_demo_technology_fields_conditions_and_prerequisites_are_preserved() -> None:
    source, result = _adapt(NORMAL_PATH)

    assert result.ok
    assert result.complete
    assert [item.game_id for item in result.candidates] == [
        "demo_echo_theory",
        "demo_prism_lattice",
        "demo_english_only",
        "demo_missing_loc",
    ]

    candidate = next(
        item for item in result.candidates if item.game_id == "demo_prism_lattice"
    )
    assert candidate.resolution == "raw_definition"
    assert [field.name for field in candidate.fields] == [
        "area",
        "tier",
        "cost",
        "prerequisites",
        "potential",
        "weight",
    ]
    assert [field.occurrence for field in candidate.fields] == [1, 1, 1, 1, 1, 1]

    cost = next(field for field in candidate.fields if field.name == "cost")
    assert cost.raw_value == "@demo_cost"
    assert cost.value is not None
    assert cost.value.kind == "scalar"

    assert len(candidate.prerequisites) == 1
    prerequisite = candidate.prerequisites[0]
    assert prerequisite.target_game_id == "demo_echo_theory"
    assert prerequisite.raw_value == '"demo_echo_theory"'
    assert prerequisite.source_ref.raw_bytes(source) == b'"demo_echo_theory"'

    potential = next(field for field in candidate.fields if field.name == "potential")
    assert potential.value is not None
    assert potential.value.kind == "block"
    assert len(potential.value.children) == 1
    condition = potential.value.children[0]
    assert condition.kind == "pair"
    assert condition.key == "has_country_flag"
    assert condition.operator == "="
    assert condition.children[0].raw == "demo_prism_ready"

    weight = next(field for field in candidate.fields if field.name == "weight")
    assert weight.value is not None
    assert [item.key for item in weight.value.children] == ["base", "modifier"]
    modifier = weight.value.children[1]
    assert modifier.children[0].kind == "block"
    assert [item.key for item in modifier.children[0].children] == [
        "factor",
        "has_country_flag",
    ]

    assert candidate.source_ref.relative_path == NORMAL_PATH.as_posix()
    assert candidate.source_ref.raw_bytes(source).startswith(b"demo_prism_lattice = {")
    assert candidate.source_ref.raw_bytes(source).endswith(b"}")


def test_duplicate_fields_and_mixed_items_keep_order_and_occurrence() -> None:
    source, result = _adapt(COLLISION_PATH)

    candidate = next(
        item for item in result.candidates if item.game_id == "demo_duplicate_fields"
    )
    assert [field.name for field in candidate.fields] == ["value", "value", "mixed"]
    assert [field.occurrence for field in candidate.fields] == [1, 2, 1]
    assert [field.raw_value for field in candidate.fields[:2]] == ["first", "second"]

    mixed = candidate.items[2]
    assert mixed.kind == "pair"
    assert mixed.key == "mixed"
    block = mixed.children[0]
    assert [item.kind for item in block.children] == ["scalar", "scalar", "pair"]
    assert [item.raw for item in block.children[:2]] == ["alpha", "beta"]
    assert block.children[2].key == "key"
    assert block.children[2].children[0].raw == "gamma"

    assert candidate.source_ref.raw_bytes(source).startswith(b"demo_duplicate_fields")


def test_same_game_id_from_different_files_is_not_overwritten() -> None:
    _, normal = _adapt(NORMAL_PATH)
    _, collision = _adapt(COLLISION_PATH)

    occurrences = [
        item
        for result in (normal, collision)
        for item in result.candidates
        if item.game_id == "demo_prism_lattice"
    ]

    assert len(occurrences) == 2
    assert [item.source_ref.relative_path for item in occurrences] == [
        NORMAL_PATH.as_posix(),
        COLLISION_PATH.as_posix(),
    ]
    normal_tier = next(field for field in occurrences[0].fields if field.name == "tier")
    collision_tier = next(
        field for field in occurrences[1].fields if field.name == "tier"
    )
    assert normal_tier.raw_value == "2"
    assert collision_tier.raw_value == "9"


def test_unknown_technology_item_is_preserved_and_diagnosed() -> None:
    source = b"demo = { mystery ^= 42 normal = 1 }"
    parsed, result = _adapt_inline(source)
    assert not parsed.ok

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.resolution == "partial"
    assert [item.kind for item in candidate.items] == ["unknown", "pair"]
    assert candidate.items[0].raw == "mystery ^= 42"
    assert candidate.items[1].key == "normal"
    assert "PARSE_UNKNOWN_SYNTAX" in [item.code for item in candidate.diagnostics]
    assert "ADAPTER_UNKNOWN_ITEM" in [item.code for item in candidate.diagnostics]
    assert not result.ok
    assert not result.complete


def test_source_refs_match_original_byte_ranges() -> None:
    source, result = _adapt(NORMAL_PATH)

    for candidate in result.candidates:
        assert candidate.source_ref.file_sha256 == hashlib.sha256(source).hexdigest()
        assert candidate.source_ref.raw_bytes(source).decode("utf-8").startswith(
            candidate.game_id
        )
        for field in candidate.fields:
            raw = field.source_ref.raw_bytes(source).decode("utf-8")
            assert raw.startswith(field.name)
            if field.value is not None:
                assert field.value.source_ref.raw_bytes(source).decode("utf-8") == (
                    field.value.raw
                )


@pytest.mark.parametrize(
    ("source", "code"),
    [
        (b"demo = { cost = 1", "PARSE_UNCLOSED_BLOCK"),
        (b"demo = { cost = }", "PARSE_MISSING_VALUE"),
        (
            b"demo = { potential = { mystery ^= 42 } }",
            "PARSE_UNKNOWN_SYNTAX",
        ),
    ],
)
def test_parser_errors_are_not_silenced_by_adapter(source: bytes, code: str) -> None:
    parsed, result = _adapt_inline(source)

    assert not parsed.ok
    assert not result.ok
    assert not result.complete
    assert code in [item.code for item in result.diagnostics]
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.resolution == "partial"
    assert code in [item.code for item in candidate.diagnostics]


def test_encoding_error_is_distinct_from_normal_empty_file() -> None:
    bad_source = (FIXTURES / "encoding" / "invalid_utf8.txt").read_bytes()
    bad_parsed = parse_bytes(bad_source)
    bad_result = adapt_technologies(
        bad_parsed,
        bad_source,
        _context(Path("encoding/invalid_utf8.txt"), bad_source),
    )

    empty_parsed, empty_result = _adapt_inline(b"")

    assert not bad_result.ok
    assert not bad_result.complete
    assert bad_result.candidates == ()
    assert [item.code for item in bad_result.diagnostics] == ["ENCODING_ERROR"]
    assert bad_result.diagnostics[0].origin == "lexer"

    assert empty_parsed.ok
    assert empty_result.ok
    assert empty_result.complete
    assert empty_result.candidates == ()
    assert empty_result.diagnostics == ()


def test_lexer_limit_is_propagated_instead_of_returning_silent_partial_success() -> None:
    source = b"demo = { cost = 1 } after = { cost = 2 }"
    parsed, result = _adapt_inline(source, max_tokens=4)

    assert not parsed.ok
    assert not result.ok
    assert not result.complete
    assert "LIMIT_EXCEEDED" in [item.code for item in result.diagnostics]


@pytest.mark.parametrize("operator", [b">", b"<", b">=", b"<="])
def test_prerequisites_require_assignment_operator(operator: bytes) -> None:
    source = b'demo = { prerequisites ' + operator + b' { "other" } }'
    parsed, result = _adapt_inline(source)

    assert parsed.ok
    candidate = result.candidates[0]
    assert candidate.prerequisites == ()
    assert candidate.resolution == "partial"
    assert "ADAPTER_UNSUPPORTED_PREREQUISITES_OPERATOR" in [
        item.code for item in candidate.diagnostics
    ]
    assert result.ok
    assert not result.complete


@pytest.mark.parametrize(
    "value",
    [
        b"@ref",
        b'""',
        b"123",
    ],
    ids=["variable", "empty-string", "number"],
)
def test_unresolved_prerequisite_values_are_not_promoted_to_game_ids(
    value: bytes,
) -> None:
    source = b"demo = { prerequisites = { " + value + b" } }"
    parsed, result = _adapt_inline(source)

    assert parsed.ok
    candidate = result.candidates[0]
    assert candidate.prerequisites == ()
    assert candidate.resolution == "partial"
    assert "ADAPTER_UNRESOLVED_PREREQUISITE" in [
        item.code for item in candidate.diagnostics
    ]


def test_supported_prerequisite_literals_preserve_order_and_raw_source() -> None:
    source = b'demo = { prerequisites = { "quoted_id" bare_id } }'
    parsed, result = _adapt_inline(source)

    assert parsed.ok
    candidate = result.candidates[0]
    assert [item.target_game_id for item in candidate.prerequisites] == [
        "quoted_id",
        "bare_id",
    ]
    assert [item.raw_value for item in candidate.prerequisites] == [
        '"quoted_id"',
        "bare_id",
    ]
    assert candidate.resolution == "raw_definition"


def test_raw_tree_reuses_source_and_field_value_nodes_without_retained_subtree_strings() -> None:
    depth = 80
    payload = b'"' + (b"x" * (256 * 1024)) + b'"'
    source = (
        b"demo = { "
        + (b"nested = { " * depth)
        + b"value = "
        + payload
        + (b" }" * depth)
        + b" }"
    )
    parsed, result = _adapt_inline(source, max_depth=128)

    assert parsed.ok
    assert result.ok
    candidate = result.candidates[0]
    raw_nodes = tuple(_walk_raw(candidate.items))

    assert raw_nodes
    assert all(node._source is source for node in raw_nodes)
    assert "raw" not in RawNodeRef.__slots__

    first_field = candidate.fields[0]
    assert first_field.value is candidate.items[0].children[0]

    serialized = json.dumps(result.to_dict())
    assert len(serialized.encode("utf-8")) < len(source)

    with pytest.raises(AdapterSerializationLimitError):
        result.to_dict(include_raw=True, max_raw_bytes=1024)


def test_raw_output_budget_allows_small_explicit_materialization() -> None:
    source = b'demo = { cost = 1 prerequisites = { "other" } }'
    _, result = _adapt_inline(source)

    serialized = result.to_dict(include_raw=True, max_raw_bytes=4096)
    raw_nodes = serialized["candidates"][0]["items"]

    assert raw_nodes[0]["raw"] == "cost = 1"
    assert raw_nodes[1]["raw"].startswith("prerequisites =")
