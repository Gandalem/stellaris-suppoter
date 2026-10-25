"""E-028/E-029 authored synthetic references and read-only UI service."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest

from stellaris_supporter.domain import SourceContext, SourceRef, adapt_technologies
from stellaris_supporter.domain.event_references import EXTRACTOR_VERSION, extract_event_records
from stellaris_supporter.domain.generic import adapt_domain
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.references import ReferenceQuery, ReferenceService
from stellaris_supporter.storage import (
    SnapshotError,
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    snapshot_identity,
)


def seed(repo, techs=(b'a = { prerequisites = { b } }\nb = {}\n',), events=(), *, tag="a"):
    sources = tuple(SourceFileInput("synthetic", "refs", f"common/technology/{i}.txt", data)
                    for i, data in enumerate(techs)) + tuple(
        SourceFileInput("synthetic", "refs", f"events/{i}.txt", data)
        for i, data in enumerate(events))
    policy = SnapshotPolicy("ordered-parser-1", "reference-tests-1", hashlib.sha256(tag.encode()).hexdigest(),
                            analysis_context={"event_references": EXTRACTOR_VERSION} if events else {})
    sid = snapshot_identity(sources, policy).snapshot_id
    tech_results, event_results, records = [], [], []
    for source in sources:
        context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                                hashlib.sha256(source.data).hexdigest())
        parsed = parse_bytes(source.data)
        if source.relative_path.startswith("events/"):
            result = adapt_domain(parsed, source.data, context, "event")
            event_results.append(result)
            records.extend(extract_event_records(result.candidates, parsed, source.data, context))
        else:
            tech_results.append(adapt_technologies(parsed, source.data, context))
    repo.stage_from_results(sources, policy, technology_results=tuple(tech_results),
                            event_results=tuple(event_results), event_records=tuple(records))
    repo.activate(sid, allow_partial=True)
    return sid


@pytest.fixture
def repo(tmp_path):
    return SnapshotRepository(tmp_path / "private")


def refs(repo, game_id="a", **kwargs):
    return ReferenceService(repo).refs(ReferenceQuery(game_id, **kwargs))


def mutate(repo, sql, params=()):
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute(sql, params)


def test_chain_bom_crlf_hangul_duplicate_occurrences_and_sources(repo):
    source = '\ufeffa = {\r\n # 한글\r\n prerequisites = { "b" b }\r\n}\r\nb = {}\r\n'.encode()
    sid = seed(repo, (source,))
    answer = refs(repo, depth=3)
    assert answer.status == "ok"
    assert answer.snapshot_id == sid
    assert [e.occurrence for e in answer.edges] == [1, 2]
    assert [n.game_id for n in answer.nodes] == ["a", "b"]
    assert [repo.citation_bytes(e.source_ref) for e in answer.edges] == [b'"b"', b'b']
    assert all(e.source_ref.line_start == 3 for e in answer.edges)
    assert repo.active_snapshot_id() == sid


@pytest.mark.parametrize("kind", ["technology", "event"])
def test_e028_missing_and_ambiguous_targets(repo, kind):
    if kind == "technology":
        seed(repo, (b'a={ prerequisites={ missing dup } }\ndup={}\ndup={}',))
        root = "a"
    else:
        seed(repo, events=(b'namespace=demo\ncountry_event={id=demo.1 immediate={'
                           b'country_event={id=demo.missing} planet_event={id=demo.dup}}}\n'
                           b'country_event={id=demo.dup}\nplanet_event={id=demo.dup}',))
        root = "demo.1"
    answer = refs(repo, root, kind=kind, depth=4)
    assert answer.status == "partial"
    assert [e.status for e in answer.edges] == ["unresolved", "ambiguous"]
    assert all(e.target_entity_key is None for e in answer.edges)
    assert len(answer.edges[1].candidate_entity_keys) == 2
    assert [n.game_id for n in answer.nodes] == [root]


def test_duplicate_roots_need_selection_and_keep_original_order(repo):
    seed(repo, (b'a={prerequisites={b}}\nb={}', b'a={}'))
    answer = refs(repo)
    assert answer.status == "partial" and not answer.edges
    assert len(answer.candidates) == 2
    assert answer.candidates[0].source_ref.relative_path.endswith("0.txt")
    selected = refs(repo, entity_key=answer.candidates[1].entity_key)
    assert selected.status == "ok" and not selected.edges
    assert refs(repo, "b", entity_key=answer.candidates[1].entity_key).status == "not_found"


def test_root_and_target_candidate_limits_are_explicit(repo):
    seed(repo, (b'a={prerequisites={b}}\nb={}\nb={}\nb={}\nb={}',))
    target = refs(repo)
    assert target.edges[0].status == "ambiguous" and target.edges[0].candidates_truncated
    assert len(target.edges[0].candidate_entity_keys) == 2
    root = refs(repo, "b", limit=2)
    assert len(root.candidates) == 2 and root.truncated
    assert root.truncation_reasons == ("candidate_limit",)


@pytest.mark.parametrize("source,cycle_count", [
    (b'a={prerequisites={a}}', 1),
    (b'a={prerequisites={b}}\nb={prerequisites={a}}', 1),
    (b'a={prerequisites={b c}}\nb={prerequisites={d}}\nc={prerequisites={d}}\nd={}', 0),
])
def test_e029_cycles_terminate_and_diamond_is_not_cycle(repo, source, cycle_count):
    seed(repo, (source,))
    answer = refs(repo, depth=16)
    assert answer.status == "ok"
    assert len(answer.cycles) == cycle_count
    assert len(answer.nodes) <= 4


def test_event_cycle(repo):
    seed(repo, events=(b'namespace=demo\ncountry_event={id=demo.1 immediate={country_event={id=demo.2}}}\n'
                       b'country_event={id=demo.2 immediate={country_event={id=demo.1}}}',))
    answer = refs(repo, "demo.1", kind="event", depth=16)
    assert answer.status == "ok" and len(answer.cycles) == 1


def test_depth_result_limits_and_bfs_minimum_depth(repo):
    seed(repo, (b'a={prerequisites={b c}}\nb={prerequisites={d}}\nc={prerequisites={d}}\nd={}',))
    shallow = refs(repo)
    assert shallow.truncated and shallow.truncation_reasons == ("depth_limit",)
    assert {n.game_id: n.depth for n in shallow.nodes} == {"a": 0, "b": 1, "c": 1}
    limited = refs(repo, depth=16, limit=1)
    assert len(limited.edges) == 1 and "result_limit" in limited.truncation_reasons
    complete = refs(repo, depth=16)
    assert {n.game_id: n.depth for n in complete.nodes}["d"] == 2


def test_empty_not_found_partial_and_unsupported_are_distinct(repo):
    seed(repo, (b'a={}\nb={prerequisites={@dynamic}}',))
    assert refs(repo).status == "ok"
    assert refs(repo, "missing").status == "not_found"
    assert refs(repo, "b").status == "partial"
    assert refs(repo, "demo.1", kind="event").status == "unsupported"


@pytest.mark.parametrize("changes", [
    {"depth": 0}, {"depth": 17}, {"depth": True}, {"limit": 0}, {"limit": 101},
    {"limit": True}, {"game_id": ""}, {"game_id": "a\n"}, {"kind": "ship"},
    {"snapshot_id": "missing"}, {"entity_key": "bad"}, {"game_id": " a"},
])
def test_invalid_queries_do_not_open_repository(repo, monkeypatch, changes):
    def forbidden(*args, **kwargs):
        raise AssertionError("storage was opened")
    monkeypatch.setattr(repo, "reference_reader", forbidden)
    query = replace(ReferenceQuery("a"), **changes)
    answer = ReferenceService(repo).refs(query)
    assert answer.status == "error" and answer.abstained
    assert answer.diagnostics[0]["code"] == "QUERY_INVALID"


def test_snapshot_pinning_during_activation_navigation_and_cards(repo, monkeypatch):
    from stellaris_supporter.storage.reference_reader import ReferenceReader
    old = seed(repo)
    new = seed(repo, (b'a={}',), tag="b")
    repo.activate(old, allow_partial=True)
    original = ReferenceReader.candidates
    activated = False
    def switch(reader, *args, **kwargs):
        nonlocal activated
        if not activated:
            activated = True
            repo.activate(new, allow_partial=True)
        return original(reader, *args, **kwargs)
    monkeypatch.setattr(ReferenceReader, "candidates", switch)
    service = ReferenceService(repo)
    answer = service.refs(ReferenceQuery("a", depth=3))
    assert answer.snapshot_id == old and len(answer.edges) == 1
    card = service.pin(answer)
    assert service.refresh(card).snapshot_id == old
    assert service.navigate(answer.nodes[1], snapshot_id=old).query.game_id == "b"
    assert service.source_text(answer.edges[0].source_ref) == "b"
    assert len(refs(repo).edges) == 0
    with pytest.raises(SnapshotError):
        service.pin(refs(repo, "missing"))


@pytest.mark.parametrize("attack", ["target", "line", "span", "deleted", "payload", "key", "status"])
def test_relation_or_entity_tampering_abstains(repo, attack):
    seed(repo)
    if attack == "target":
        mutate(repo, "UPDATE relations SET target_game_id='forged'")
    elif attack in {"line", "span"}:
        with sqlite3.connect(repo.db_path) as conn:
            payload = json.loads(conn.execute("SELECT source_ref_json FROM relations").fetchone()[0])
            payload["line_start" if attack == "line" else "byte_start"] += 1
            conn.execute("UPDATE relations SET source_ref_json=?", (json.dumps(payload),))
    elif attack == "deleted":
        mutate(repo, "DELETE FROM relations")
    elif attack == "payload":
        mutate(repo, "UPDATE entities SET candidate_json=json_set(candidate_json,'$.prerequisites',json('[]')) WHERE game_id='a'")
    elif attack == "key":
        mutate(repo, "UPDATE entities SET entity_key=? WHERE game_id='a'", ("f" * 64,))
    else:
        mutate(repo, "UPDATE relations SET status='ambiguous'")
    answer = refs(repo)
    assert answer.status == "error" and answer.abstained
    assert not answer.nodes and not answer.edges
    assert answer.diagnostics[0]["code"] == "SOURCE_CHANGED"


def test_nested_definition_is_not_a_root(repo):
    from stellaris_supporter.domain.technology import _candidate_from_pair
    source = SourceFileInput("synthetic", "refs", "common/technology/nested.txt", b'outer={a={prerequisites={b}}}')
    policy = SnapshotPolicy("ordered-parser-1", "test", "d" * 64)
    sid = snapshot_identity((source,), policy).snapshot_id
    context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                            hashlib.sha256(source.data).hexdigest())
    parsed = parse_bytes(source.data)
    nested = parsed.document.items[0].value.items[0]
    candidate = _candidate_from_pair(nested, source.data, context, ())
    repo.stage((source,), policy, candidates=(candidate,))
    repo.activate(sid, allow_partial=True)
    answer = refs(repo)
    assert answer.status == "error" and not answer.edges


@pytest.mark.parametrize("budget, expected", [("MAX_CHECKED_NODES", "node_limit"), ("MAX_SCANNED_EDGES", "scan_limit")])
def test_soft_request_budgets(repo, monkeypatch, budget, expected):
    import stellaris_supporter.references as module
    seed(repo)
    monkeypatch.setattr(module, budget, 1 if budget == "MAX_CHECKED_NODES" else 0)
    answer = refs(repo)
    assert answer.status == "partial" and answer.truncated
    assert expected in answer.truncation_reasons


@pytest.mark.parametrize("budget", ["source", "output"])
def test_hard_budgets_abstain(repo, monkeypatch, budget):
    seed(repo)
    if budget == "source":
        import stellaris_supporter.storage.reference_reader as module
        monkeypatch.setattr(module, "MAX_REQUEST_SOURCE_BYTES", 1)
    else:
        import stellaris_supporter.references as module
        monkeypatch.setattr(module, "MAX_RESPONSE_BYTES", 1)
    answer = refs(repo)
    assert answer.status == "error" and answer.abstained and not answer.nodes
    assert answer.diagnostics[0]["code"] == "LIMIT_EXCEEDED"


def test_event_nested_static_calls_keep_guards_and_ignore_quotes_comments(repo):
    event = b'''namespace=demo
country_event={id=demo.1 title="country_event={id=fake.1}" trigger={country_event={id=fake.2}}
 immediate={
  # country_event={id=fake.3}
  if={limit={always=yes} hidden_effect={planet_event={id="demo.2" days=5}}}
 }
 option={name=demo.option country_event={id=demo.2}}
}
planet_event={id=demo.2}
'''
    seed(repo, events=(event,))
    answer = refs(repo, "demo.1", kind="event", depth=3)
    assert answer.status == "ok"
    assert [e.target_game_id for e in answer.edges] == ["demo.2", "demo.2"]
    assert [e.occurrence for e in answer.edges] == [1, 2]
    assert "limit={always=yes}" in answer.edges[0].conditions_raw
    assert json.loads(answer.edges[1].conditions_raw)[0]["name"] == "option"
    assert repo.citation_bytes(answer.edges[0].source_ref) == b'"demo.2"'


@pytest.mark.parametrize("effect", [
    b'country_event={id=@variable}', b'country_event={id=demo.2 id=demo.3}',
    b'country_event=@call', b'owner={country_event={id=demo.2}}', b'if=yes',
])
def test_unsupported_event_calls_are_partial_not_successful_empty(repo, effect):
    seed(repo, events=(b'namespace=demo\ncountry_event={id=demo.1 immediate={' + effect + b'}}',))
    answer = refs(repo, "demo.1", kind="event")
    assert answer.status == "partial" and not answer.edges
    assert not answer.nodes[0].coverage_complete and answer.nodes[0].coverage_reasons


def test_event_guard_tampering_abstains(repo):
    seed(repo, events=(b'namespace=demo\ncountry_event={id=demo.1 immediate={if={limit={always=yes} country_event={id=demo.2}}}}',))
    mutate(repo, "UPDATE relations SET conditions_raw='[]'")
    assert refs(repo, "demo.1", kind="event").status == "error"


def test_source_panel_limit_and_cross_snapshot_rejection(repo):
    sid = seed(repo)
    answer = refs(repo)
    ref = answer.nodes[0].source_ref
    service = ReferenceService(repo)
    with pytest.raises(SnapshotError):
        service.source_text(ref, max_bytes=1)
    forged = SourceRef(**{**ref.to_dict(), "snapshot_id": "0" * 64})
    with pytest.raises(SnapshotError):
        service.source_text(forged)
    assert sid != forged.snapshot_id


def test_corrupt_cache_abstains(repo):
    seed(repo)
    answer = refs(repo)
    blob = repo.cache._path(answer.nodes[0].source_ref.file_sha256)
    original = blob.read_bytes()
    blob.write_bytes(original.replace(b'a', b'z', 1))
    result = refs(repo)
    assert result.status == "error" and not result.nodes and not result.edges
    assert result.diagnostics[0]["code"] == "SOURCE_CHANGED"


@pytest.mark.parametrize("column", ["candidate_json", "source_ref_json", "conditions_raw"])
def test_oversized_stored_records_abstain_before_materialization(repo, column):
    seed(repo)
    if column == "candidate_json":
        mutate(repo, "UPDATE entities SET candidate_json=? WHERE game_id='a'", ('"' + 'x' * (1024 * 1024) + '"',))
    else:
        mutate(repo, f"UPDATE relations SET {column}=?", ('x' * (1024 * 1024 + 1),))
    answer = refs(repo)
    assert answer.status == "error" and answer.abstained
    assert answer.diagnostics[0]["code"] == "LIMIT_EXCEEDED"


def test_event_depth_limit_is_explicit(repo):
    seed(repo, events=(b'namespace=demo\ncountry_event={id=demo.1 immediate={country_event={id=demo.2}}}\n'
                       b'country_event={id=demo.2 immediate={country_event={id=demo.3}}}\n'
                       b'country_event={id=demo.3}',))
    answer = refs(repo, "demo.1", kind="event")
    assert answer.status == "partial" and answer.truncation_reasons == ("depth_limit",)
    assert len(answer.edges) == 1


def test_event_namespace_warning_keeps_reference_coverage_partial(repo):
    seed(repo, events=(b'namespace=other\ncountry_event={id=demo.1 immediate={country_event={id=demo.2}}}',))
    answer = refs(repo, "demo.1", kind="event")
    assert answer.status == "partial"
    assert "DOMAIN_EVENT_NAMESPACE_MISMATCH" in answer.nodes[0].coverage_reasons


def test_event_record_omission_rejected_at_safe_stage_boundary(repo):
    source = SourceFileInput("synthetic", "refs", "events/0.txt", b'namespace=demo\ncountry_event={id=demo.1}')
    policy = SnapshotPolicy("parser-1", "adapter-1", "b" * 64)
    sid = snapshot_identity((source,), policy).snapshot_id
    context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                            hashlib.sha256(source.data).hexdigest())
    adapted = adapt_domain(parse_bytes(source.data), source.data, context, "event")
    with pytest.raises(SnapshotError) as error:
        repo.stage_from_results((source,), policy, event_results=(adapted,))
    assert error.value.code == "SOURCE_CHANGED" and repo.snapshot(sid) is None


def test_reference_kind_does_not_cross_link_same_game_id(repo):
    seed(repo, (b'a={prerequisites={demo.1}}',),
         events=(b'namespace=demo\ncountry_event={id=demo.1 title=demo_title}',))
    answer = refs(repo)
    assert answer.edges[0].status == "unresolved"
    event = refs(repo, "demo.1", kind="event")
    assert event.status == "ok" and event.nodes[0].kind == "event"


@pytest.mark.parametrize("value", [None, "a", ReferenceQuery("x" * (1024 * 1024 + 1)), ReferenceQuery("a", kind=[])])
def test_invalid_api_input_has_bounded_serializable_error(repo, value):
    answer = ReferenceService(repo).refs(value)
    assert answer.status == "error" and answer.abstained
    assert answer.diagnostics[0]["code"] == "QUERY_INVALID"
    assert len(json.dumps(answer.to_dict())) < 4096


def test_event_guard_amplification_stops_during_extraction(repo, monkeypatch):
    import stellaris_supporter.domain.event_references as extraction
    body = b'namespace=demo\ncountry_event={id=demo.1 immediate={if={limit={always=yes}'
    body += b'country_event={id=demo.2}' * 40 + b'}}}'
    monkeypatch.setattr(extraction, "MAX_REFERENCE_RAW_BYTES", 4 * len(body))
    with pytest.raises(SnapshotError) as error:
        seed(repo, events=(body,))
    assert error.value.code == "LIMIT_EXCEEDED"
    assert repo.active_snapshot_id() is None


def test_scan_budget_includes_target_source_proof_and_depth_boundary(repo, monkeypatch):
    import stellaris_supporter.references as module
    seed(repo, (b'a={prerequisites={b}}\nb={prerequisites={c}}\nc={}',))
    monkeypatch.setattr(module, "MAX_SCANNED_EDGES", 1)
    answer = refs(repo, depth=1)
    assert answer.status == "partial" and answer.truncation_reasons == ("scan_limit",)
    assert [n.game_id for n in answer.nodes] == ["a"] and not answer.edges
    monkeypatch.setattr(module, "MAX_SCANNED_EDGES", 2)
    answer = refs(repo, depth=1)
    assert [n.game_id for n in answer.nodes] == ["a", "b"]
    assert len(answer.edges) == 1 and answer.truncation_reasons == ("depth_limit",)


@pytest.mark.parametrize("invalid_id", [None, ""])
def test_idless_technology_is_rejected_not_silently_skipped(repo, invalid_id):
    source = SourceFileInput("synthetic", "refs", "common/technology/0.txt", b'a={}')
    policy = SnapshotPolicy("parser-1", "adapter-1", "e" * 64)
    sid = snapshot_identity((source,), policy).snapshot_id
    context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                            hashlib.sha256(source.data).hexdigest())
    adapted = adapt_technologies(parse_bytes(source.data), source.data, context)
    invalid = replace(adapted.candidates[0], game_id=invalid_id)
    with pytest.raises(SnapshotError) as error:
        repo.stage((source,), policy, candidates=(invalid,))
    assert error.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() is None
