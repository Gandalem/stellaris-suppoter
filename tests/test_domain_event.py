"""TASK-014 Phase C1 event/namespace rules (authored synthetic; NOT game grammar)."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain import generic as domain
from stellaris_supporter.domain.generic import (
    adapt_domain,
    find_domain_collisions,
    resolve_domain_name,
    verify_domain_candidate,
)
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.localisation import build_localisation_catalog, parse_localisation
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.parsing.parser import DEFAULT_PARSER_MAX_DIAGNOSTICS

LIMIT = DEFAULT_PARSER_MAX_DIAGNOSTICS
KINDS_BEFORE = (
    "component_template", "building", "district", "pop_job", "trait",
    "government", "civic", "origin", "tradition", "ascension_perk",
)


def event(
    game_id: str = "authored.1", *,
    event_type: str = "country_event",
    body: str = "",
    title: str = "authored_title",
) -> str:
    return (
        f"{event_type} = {{ id = {game_id} title = {title} "
        f"trigger = {{ has_country_flag = example }} "
        f"immediate = {{ country_event = {{ id = authored.2 }} }} "
        f"{body} }}"
    )


def context(raw: bytes, *, snapshot: str = "A", file: str = "wave4.txt"):
    return SourceContext(
        snapshot, "synthetic", "authored", "events/" + file,
        hashlib.sha256(raw).hexdigest(),
    )


def adapted(text: str, *, snapshot: str = "A", file: str = "wave4.txt"):
    raw = text.encode()
    ctx = context(raw, snapshot=snapshot, file=file)
    result = adapt_domain(parse_bytes(raw), raw, ctx, "event")
    return raw, ctx, result


def loc(raw: bytes, language: str = "english", *, snapshot: str = "A"):
    return parse_localisation(raw, SourceContext(
        snapshot, "synthetic", "authored",
        f"localisation/{language}/wave4_l_{language}.yml",
        hashlib.sha256(raw).hexdigest(),
    ))


def codes(result):
    return [d.code for d in result.diagnostics]


def test_event_opt_in_registry_and_previous_ten_preserved():
    assert all(k in domain.DOMAIN_REGISTRY for k in KINDS_BEFORE)
    spec = domain.DOMAIN_REGISTRY["event"]
    assert spec.path_prefix == "events/"
    assert spec.id_rule == "literal_id_field"
    assert spec.localisation_rule == "title_field"


@pytest.mark.parametrize("event_type", ["country_event", "planet_event"])
def test_event_namespace_type_id_source_and_nested_raw_not_new_definition(event_type):
    raw, ctx, r = adapted("namespace = authored\n" + event(
        event_type=event_type, body="cost = 100 cost = 200"
    ))
    assert r.ok and r.complete and not r.blocked
    assert len(r.candidates) == 1 and not r.unhandled
    c = r.candidates[0]
    assert (c.kind, c.game_id, c.localisation_key) == (
        "event", "authored.1", "authored_title"
    )
    assert c.source_ref.raw_bytes(raw).startswith(event_type.encode() + b" =")
    assert c.id_source_ref.raw_bytes(raw) == b"authored.1"
    assert c.source_ref.relative_path == ctx.relative_path
    assert [f.raw_value for f in c.fields if f.name == "cost"] == ["100", "200"]
    assert [f.occurrence for f in c.fields if f.name == "cost"] == [1, 2]
    assert [f.name for f in c.conditions] == ["trigger"]
    assert "{ id = authored.2 }" in next(
        f.raw_value for f in c.fields if f.name == "immediate"
    )
    assert any(
        d.code == "DOMAIN_EVENT_NAMESPACE" and
        d.source_ref.raw_bytes(raw) == b"namespace = authored" for d in r.diagnostics
    )
    assert len([d for d in r.diagnostics if d.code == "DOMAIN_EVENT_NAMESPACE"]) == 1
    assert verify_domain_candidate(c, raw, ctx)


def test_event_missing_namespace_is_explicit_partial_cross_file_not_guessed():
    raw, ctx, r = adapted(event())
    assert len(r.candidates) == 1 and not r.complete
    c = r.candidates[0]
    assert c.game_id == "authored.1" and c.resolution == "partial"
    assert "DOMAIN_EVENT_NAMESPACE_UNVERIFIED" in codes(r)
    assert verify_domain_candidate(c, raw, ctx)
    # Another file may declare the namespace, but this single-file adapter
    # must not silently assume that declaration applies.
    other, _, declared = adapted("namespace = authored", file="other.txt")
    assert other and not declared.candidates


def test_event_identical_namespace_declarations_keep_both_source_refs():
    raw, _, r = adapted("namespace = authored\nnamespace = authored\n" + event())
    assert r.complete and r.candidates[0].resolution == "raw_definition"
    declarations = [d for d in r.diagnostics if d.code == "DOMAIN_EVENT_NAMESPACE"]
    assert len(declarations) == 2
    assert declarations[0].source_ref != declarations[1].source_ref
    assert all(d.source_ref.raw_bytes(raw) == b"namespace = authored"
               for d in declarations)


@pytest.mark.parametrize("prefix", ["other.1", "authored", "@dynamic"])
def test_event_id_namespace_mismatch_or_nonqualified_is_partial(prefix):
    _, _, r = adapted("namespace = authored\n" + event(prefix))
    assert not r.complete and r.candidates[0].resolution == "partial"
    assert any(d.code in {
        "DOMAIN_EVENT_NAMESPACE_MISMATCH", "DOMAIN_UNRESOLVED_ID",
        "DOMAIN_EVENT_UNQUALIFIED_ID",
    } for d in r.diagnostics)


def test_event_conflicting_or_invalid_namespace_never_declares_verified_id():
    for declarations in (
        "namespace = authored\nnamespace = other\n",
        "namespace > authored\n",
        "namespace = @dynamic\n",
        "namespace = { foo = bar }\n",
    ):
        _, _, r = adapted(declarations + event())
        assert not r.complete and r.candidates[0].resolution == "partial"
        assert any(x in codes(r) for x in (
            "DOMAIN_EVENT_NAMESPACE_CONFLICT",
            "DOMAIN_EVENT_NAMESPACE_INVALID",
            "DOMAIN_EVENT_NAMESPACE_UNVERIFIED",
        ))


@pytest.mark.parametrize("event_type", ["fleet_event", "event", "unknown_event"])
def test_event_unsupported_event_type_is_raw_unknown_not_candidate(event_type):
    raw, _, r = adapted("namespace = authored\n" + event(event_type=event_type))
    assert not r.candidates and r.unhandled and not r.complete
    assert any(d.code == "DOMAIN_UNSUPPORTED_TOP_LEVEL" for d in r.diagnostics)
    assert all(u.source_ref.raw_bytes(raw) for u in r.unhandled)


@pytest.mark.parametrize("fragment", (
    "", "id = @dynamic", "id = authored.1 id = authored.2",
    "id > authored.1", "id = { dynamic = yes }",
))
def test_event_id_missing_dynamic_or_duplicated_is_partial(fragment):
    _, _, r = adapted(
        "namespace = authored\n" + event().replace("id = authored.1", fragment, 1)
    )
    assert len(r.candidates) == 1 and not r.complete
    assert r.candidates[0].game_id is None
    assert "DOMAIN_UNRESOLVED_ID" in codes(r)


@pytest.mark.parametrize("fragment", (
    "", "title = @dynamic", "title = a title = b", "title > authored_title",
))
def test_event_title_must_be_unique_static_key(fragment):
    raw, ctx, r = adapted(
        "namespace = authored\n"
        + event().replace("title = authored_title", fragment, 1)
    )
    c = r.candidates[0]
    assert c.game_id == "authored.1" and c.localisation_key is None
    assert c.resolution == "partial" and not r.complete
    assert "DOMAIN_UNRESOLVED_LOCALISATION_KEY" in codes(r)
    assert verify_domain_candidate(c, raw, ctx)
    with pytest.raises(ValueError, match="localisation key"):
        resolve_domain_name(c, build_localisation_catalog(()))


def test_event_duplicate_id_across_types_and_same_file_retains_all():
    raw, ctx, r = adapted(
        "namespace = authored\n" + event()
        + "\n" + event(event_type="planet_event", body="cost = 999")
    )
    assert [c.game_id for c in r.candidates] == ["authored.1", "authored.1"]
    assert [c.definition_occurrence for c in r.candidates] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in r.candidates)
    assert "DOMAIN_DUPLICATE_ID" in codes(r)
    assert all(verify_domain_candidate(c, raw, ctx) for c in r.candidates)


def test_event_cross_file_collision_snapshot_isolation_and_kind_separation():
    raw, ctx, left = adapted("namespace = authored\n" + event(), file="one.txt")
    _, _, right = adapted("namespace = authored\n" + event(), file="two.txt")
    collision = find_domain_collisions((*left.candidates, *right.candidates))
    assert len(collision) == 1
    assert len(collision[0].definition_source_refs) == 2
    assert not verify_domain_candidate(left.candidates[0], raw, replace(
        ctx, relative_path="events/two.txt"
    ))
    assert not verify_domain_candidate(left.candidates[0], raw, replace(
        ctx, snapshot_id="B"
    ))
    _, _, foreign = adapted("namespace = authored\n" + event(), snapshot="B")
    with pytest.raises(ValueError, match="snapshot"):
        find_domain_collisions((*left.candidates, *foreign.candidates))


def test_event_unknown_operator_unclosed_fake_comment_and_effect_raw():
    text = (
        "namespace = authored\n" + event(
            body='cost >= 44 unknown ^ = 3 text = "fake_event = { }" '
            "if = { limit = { has_flag = yes } add_resource = @dynamic }"
        )
    )
    raw, _, r = adapted(text + "\n# planet_event = { id = fake.2 }")
    assert len(r.candidates) == 1 and not r.complete
    assert any(d.code in {
        "PARSE_UNKNOWN_SYNTAX", "DOMAIN_UNKNOWN_STRUCTURE"
    } for d in r.diagnostics)
    assert "DOMAIN_UNSUPPORTED_OPERATOR" in codes(r)
    assert b"@dynamic" in raw
    assert "add_resource = @dynamic" in next(
        f.raw_value for f in r.candidates[0].fields if f.name == "if"
    )
    _, _, unclosed = adapted("namespace = authored\n" + event()[:-2])
    assert not unclosed.complete and "PARSE_UNCLOSED_BLOCK" in codes(unclosed)


def test_event_r1_independent_field_condition_child_and_borrowed_ref_rejected():
    raw, ctx, r = adapted(
        "namespace = authored\n" + event(
            body="cost = 100 cost = 100 trigger = { flag = yes }"
        )
    )
    c = r.candidates[0]
    cost = [f for f in c.fields if f.name == "cost"][0]
    assert cost.value is not None
    bad_bytes = raw.replace(b"100", b"999")
    forged = replace(c, fields=tuple(
        replace(f, value=replace(f.value, _source=bad_bytes))
        if f is cost else f for f in c.fields
    ))
    assert not verify_domain_candidate(forged, raw, ctx)
    cond = c.conditions[0]
    assert cond.value is not None and cond.value.children
    bad_cond = replace(cond, value=replace(cond.value, _source=raw.replace(
        b"example", b"altered"
    )))
    assert not verify_domain_candidate(replace(c, conditions=(bad_cond,)), raw, ctx)
    nested = replace(cond.value, children=(
        replace(cond.value.children[0], _source=raw.replace(
            b"example", b"altered"
        )),
    ))
    assert not verify_domain_candidate(
        replace(c, conditions=(replace(cond, value=nested),)), raw, ctx
    )
    costs = [f for f in c.fields if f.name == "cost"]
    stolen_ref = replace(costs[0], source_ref=costs[1].source_ref)
    borrowed = replace(c, fields=tuple(
        stolen_ref if f is costs[0] else f for f in c.fields
    ))
    assert not verify_domain_candidate(borrowed, raw, ctx)
    assert verify_domain_candidate(c, raw, ctx)


def test_event_r2_canonical_parse_sha_bytes_coordinates_and_hard_stops():
    raw, ctx, r = adapted("namespace = authored\n" + event())
    parsed = parse_bytes(raw)
    bad = (
        parse_bytes(b""),
        replace(parsed, document=replace(parsed.document, items=())),
        replace(parsed, tokens=(replace(
            parsed.tokens[0], span=replace(parsed.tokens[0].span, line_start=99)
        ), *parsed.tokens[1:])),
        replace(parsed, document=replace(parsed.document, items=(
            replace(parsed.document.items[0], span=replace(
                parsed.document.items[0].span, column_start=99
            )), *parsed.document.items[1:]
        ))),
    )
    for foreign in bad:
        with pytest.raises(ValueError):
            adapt_domain(foreign, raw, ctx, "event")
    with pytest.raises(ValueError, match="hash"):
        adapt_domain(parsed, raw, replace(ctx, file_sha256="0" * 64), "event")
    for limited in (
        parse_bytes(raw, max_tokens=2),
        parse_bytes(raw, max_nodes=2),
        parse_bytes(raw, max_depth=1),
    ):
        result = adapt_domain(limited, raw, ctx, "event")
        assert result.blocked and not result.candidates and not result.complete
    assert verify_domain_candidate(r.candidates[0], raw, ctx)
    with patch.object(domain, "parse_bytes", wraps=parse_bytes) as canonical:
        adapt_domain(parsed, raw, ctx, "event")
    assert canonical.call_count == 1


def test_event_bom_crlf_hangul_and_invalid_utf8():
    raw, ctx, r = adapted(
        "\ufeffnamespace = authored\r\n"
        + event(body='description = "한글 # = {}"').replace(
            " trigger =", "\r\n trigger ="
        )
    )
    assert r.complete and len(r.candidates) == 1
    assert r.candidates[0].id_source_ref.raw_bytes(raw) == b"authored.1"
    assert next(
        f.raw_value for f in r.candidates[0].fields if f.name == "description"
    ) == '"한글 # = {}"'
    assert verify_domain_candidate(r.candidates[0], raw, ctx)
    bad = b"\xff"
    with pytest.raises(ValueError):
        adapt_domain(parse_bytes(b""), bad, context(bad), "event")
    blocked = adapt_domain(parse_bytes(bad), bad, context(bad), "event")
    assert blocked.blocked and not blocked.candidates
    with pytest.raises(ValueError):
        r.to_dict(include_raw=True, max_raw_bytes=1)


def test_event_korean_english_fallback_refs_ambiguous_cycles_dynamic_and_budget():
    _, ctx, r = adapted("namespace = authored\n" + event())
    c = r.candidates[0]
    key = c.localisation_key
    assert key == "authored_title" and c.game_id != key
    ko = f'l_korean:\n {key}:0 "한글 $a$"\n a:0 "$b$"\n b:0 "제목"\n'.encode()
    en = f'l_english:\n {key}:0 "English title"\n'.encode()
    dko, den = loc(ko, "korean"), loc(en)
    named = build_localisation_catalog((dko, den))
    kr = resolve_domain_name(c, named, "korean").localisation
    assert kr.display_value == "한글 제목"
    assert kr.source_ref == dko.entries[0].source_ref
    assert len(kr.reference_source_refs) == 2
    assert all(ref.snapshot_id == ctx.snapshot_id for ref in kr.reference_source_refs)
    eng = resolve_domain_name(c, named, "english").localisation
    assert eng.display_value == "English title"
    fallback = resolve_domain_name(
        c, build_localisation_catalog((den,)), "korean"
    ).localisation
    assert fallback.fallback == "english"
    missing = resolve_domain_name(c, build_localisation_catalog(())).localisation
    assert missing.fallback == "id" and missing.display_value == key
    duplicate = f'l_korean:\n {key}:0 "a"\n {key}:0 "b"\n'.encode()
    assert resolve_domain_name(
        c, build_localisation_catalog((loc(duplicate, "korean"),))
    ).localisation.resolution == "ambiguous"
    cyclic = f'l_korean:\n {key}:0 "$a$"\n a:0 "$a$"\n'.encode()
    assert "LOC_CYCLE" in [
        d.code for d in resolve_domain_name(
            c, build_localisation_catalog((loc(cyclic, "korean"),))
        ).localisation.diagnostics
    ]
    dynamic = f'l_english:\n {key}:0 "[Root.GetName] £unity£"\n'.encode()
    catalog = build_localisation_catalog((loc(dynamic),))
    assert resolve_domain_name(c, catalog, "english").localisation.resolution == "partial"
    limited = resolve_domain_name(
        c, catalog, "english", max_scan_bytes=1
    ).localisation
    assert limited.truncated
    with pytest.raises(ValueError, match="snapshot"):
        resolve_domain_name(
            c, build_localisation_catalog((loc(ko, "korean", snapshot="B"),))
        )


@pytest.mark.parametrize("count", (998, 999, 1199))
def test_event_namespace_info_plus_warning_budget_bound(count):
    # One namespace provenance info + one unresolved-title warning per event:
    # 998 -> 999 diagnostics, 999 -> exactly 1000, 1199 -> early stop at 999.
    text = "namespace = authored\n" + "\n".join(
        f"country_event = {{ id = authored.{i} }}" for i in range(count)
    )
    raw, ctx = text.encode(), context(text.encode())
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        r = adapt_domain(parse_bytes(raw), raw, ctx, "event")
    assert make.call_count == min(count, 999)
    assert r.blocked is (count >= 999)
    if count < 999:
        assert len(r.candidates) == count and len(r.diagnostics) == count + 1
        assert not r.complete
    else:
        assert not r.candidates and not r.complete
        assert [d.code for d in r.diagnostics] == ["LIMIT_EXCEEDED"]


def test_event_1200_diagnostic_free_definitions_and_duplicate_occurrence():
    source = "namespace = authored\n" + "\n".join(
        f"country_event = {{ id = authored.{i} title = title_{i} }}"
        for i in range(1200)
    )
    raw, ctx, r = adapted(source)
    assert not r.blocked and r.complete and len(r.candidates) == 1200
    assert verify_domain_candidate(r.candidates[0], raw, ctx)
    assert verify_domain_candidate(r.candidates[-1], raw, ctx)


def test_event_one_candidate_1200_bad_operators_blocks_before_raw_projection():
    source = "namespace = authored\ncountry_event = { id = authored.1 title = title_x " + " ".join(
        f"bad_{i} > yes" for i in range(1200)
    ) + " }"
    raw, ctx = source.encode(), context(source.encode())
    with patch.object(domain, "_raw_node", wraps=domain._raw_node) as raw_node:
        r = adapt_domain(parse_bytes(raw), raw, ctx, "event")
    assert r.blocked and not r.candidates
    assert [d.code for d in r.diagnostics] == ["LIMIT_EXCEEDED"]
    assert raw_node.call_count <= LIMIT


def test_event_parser_and_adapter_diagnostics_share_budget():
    source = "namespace = authored\nbad ^ = 2\n" + "\n".join(
        f"country_event = {{ id = authored.{i} }}"
        for i in range(1200)
    )
    raw, ctx = source.encode(), context(source.encode())
    parsed = parse_bytes(raw)
    assert "PARSE_UNKNOWN_SYNTAX" in [d.code for d in parsed.diagnostics]
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        r = adapt_domain(parsed, raw, ctx, "event")
    assert r.blocked and not r.candidates and not r.complete
    assert make.call_count <= LIMIT - 2


def test_event_namespace_many_declarations_bound_without_candidate_allocation():
    source = "\n".join("namespace = authored" for _ in range(1200))
    raw, ctx = source.encode(), context(source.encode())
    with patch.object(domain, "_make_candidate", wraps=domain._make_candidate) as make:
        r = adapt_domain(parse_bytes(raw), raw, ctx, "event")
    assert r.blocked and not r.candidates
    assert [d.code for d in r.diagnostics] == ["LIMIT_EXCEEDED"]
    assert make.call_count == 0
