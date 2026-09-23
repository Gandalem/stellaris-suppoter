from __future__ import annotations

import hashlib
from pathlib import Path

from stellaris_supporter.domain import SourceContext, adapt_technologies
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


def _adapt(relative_path: Path):
    source = (FIXTURES / relative_path).read_bytes()
    parsed = parse_bytes(source)
    assert parsed.ok
    result = adapt_technologies(parsed.document, source, _context(relative_path, source))
    return source, result


def test_demo_technology_fields_conditions_and_prerequisites_are_preserved() -> None:
    source, result = _adapt(NORMAL_PATH)

    assert result.ok
    assert [item.game_id for item in result.candidates] == [
        "demo_echo_theory",
        "demo_prism_lattice",
        "demo_english_only",
        "demo_missing_loc",
    ]

    candidate = next(
        item for item in result.candidates if item.game_id == "demo_prism_lattice"
    )
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
    parsed = parse_bytes(source)
    assert not parsed.ok

    context = SourceContext(
        snapshot_id="synthetic-task-008",
        source_kind="synthetic",
        source_id="inline",
        relative_path="common/technology/inline.txt",
        file_sha256=hashlib.sha256(source).hexdigest(),
    )
    result = adapt_technologies(parsed.document, source, context)

    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert [item.kind for item in candidate.items] == ["unknown", "pair"]
    assert candidate.items[0].raw == "mystery ^= 42"
    assert candidate.items[1].key == "normal"
    assert [item.code for item in candidate.diagnostics] == ["ADAPTER_UNKNOWN_ITEM"]
    assert candidate.diagnostics[0].source_ref.raw_bytes(source) == b"mystery ^= 42"


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
