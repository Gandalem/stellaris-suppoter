"""Essential E-030/E-031 and comparison acceptance, authored temporary data only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import replace

import pytest
from test_cli_vertical import initialised, query

from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.comparison import DiffQuery, DiffService
from stellaris_supporter.config import load_settings
from stellaris_supporter.domain import SourceContext, adapt_technologies
from stellaris_supporter.domain.event_references import EXTRACTOR_VERSION, extract_event_records
from stellaris_supporter.domain.generic import adapt_domain
from stellaris_supporter.localisation import (
    build_localisation_catalog,
    parse_localisation,
    resolve_technology_name,
)
from stellaris_supporter.parsing import parse_bytes
from stellaris_supporter.references import ReferenceQuery, ReferenceService
from stellaris_supporter.storage import (
    SnapshotError,
    SnapshotPolicy,
    SnapshotRepository,
    SourceFileInput,
    snapshot_identity,
)


def snapshot(repo, tech=b'a={cost=100 prerequisites={b}}\nb={}', *, loc=None, event=None,
             parser="ordered-parser-1", extra=None):
    files = {"common/technology/demo.txt": tech, **(extra or {})}
    if loc is not None:
        files["localisation/korean/demo.yml"] = loc.encode()
    if event is not None:
        files["events/demo.txt"] = event
    sources = tuple(SourceFileInput("synthetic", "demo", name, data) for name, data in files.items())
    policy = SnapshotPolicy(parser, "adapter-1", "a" * 64,
                            analysis_context={"event_references": EXTRACTOR_VERSION} if event is not None else {})
    sid = snapshot_identity(sources, policy).snapshot_id
    if repo.snapshot(sid) is not None:
        return sid
    technologies, events, records, documents = [], [], [], []
    for source in sources:
        context = SourceContext(sid, source.source_kind, source.source_id, source.relative_path,
                                hashlib.sha256(source.data).hexdigest())
        if source.relative_path.startswith("common/technology/"):
            technologies.append(adapt_technologies(parse_bytes(source.data), source.data, context))
        elif source.relative_path.startswith("events/"):
            parsed = parse_bytes(source.data)
            adapted = adapt_domain(parsed, source.data, context, "event")
            events.append(adapted)
            records.extend(extract_event_records(adapted.candidates, parsed, source.data, context))
        else:
            documents.append(parse_localisation(source.data, context))
    catalog = build_localisation_catalog(tuple(documents))
    names = tuple(resolve_technology_name(c, catalog) for result in technologies for c in result.candidates)
    repo.stage_from_results(sources, policy, technology_results=tuple(technologies), event_results=tuple(events),
                            event_records=tuple(records), localisation_documents=tuple(documents), localised_names=names)
    repo.activate(sid, allow_partial=True)
    return sid


@pytest.fixture
def repo(tmp_path):
    return SnapshotRepository(tmp_path / "private")


def compare(repo, before, after, **kwargs):
    return DiffService(repo).compare(DiffQuery(before, after, **kwargs))


def entity_results(answer):
    return [item for item in answer.results if item["section"] == "entities"]


def test_diff_fields_relations_added_removed_sources_and_read_only(repo):
    before = snapshot(repo)
    after = snapshot(repo, b'a={cost=120 prerequisites={b}}\nc={}')
    answer = compare(repo, before, after)
    assert answer.status == "ok", answer
    changes = {r["game_id"]: r for r in entity_results(answer)}
    assert changes['b']['change_kind'] == 'removed' and changes['c']['change_kind'] == 'added'
    cost = next(d for d in changes['a']['details'] if d.get('field') == 'cost')
    assert cost['before'][0]['raw_expression'] == '100' and cost['after'][0]['raw_expression'] == '120'
    relations = next(d for d in changes['a']['details'] if d['section'] == 'relations')
    assert relations['before'][0]['status'] == 'resolved' and relations['after'][0]['status'] == 'unresolved'
    assert changes['a']['before']['source_ref']['snapshot_id'] == before
    assert changes['a']['after']['source_ref']['snapshot_id'] == after
    assert repo.active_snapshot_id() == after
    old = ReferenceService(repo).refs(ReferenceQuery('a', snapshot_id=before))
    assert old.edges[0].status == 'resolved'


def test_comment_whitespace_and_snapshot_ids_are_not_content_changes(repo):
    before = snapshot(repo)
    after = snapshot(repo, b'# moved\r\na = { cost = 100 prerequisites = { b } }\r\nb = { }')
    answer = compare(repo, before, after)
    assert answer.status == 'ok' and not entity_results(answer)
    sourced = compare(repo, before, after, include_source_changes=True)
    assert all(r['change_kind'] == 'source_changed' for r in entity_results(sourced))
    assert len(entity_results(sourced)) == 2
    assert compare(repo, before, before).summary['total_results'] == 0


def test_duplicate_definitions_are_conservative_and_counts_preserved(repo):
    before = snapshot(repo, b'a={cost=1}\na={cost=2}')
    after = snapshot(repo, b'a={cost=1}\na={cost=3}')
    answer = compare(repo, before, after)
    assert answer.status == 'partial'
    ambiguity = next(r for r in entity_results(answer) if r['change_kind'] == 'ambiguous')
    assert len(ambiguity['before_candidates']) == len(ambiguity['after_candidates']) == 1
    same = snapshot(repo, b'# shifted\na={cost=1}\na={cost=2}')
    assert not entity_results(compare(repo, before, same))


def test_translation_change_recomputes_display_and_preserves_prior_sources(repo):
    before = snapshot(repo, b'a={}', loc='l_korean:\n a:0 "$shared$"\n shared:0 "이전 이름"\n')
    after = snapshot(repo, b'a={}', loc='l_korean:\n a:0 "$shared$"\n shared:0 "새 이름"\n')
    answer = compare(repo, before, after, game_id='a')
    item = entity_results(answer)[0]
    assert item['before']['display_name'] == '이전 이름' and item['after']['display_name'] == '새 이름'
    assert any(d['section'] == 'localisation' for d in item['details'])


def test_event_guards_and_collection_scope_are_distinct(repo):
    event = b'namespace=demo\ncountry_event={id=demo.1 title=demo_title immediate={if={limit={always=yes} country_event={id=demo.2}}}}\ncountry_event={id=demo.2 title=demo_title}'
    before = snapshot(repo, event=event)
    after = snapshot(repo, event=event.replace(b'always=yes', b'always=no'))
    answer = compare(repo, before, after, kind='event')
    assert any(d['section'] == 'relations' for r in entity_results(answer) for d in r['details'])
    tech_only = snapshot(repo)
    mixed = compare(repo, tech_only, after)
    assert all(r['kind'] != 'event' for r in mixed.results)
    assert any(d['code'] == 'DIFF_SCOPE_DIFFERENT' for d in mixed.diagnostics)
    assert compare(repo, tech_only, after, kind='event').status == 'unsupported'


def test_interpretation_change_does_not_invent_game_definition_changes(repo):
    before = snapshot(repo)
    after = snapshot(repo, b'a={cost=120}', parser='parser-2')
    answer = compare(repo, before, after)
    assert answer.status == 'partial' and not answer.summary_complete
    assert not entity_results(answer) and any(r['section'] == 'files' for r in answer.results)


def test_filters_pagination_and_partial_analysis_are_separate(repo, monkeypatch):
    before = snapshot(repo, b'a={}\nb={}\nc={}')
    after = snapshot(repo, b'a={cost=1}\nb={cost=2}\nc={cost=3}')
    answer = compare(repo, before, after, interest_ids=('b',))
    assert [r['game_id'] for r in answer.results] == ['b']
    first = compare(repo, before, after, kind='technology', limit=1)
    second = compare(repo, before, after, kind='technology', limit=1, offset=1)
    assert first.summary_complete and first.truncated and first.results != second.results
    import stellaris_supporter.comparison as module
    monkeypatch.setattr(module, 'MAX_COMPARE_RECORDS', 1)
    limited = compare(repo, before, after)
    assert limited.status == 'partial' and not limited.summary_complete
    assert limited.truncation_reasons == ('analysis_limit',) and not entity_results(limited)


@pytest.mark.parametrize('change', [{'before_snapshot': 'bad'}, {'kind': 'building'}, {'limit': True},
                                   {'offset': -1}, {'game_id': ' a'}, {'include_source_changes': 1}])
def test_invalid_diff_is_rejected_before_opening(repo, monkeypatch, change):
    def forbidden(*args, **kwargs):
        raise AssertionError('opened storage')
    monkeypatch.setattr(repo, 'reference_reader', forbidden)
    result = DiffService(repo).compare(replace(DiffQuery('a'*64, 'b'*64), **change))
    assert result.status == 'error' and result.diagnostics[0]['code'] == 'QUERY_INVALID'


def test_corrupt_snapshot_abstains_instead_of_returning_false_diff(repo):
    before = snapshot(repo)
    after = snapshot(repo, b'a={cost=120 prerequisites={b}}\nb={}')
    with sqlite3.connect(repo.db_path) as conn:
        conn.execute("DELETE FROM entities WHERE snapshot_id=? AND game_id='b'", (after,))
    answer = compare(repo, before, after)
    assert answer.status == 'error' and answer.abstained and not answer.results


def test_incremental_and_full_products_match_and_rebind_sources(tmp_path):
    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    original = index_technologies(repo, settings)
    (game / 'common/technology/demo.txt').write_bytes(b'demo_tech={tier=3}\nadded={}\n')
    incremental = index_technologies(repo, settings, allow_partial=True)
    assert incremental['processing']['parsed_files'] == 1
    assert incremental['processing']['reused_files'] == 2
    assert incremental['processing']['file_changes']['modified'] == 1
    full = index_technologies(repo, settings, allow_partial=True, full=True)
    assert full['snapshot_id'] == incremental['snapshot_id']
    assert full['processing']['parsed_files'] == 3 and full['processing']['reused_files'] == 0
    assert original['snapshot_id'] != full['snapshot_id']
    # A fresh repository has the same ID and canonical stored products.
    fresh = SnapshotRepository(tmp_path / 'fresh', game_root=game)
    rebuilt = index_technologies(fresh, settings, allow_partial=True, full=True)
    assert rebuilt['snapshot_id'] == full['snapshot_id']
    assert fresh.entities() == repo.entities()
    for result in repo.entities():
        assert result['candidate']['source_ref']['snapshot_id'] == full['snapshot_id']
    assert query(config, 'show', 'demo_tech')[0] == 0
    assert query(config, 'refs', 'demo_tech')[0] == 0


def test_cached_events_and_localisation_changes_keep_citations(tmp_path):
    game, data, config = initialised(tmp_path)
    event_dir = game / 'events'
    event_dir.mkdir()
    (event_dir / 'demo.txt').write_bytes(b'namespace=demo\ncountry_event={id=demo.1 title=demo_title immediate={if={limit={always=yes} country_event={id=demo.2}}}}\ncountry_event={id=demo.2 title=demo_title}')
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    old = index_technologies(repo, settings, include_events=True)
    (game / 'localisation/korean/demo_l_korean.yml').write_text('l_korean:\n demo_tech:0 "새 기술"\n', encoding='utf-8')
    current = index_technologies(repo, settings, include_events=True)
    assert current['processing']['parsed_files'] == 1 and current['processing']['reused_files'] == 3
    refs = ReferenceService(repo).refs(ReferenceQuery('demo.1', kind='event', depth=3))
    assert refs.status == 'ok' and refs.edges[0].source_ref.snapshot_id == current['snapshot_id']
    assert old['snapshot_id'] not in refs.edges[0].conditions_raw
    assert current['snapshot_id'] in refs.edges[0].conditions_raw
    answer = compare(repo, old['snapshot_id'], current['snapshot_id'])
    assert any(r['game_id']=='demo_tech' for r in entity_results(answer))
    assert index_technologies(repo, settings, include_events=True, full=True)['snapshot_id'] == current['snapshot_id']


@pytest.mark.parametrize('mutation', ['added', 'modified', 'removed'])
def test_e031_change_after_staging_preserves_active(tmp_path, monkeypatch, mutation):
    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    previous = index_technologies(repo, settings)['snapshot_id']
    script = game / 'common/technology/demo.txt'
    script.write_bytes(b'demo_tech={tier=3}')
    stage = repo.stage_from_results
    def change(*args, **kwargs):
        result = stage(*args, **kwargs)
        if mutation == 'added':
            (script.parent / 'new.txt').write_bytes(b'new={}')
        elif mutation == 'modified':
            script.write_bytes(b'demo_tech={tier=4}')
        else:
            script.unlink()
        return result
    monkeypatch.setattr(repo, 'stage_from_results', change)
    with pytest.raises(SnapshotError) as error:
        index_technologies(repo, settings)
    assert error.value.code == 'SOURCE_CHANGED'
    assert repo.active_snapshot_id() == previous


def test_policy_changes_invalidate_products_and_source_removal_is_applied(tmp_path):
    game, data, config = initialised(tmp_path)
    second = game / 'common/technology/extra.txt'
    second.write_bytes(b'extra={}')
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    old = index_technologies(repo, settings, allow_partial=True)
    second.unlink()
    new = index_technologies(repo, settings)
    assert new['processing']['file_changes']['removed'] == 1
    assert [r['game_id'] for r in repo.entities()] == ['demo_tech']
    different = index_technologies(repo, replace(settings, language='english'))
    assert different['processing']['parsed_files'] == 0 and different['snapshot_id'] == new['snapshot_id']
    # Display language is not a parsing-policy dependency in option 2.
    assert len(repo.entities(old['snapshot_id'])) == 2


def test_diff_cli_json_text_and_index_full(tmp_path):
    import subprocess
    import sys
    game, _, config = initialised(tmp_path)
    old = query(config, 'index')[1]['snapshot_id']
    (game / 'common/technology/demo.txt').write_bytes(b'demo_tech={tier=3}')
    rc, current, err = query(config, 'index', '--full')
    assert rc == 0 and not err and current['processing']['mode'] == 'full'
    rc, diff, err = query(config, 'diff', old, current['snapshot_id'], '--game-id', 'demo_tech')
    assert rc == 0 and not err and diff['results'][0]['change_kind'] == 'modified'
    proc = subprocess.run([sys.executable, '-m', 'stellaris_supporter', '--config', str(config),
                           'diff', old, current['snapshot_id']], capture_output=True, text=True, timeout=60)
    assert proc.returncode == 0 and 'modified technology demo_tech' in proc.stdout and 'tier:' in proc.stdout
    assert query(config, 'diff', 'bad', current['snapshot_id'])[0] == 2
    assert query(config, 'search', '합금 연구')[1]['results']


def test_e031_concurrent_activation_does_not_get_overwritten(tmp_path, monkeypatch):
    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    competing = snapshot(repo, b'competitor={}')
    initial = index_technologies(repo, settings)['snapshot_id']
    (game / 'common/technology/demo.txt').write_bytes(b'demo_tech={tier=4}')
    activate = repo.activate
    def race(sid, **kwargs):
        activate(competing, allow_partial=True)
        return activate(sid, **kwargs)
    monkeypatch.setattr(repo, 'activate', race)
    with pytest.raises(SnapshotError) as error:
        index_technologies(repo, settings)
    assert error.value.code == 'SOURCE_CHANGED'
    assert repo.active_snapshot_id() == competing != initial


def test_warm_products_really_skip_unchanged_technology_parsing(tmp_path, monkeypatch):
    import stellaris_supporter.cli_index as pipeline
    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    index_technologies(repo, settings)
    (game / 'localisation/korean/demo_l_korean.yml').write_text('l_korean:\n demo_tech:0 "변경 이름"\n', encoding='utf-8')
    def forbidden(*args, **kwargs):
        raise AssertionError('unchanged script was parsed')
    monkeypatch.setattr(pipeline, 'parse_bytes', forbidden)
    result = index_technologies(repo, settings)
    assert result['processing']['parsed_files'] == 1 and result['processing']['reused_files'] == 2


def test_optional_product_corruption_falls_back_to_original_source(tmp_path):
    from stellaris_supporter.cli_index import _inventory_sources, _policy
    from stellaris_supporter.incremental import FileProducts
    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    index_technologies(repo, settings)
    products = FileProducts(repo, _policy(settings))
    source = next(s for s in _inventory_sources(settings) if s.relative_path.startswith('common/technology/'))
    pointer = json.loads(products.pointers[products._key(source)])
    repo.cache._path(pointer['sha256']).write_bytes(b'broken optional cache')
    (game / 'localisation/korean/demo_l_korean.yml').write_text('l_korean:\n demo_tech:0 "변경 이름"\n', encoding='utf-8')
    result = index_technologies(repo, settings)
    assert result['processing']['parsed_files'] == 2 and result['processing']['reused_files'] == 1
    assert query(config, 'show', 'demo_tech')[0] == 0


def test_repeated_fields_insertion_does_not_relabel_other_fields(repo):
    before = snapshot(repo, b'a={cost=1 tier=2 cost=3}')
    after = snapshot(repo, b'a={weight=5 cost=1 tier=2 cost=3}')
    changes = entity_results(compare(repo, before, after))[0]['details']
    assert [d['field'] for d in changes if d['section']=='fields'] == ['weight']


def test_diff_output_budget_abstains(repo, monkeypatch):
    import stellaris_supporter.comparison as module
    before = snapshot(repo)
    after = snapshot(repo, b'a={cost=120}')
    monkeypatch.setattr(module, 'MAX_DIFF_OUTPUT_BYTES', 1)
    answer = compare(repo, before, after)
    assert answer.status == 'error' and answer.abstained and not answer.results
    assert answer.diagnostics[0]['code'] == 'LIMIT_EXCEEDED'


def test_partial_translation_does_not_invent_removals_or_name_changes(repo):
    before = snapshot(repo, b'a={}', loc='l_korean:\n a:0 "이전 이름"\n')
    after = snapshot(repo, b'a={}', loc='l_korean:\n a:0 "unterminated\n')
    answer = compare(repo, before, after)
    assert answer.status == 'partial' and not answer.summary_complete
    assert not entity_results(answer)
    assert not any(r['section']=='localisation' for r in answer.results)
    assert any(d['code']=='DIFF_PARTIAL_LOCALISATION' for d in answer.diagnostics)
