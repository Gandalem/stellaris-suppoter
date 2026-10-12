"""Authored synthetic TASK-014 foundation acceptance and fail-closed regressions."""

import dataclasses
import hashlib

import pytest

from stellaris_supporter.domain.generic import (
    DOMAIN_REGISTRY,
    adapt_domain,
    find_domain_collisions,
    verify_domain_candidate,
)
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.parsing import parse_bytes


def case(kind, body, *, snapshot="A", path=None):
    raw = body.encode("utf-8")
    prefix = DOMAIN_REGISTRY[kind].path_prefix
    ctx = SourceContext(
        snapshot, "synthetic", "authored",
        path or prefix + "sample.txt", hashlib.sha256(raw).hexdigest(),
    )
    result = adapt_domain(parse_bytes(raw), raw, ctx, kind)
    return raw, ctx, result


@pytest.mark.parametrize(("kind", "source", "game_id"), [
    ("component_template", 'component_template = { key = "laser_x" cost = { alloys = 5 } allow = { flag = yes } }', "laser_x"),
    ("building", "building_x = { cost = { minerals = @dynamic } upkeep = { energy = 2 } potential = { flag = yes } }", "building_x"),
    ("district", "district_x = { cost = 100 allow = { flag = yes } }", "district_x"),
    ("pop_job", "job_x = { produces = { unity = 1 } possible = { flag = yes } }", "job_x"),
])
def test_registered_domains_extract_exact_raw_fields(kind, source, game_id):
    raw, ctx, result = case(kind, source)
    assert result.ok and result.complete and len(result.candidates) == 1
    c = result.candidates[0]
    assert (c.game_id, c.kind, c.resolution) == (game_id, kind, "raw_definition")
    assert c.id_source_ref.raw_bytes(raw).decode("utf-8").strip('"') == game_id
    assert c.source_ref.raw_bytes(raw) == raw
    assert len(c.conditions) == 1
    assert all(f.source_ref.raw_bytes(raw).startswith(f.name.encode()) for f in c.fields)
    assert verify_domain_candidate(c, raw, ctx)


def test_occurrence_order_and_cross_file_collision_without_overwrite():
    src = "building_x = { cost = 1 cost = 2 }\nbuilding_x = { cost = 3 }"
    raw, ctx, r = case("building", src)
    assert [c.definition_occurrence for c in r.candidates] == [1, 2]
    assert [f.occurrence for f in r.candidates[0].fields] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in r.candidates)
    raw2, ctx2, other = case("building", "building_x = { cost = 7 }", path="common/buildings/other.txt")
    conflicts = find_domain_collisions((*r.candidates, *other.candidates))
    assert len(conflicts) == 1 and len(conflicts[0].definition_source_refs) == 3
    assert all(verify_domain_candidate(c, raw, ctx) for c in r.candidates)
    assert verify_domain_candidate(other.candidates[0], raw2, ctx2)


@pytest.mark.parametrize("source", [
    'component_template = { key = @dynamic cost = 1 }',
    'component_template = { cost = 1 }',
    'component_template = { key = id_a key = id_b }',
])
def test_component_id_is_never_inferred(source):
    _, _, result = case("component_template", source)
    assert result.candidates[0].game_id is None
    assert result.candidates[0].resolution == "partial"


def test_non_registered_top_level_is_preserved_and_diagnosed():
    raw, _, result = case("component_template", "unexpected = { key = x }")
    assert len(result.candidates) == 0
    assert len(result.unhandled) == 1
    assert result.unhandled[0].raw_bytes() == raw
    assert not result.complete


def test_same_identifier_different_domains_remains_distinct():
    _, _, building = case("building", "same = { cost = 1 }")
    _, _, district = case("district", "same = { cost = 2 }")
    assert not find_domain_collisions((*building.candidates, *district.candidates))


def test_metadata_and_ast_tampering_is_rejected():
    raw, ctx, result = case("building", "building_a = { cost = 1 }")
    c = result.candidates[0]
    assert not verify_domain_candidate(dataclasses.replace(c, game_id="building_b"), raw, ctx)
    assert not verify_domain_candidate(dataclasses.replace(c, definition_occurrence=2), raw, ctx)
    assert not verify_domain_candidate(dataclasses.replace(c, source_ref=dataclasses.replace(c.source_ref, byte_end=3)), raw, ctx)
    with pytest.raises(ValueError):
        case("building", "building_a = { cost = 1 }", path="common/districts/fake.txt")
    bad = dataclasses.replace(ctx, file_sha256="0" * 64)
    with pytest.raises(ValueError):
        adapt_domain(parse_bytes(raw), raw, bad, "building")


def test_snapshot_isolation_and_parser_resource_stop():
    _, _, a = case("building", "one = {}")
    _, _, b = case("building", "one = {}", snapshot="B")
    with pytest.raises(ValueError):
        find_domain_collisions((*a.candidates, *b.candidates))
    source = ("one = { x = { y = { z = 1 } } }").encode()
    ctx = SourceContext("A", "synthetic", "authored", "common/buildings/sample.txt", hashlib.sha256(source).hexdigest())
    result = adapt_domain(parse_bytes(source, max_depth=1), source, ctx, "building")
    assert result.blocked and not result.candidates
    assert any(d.code == "PARSE_DEPTH_LIMIT" for d in result.diagnostics)


def test_crlf_unicode_spans_and_partial_unknown():
    raw, _, r = case("building", "\ufeffbuilding_ko = {\r\n description = \"한글 # {}\"\r\n unknown ^ = 2\r\n }")
    assert not r.complete
    c = r.candidates[0]
    assert c.fields[0].raw_value == '"한글 # {}"'
    assert c.source_ref.raw_bytes(raw).startswith(b"building_ko")
    assert any(d.code in {"PARSE_UNKNOWN_SYNTAX", "DOMAIN_UNKNOWN_STRUCTURE"} for d in r.diagnostics)


def test_raw_serialisation_is_bounded():
    _, _, result = case("building", "one = { cost = { energy = 10 } }")
    with pytest.raises(ValueError):
        result.to_dict(include_raw=True, max_raw_bytes=1)
    assert result.to_dict(include_raw=False)["candidates"][0]["kind"] == "building"
