"""TASK-014 Phase A authored synthetic grammars; no real-game compatibility claim."""

from __future__ import annotations

import hashlib
from dataclasses import replace
from unittest.mock import patch

import pytest

from stellaris_supporter.domain.generic import (
    DOMAIN_REGISTRY,
    adapt_domain,
    find_domain_collisions,
    resolve_domain_name,
    verify_domain_candidate,
)
from stellaris_supporter.domain.technology import SourceContext
from stellaris_supporter.localisation import build_localisation_catalog, parse_localisation
from stellaris_supporter.parsing import parse_bytes

KINDS = ("trait", "government", "civic", "origin")


def sample(kind: str, *, game_id: str = "shared_x", body: str = "") -> str:
    extra = f" cost = 100 potential = {{ flag = yes }} {body}"
    if kind == "trait":
        return f"{game_id} = {{{extra} }}"
    if kind == "government":
        return f"governments = {{ {game_id} = {{ name = {game_id}_display {extra} }} }}"
    if kind == "civic":
        return f"civic = {{ key = {game_id} name = {game_id}_display {extra} }}"
    if kind == "origin":
        return f"origin = {{ id = {game_id} name = {game_id}_display {extra} }}"
    raise AssertionError("unknown synthetic fixture kind")


def context(kind: str, source: bytes, *, snapshot: str = "A", filename: str = "wave2.txt"):
    return SourceContext(
        snapshot, "synthetic", "authored",
        DOMAIN_REGISTRY[kind].path_prefix + filename,
        hashlib.sha256(source).hexdigest(),
    )


def adapted(kind: str, text: str, *, snapshot: str = "A", filename: str = "wave2.txt"):
    source = text.encode("utf-8")
    ctx = context(kind, source, snapshot=snapshot, filename=filename)
    result = adapt_domain(parse_bytes(source), source, ctx, kind)
    return source, ctx, result


def document(source: bytes, *, language: str = "english", snapshot: str = "A"):
    ctx = SourceContext(
        snapshot, "synthetic", "authored",
        f"localisation/{language}/wave2_l_{language}.yml",
        hashlib.sha256(source).hexdigest(),
    )
    return parse_localisation(source, ctx)


def catalog(*sources: bytes, snapshot="A"):
    languages = ("korean", "english")
    docs = tuple(
        document(source, language=languages[i], snapshot=snapshot)
        for i, source in enumerate(sources)
    )
    return build_localisation_catalog(docs)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_four_distinct_id_grammars_and_source_spans(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    assert result.ok and result.complete and not result.blocked
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.kind == kind and candidate.game_id == "shared_x"
    assert candidate.resolution == "raw_definition"
    assert candidate.support_level == "synthetic_static"
    assert candidate.id_source_ref is not None
    assert candidate.id_source_ref.raw_bytes(raw) == b"shared_x"
    assert candidate.source_ref.raw_bytes(raw).startswith(
        b"shared_x =" if kind in ("trait", "government") else kind.encode() + b" ="
    )
    assert candidate.localisation_key == (
        "shared_x" if kind == "trait" else "shared_x_display"
    )
    assert [f.raw_value for f in candidate.conditions] == ["{ flag = yes }"]
    assert next(f for f in candidate.fields if f.name == "cost").raw_value == "100"
    assert all(f.source_ref.snapshot_id == "A" for f in candidate.fields)
    assert verify_domain_candidate(candidate, raw, ctx)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_duplicate_fields_and_duplicate_ids_are_not_merged(kind: str):
    first = sample(kind, body="cost = 200 potential = { other = yes }")
    second = sample(kind, body="cost = 300")
    raw, ctx, result = adapted(kind, first + "\n" + second)
    assert [c.game_id for c in result.candidates] == ["shared_x", "shared_x"]
    assert [c.definition_occurrence for c in result.candidates] == [1, 2]
    assert all(c.resolution == "ambiguous" for c in result.candidates)
    assert [f.raw_value for f in result.candidates[0].fields if f.name == "cost"] == [
        "100", "200",
    ]
    assert [f.occurrence for f in result.candidates[0].fields if f.name == "cost"] == [1, 2]
    assert len(result.candidates[0].conditions) == 2
    assert any(d.code == "DOMAIN_DUPLICATE_ID" for d in result.diagnostics)
    assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_cross_file_collision_and_cross_snapshot_fail_closed(kind: str):
    raw, ctx, left = adapted(kind, sample(kind), filename="left.txt")
    _, _, right = adapted(kind, sample(kind, body="cost = 777"), filename="right.txt")
    conflicts = find_domain_collisions((*left.candidates, *right.candidates))
    assert len(conflicts) == 1 and len(conflicts[0].definition_source_refs) == 2
    assert conflicts[0].definition_source_refs[0].relative_path.endswith("left.txt")
    assert conflicts[0].definition_source_refs[1].relative_path.endswith("right.txt")
    assert not verify_domain_candidate(left.candidates[0], raw, replace(ctx, relative_path=DOMAIN_REGISTRY[kind].path_prefix + "other.txt"))
    assert not verify_domain_candidate(left.candidates[0], raw, replace(ctx, snapshot_id="B"))
    _, _, foreign = adapted(kind, sample(kind), snapshot="B")
    with pytest.raises(ValueError, match="snapshot"):
        find_domain_collisions((*left.candidates, *foreign.candidates))


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_r1_raw_backing_field_condition_and_nested_rejected(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    candidate = result.candidates[0]
    other = raw.replace(b"100", b"999")
    field = next(f for f in candidate.fields if f.name == "cost")
    assert field.value is not None
    forged = replace(candidate, fields=tuple(
        replace(f, value=replace(f.value, _source=other)) if f is field else f
        for f in candidate.fields
    ))
    assert next(f for f in forged.fields if f.name == "cost").raw_value == "999"
    assert not verify_domain_candidate(forged, raw, ctx)
    other_condition = raw.replace(b"yes", b"no!")
    condition = candidate.conditions[0]
    assert condition.value is not None and condition.value.children
    bad_condition = replace(condition, value=replace(condition.value, _source=other_condition))
    assert not verify_domain_candidate(
        replace(candidate, conditions=(bad_condition,)), raw, ctx
    )
    child = replace(condition.value.children[0], _source=other_condition)
    bad_nested = replace(condition.value, children=(child,))
    forged_fields = tuple(
        replace(f, value=bad_nested) if f.source_ref == condition.source_ref else f
        for f in candidate.fields
    )
    assert not verify_domain_candidate(replace(candidate, fields=forged_fields), raw, ctx)
    assert not verify_domain_candidate(
        replace(candidate, conditions=(replace(condition, value=bad_nested),)), raw, ctx
    )
    assert verify_domain_candidate(candidate, raw, ctx)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_r1_field_identity_operator_and_occurrence_tampering_rejected(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    c = result.candidates[0]
    f = c.fields[-1]
    for damaged in (
        replace(c, definition_occurrence=42),
        replace(c, fields=(*c.fields[:-1], replace(f, name="changed"))),
        replace(c, fields=(*c.fields[:-1], replace(f, operator=">"))),
        replace(c, fields=(*c.fields[:-1], replace(f, source_ref=replace(f.source_ref, byte_start=0)))),
    ):
        assert not verify_domain_candidate(damaged, raw, ctx)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_r2_canonical_parse_and_hard_limits(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    parsed = parse_bytes(raw)
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(parse_bytes(b""), raw, ctx, kind)
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(replace(parsed, document=replace(parsed.document, items=())), raw, ctx, kind)
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(replace(
            parsed, tokens=(replace(parsed.tokens[0], span=replace(parsed.tokens[0].span, column_start=33)), *parsed.tokens[1:])
        ), raw, ctx, kind)
    for restricted in (parse_bytes(raw, max_tokens=2), parse_bytes(raw, max_nodes=2)):
        stopped = adapt_domain(restricted, raw, ctx, kind)
        assert stopped.blocked and not stopped.candidates
    assert verify_domain_candidate(result.candidates[0], raw, ctx)
    with patch("stellaris_supporter.domain.generic.parse_bytes", wraps=parse_bytes) as canonical:
        assert len(adapt_domain(parsed, raw, ctx, kind).candidates) == 1
    assert canonical.call_count == 1


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_missing_dynamic_and_duplicate_id_fields_remain_partial(kind: str):
    original = sample(kind)
    if kind == "trait":
        text = original.replace("shared_x =", "@dynamic =")
        _, _, result = adapted(kind, text)
        assert not result.candidates and result.unhandled and not result.complete
    elif kind == "government":
        text = original.replace("shared_x = {", "@dynamic = {")
        _, _, result = adapted(kind, text)
        assert not result.candidates and result.unhandled and not result.complete
    else:
        field = "key" if kind == "civic" else "id"
        for fragment in ("", f"{field} = @dynamic", f"{field} = shared_x {field} = other_x", f"{field} > shared_x"):
            text = original.replace(f"{field} = shared_x", fragment)
            _, _, result = adapted(kind, text)
            assert result.candidates and result.candidates[0].game_id is None
            assert result.candidates[0].resolution == "partial"
            assert any(d.code == "DOMAIN_UNRESOLVED_ID" for d in result.diagnostics)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_bad_operators_unclosed_unknown_and_strings_are_partial(kind: str):
    _, _, result = adapted(kind, sample(kind, body='cost >= 44 mystery ^ = 1'))
    assert not result.complete
    assert any(d.code == "DOMAIN_UNSUPPORTED_OPERATOR" for d in result.diagnostics)
    assert any(d.code in {"PARSE_UNKNOWN_SYNTAX", "DOMAIN_UNKNOWN_STRUCTURE"} for d in result.diagnostics)
    _, _, broken = adapted(kind, sample(kind)[:-2])
    assert not broken.complete
    assert any(d.code == "PARSE_UNCLOSED_BLOCK" for d in broken.diagnostics)
    raw, _, safe = adapted(
        kind, sample(kind, body='description = "fake = { # }"') + "\n# ignored = { cost = 999 }"
    )
    assert safe.complete
    assert len(safe.candidates) == 1
    assert b'fake = { # }' in raw


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_localisation_korean_english_missing_refs_and_snapshot(kind: str):
    raw, ctx, result = adapted(kind, sample(kind))
    c = result.candidates[0]
    key = c.localisation_key
    assert key is not None
    ko = f'l_korean:\n {key}:0 "한글 $part_a$"\n part_a:0 "$part_b$"\n part_b:0 "이름"\n'.encode()
    en = f'l_english:\n {key}:0 "English Name"\n'.encode()
    docs = (document(ko, language="korean"), document(en))
    names = build_localisation_catalog(docs)
    name = resolve_domain_name(c, names, "korean").localisation
    assert name.display_value == "한글 이름"
    assert name.language_used == "korean" and name.fallback == "none"
    assert name.source_ref == docs[0].entries[0].source_ref
    assert len(name.reference_source_refs) == 2
    assert all(ref.snapshot_id == ctx.snapshot_id for ref in name.reference_source_refs)
    en_name = resolve_domain_name(c, names, "english").localisation
    assert en_name.display_value == "English Name" and en_name.language_used == "english"
    english_only = resolve_domain_name(c, build_localisation_catalog((document(en),)), "korean").localisation
    assert english_only.fallback == "english" and english_only.language_used == "english"
    missing = resolve_domain_name(c, build_localisation_catalog(()), "korean").localisation
    assert missing.resolution == "unresolved" and missing.fallback == "id"
    assert missing.display_value == key
    with pytest.raises(ValueError, match="snapshot"):
        resolve_domain_name(c, build_localisation_catalog((document(ko, language="korean", snapshot="B"),)))


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_localisation_ambiguous_cycle_dynamic_limit_and_tampered_source(kind: str):
    _, _, result = adapted(kind, sample(kind))
    c = result.candidates[0]
    key = c.localisation_key
    assert key is not None
    repeated = f'l_korean:\n {key}:0 "a"\n {key}:0 "b"\n'.encode()
    ambiguous = resolve_domain_name(c, build_localisation_catalog((document(repeated, language="korean"),))).localisation
    assert ambiguous.resolution == "ambiguous"
    cyclic = f'l_korean:\n {key}:0 "$dep$"\n dep:0 "$dep$"\n'.encode()
    cycle = resolve_domain_name(c, build_localisation_catalog((document(cyclic, language="korean"),))).localisation
    assert cycle.resolution == "partial" and any(d.code == "LOC_CYCLE" for d in cycle.diagnostics)
    dynamic = f'l_english:\n {key}:0 "[Root.GetName] £energy£"\n'.encode()
    dyn = resolve_domain_name(c, build_localisation_catalog((document(dynamic),)), "english").localisation
    assert dyn.resolution == "partial" and any(d.code == "LOC_DYNAMIC_UNSUPPORTED" for d in dyn.diagnostics)
    bounded = resolve_domain_name(c, build_localisation_catalog((document(dynamic),)), "english", max_scan_bytes=1).localisation
    assert bounded.resolution == "partial" and bounded.truncated
    altered_ctx = replace(document(dynamic).context, file_sha256="0" * 64)
    forged_doc = parse_localisation(dynamic, altered_ctx)
    assert not forged_doc.complete and not forged_doc.entries
    compromised = resolve_domain_name(c, build_localisation_catalog((forged_doc,)), "english").localisation
    assert compromised.resolution != "resolved"


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_utf8_bom_crlf_hangul_source_and_raw_budget(kind: str):
    src = "\ufeff" + sample(kind, body='description = "한글 # {}"').replace(" cost", "\r\n cost")
    raw, _, result = adapted(kind, src)
    c = result.candidates[0]
    assert c.resolution == "raw_definition"
    assert any(f.raw_value == '"한글 # {}"' for f in c.fields)
    expected = b"shared_x" if kind in ("trait", "government") else f"{kind} =".encode()
    assert c.source_ref.raw_bytes(raw).startswith(expected)
    with pytest.raises(ValueError):
        result.to_dict(include_raw=True, max_raw_bytes=1)
    bad = b"\xff"
    bad_ctx = context(kind, bad)
    with pytest.raises(ValueError, match="ParseResult"):
        adapt_domain(parse_bytes(b""), bad, bad_ctx, kind)
    stopped = adapt_domain(parse_bytes(bad), bad, bad_ctx, kind)
    assert stopped.blocked and not stopped.candidates



def test_wave2_government_multiple_direct_children_and_unhandled_contents():
    source = (
        "governments = { first_government = { name = first_name potential = { flag = yes } } "
        "second_government = { name = second_name } @unsupported = dynamic }"
    )
    raw, ctx, result = adapted("government", source)
    assert [c.game_id for c in result.candidates] == [
        "first_government", "second_government",
    ]
    assert len(result.unhandled) == 1 and not result.complete
    assert result.unhandled[0].raw.startswith("@unsupported")
    assert all(verify_domain_candidate(c, raw, ctx) for c in result.candidates)
    _, _, wrong_wrapper = adapted(
        "government", "civics = { first_government = { name = first_name } }"
    )
    assert not wrong_wrapper.candidates and not wrong_wrapper.complete
    assert len(wrong_wrapper.unhandled) == 1


@pytest.mark.parametrize("kind", ("government", "civic", "origin"))
@pytest.mark.parametrize("replacement", ("", "name = @dynamic", "name = duplicate name = other"))
def test_wave2_display_name_key_is_distinct_from_id_and_never_guessed(
    kind: str, replacement: str
):
    original = sample(kind)
    _, _, result = adapted(
        kind, original.replace("name = shared_x_display", replacement)
    )
    assert len(result.candidates) == 1
    candidate = result.candidates[0]
    assert candidate.game_id == "shared_x"
    assert candidate.localisation_key is None
    assert candidate.resolution == "partial"
    assert any(
        d.code == "DOMAIN_UNRESOLVED_LOCALISATION_KEY"
        for d in candidate.diagnostics
    )
    with pytest.raises(ValueError, match="localisation key"):
        resolve_domain_name(candidate, build_localisation_catalog(()))


def test_wave2_identical_ids_in_different_kinds_are_not_collisions():
    candidates = tuple(
        adapted(kind, sample(kind))[2].candidates[0] for kind in KINDS
    )
    assert [c.kind for c in candidates] == list(KINDS)
    assert {c.game_id for c in candidates} == {"shared_x"}
    assert not find_domain_collisions(candidates)


@pytest.mark.parametrize("kind", KINDS)
def test_wave2_path_and_sha_boundaries_stay_fail_closed(kind: str):
    source = sample(kind).encode("utf-8")
    ctx = context(kind, source)
    parsed = parse_bytes(source)
    for damaged in (
        replace(ctx, relative_path="other/wave2.txt"),
        replace(ctx, relative_path="../common/traits/wave2.txt"),
        replace(ctx, file_sha256="0" * 64),
    ):
        with pytest.raises(ValueError):
            adapt_domain(parsed, source, damaged, kind)
