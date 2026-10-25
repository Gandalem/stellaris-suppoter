"""Real CLI invocation for refs and opt-in event indexing, using authored data."""
from __future__ import annotations

import json
import subprocess
import sys

import pytest
from test_cli_vertical import initialised, query


def event_corpus(game, *, dynamic=False):
    parent = game / "events"
    parent.mkdir(exist_ok=True)
    (parent / "demo.txt").write_bytes(
        b'namespace=demo\ncountry_event={id=demo.1 title=demo_title immediate={'
        + (b'country_event={id=@call}' if dynamic else b'planet_event={id=demo.2}')
        + b'}}\nplanet_event={id=demo.2 title=demo_title}\n'
    )


def test_cli_tech_refs_json_text_and_argument_errors(tmp_path):
    game, _, config = initialised(tmp_path)
    tech = game / "common" / "technology" / "demo.txt"
    tech.write_bytes(b'demo_tech={prerequisites={other}}\nother={}\n')
    assert query(config, "index", "--allow-partial")[0] == 0
    rc, payload, stderr = query(config, "refs", "demo_tech", "--depth", "3")
    assert rc == 0 and not stderr and payload["status"] == "ok"
    assert payload["edges"][0]["target_game_id"] == "other"
    assert payload["edges"][0]["status"] == "resolved"
    process = subprocess.run([sys.executable, "-m", "stellaris_supporter", "--config", str(config),
                              "refs", "demo_tech"], capture_output=True, text=True, timeout=60)
    assert process.returncode == 0 and "-> other" in process.stdout
    assert "common/technology/demo.txt:" in process.stdout
    for flag, value in [("--depth", "0"), ("--depth", "17"), ("--limit", "101"),
                        ("--entity-key", "bad"), ("--kind", "bad")]:
        rc, payload, stderr = query(config, "refs", "demo_tech", flag, value)
        assert rc == 2 and payload["status"] == "error" and not stderr


def test_opt_in_event_index_reuse_and_default_search_show_preserved(tmp_path):
    game, _, config = initialised(tmp_path)
    event_corpus(game)
    rc, original, _ = query(config, "index")
    assert rc == 0
    assert query(config, "refs", "demo.1", "--kind", "event")[1]["status"] == "unsupported"
    rc, mixed, _ = query(config, "index", "--include-events")
    assert rc == 0 and mixed["snapshot_id"] != original["snapshot_id"]
    rc, result, err = query(config, "refs", "demo.1", "--kind", "event", "--depth", "3")
    assert rc == 0 and not err and result["status"] == "ok"
    assert result["edges"][0]["target_game_id"] == "demo.2"
    assert query(config, "search", "demo.1")[1]["results"] == []
    assert query(config, "show", "demo_tech")[1]["results"][0]["game_id"] == "demo_tech"
    rc, reused, _ = query(config, "index", "--include-events")
    assert rc == 0 and reused["reused"] is True and reused["snapshot_id"] == mixed["snapshot_id"]
    assert query(config, "refs", "demo.1", "--kind", "event", "--snapshot", original["snapshot_id"])[1]["status"] == "unsupported"
    assert query(config, "refs", "demo_tech", "--snapshot", original["snapshot_id"])[1]["status"] == "ok"
    # Default policy/identity remains exactly the original technology scope.
    rc, default_again, _ = query(config, "index")
    assert rc == 0 and default_again["snapshot_id"] == original["snapshot_id"]


def test_partial_event_coverage_requires_consent_and_preserves_active(tmp_path):
    game, _, config = initialised(tmp_path)
    original = query(config, "index")[1]["snapshot_id"]
    event_corpus(game, dynamic=True)
    rc, response, _ = query(config, "index", "--include-events")
    assert rc == 5 and response["status"] == "error"
    rows = query(config, "snapshots")[1]["results"]
    assert next(r for r in rows if r["active"])["snapshot_id"] == original
    rc, accepted, _ = query(config, "index", "--include-events", "--allow-partial")
    assert rc == 0 and accepted["snapshot_status"] == "partial"
    result = query(config, "refs", "demo.1", "--kind", "event")[1]
    assert result["status"] == "partial" and not result["edges"]
    assert result["nodes"][0]["coverage_reasons"] == ["nonliteral_event_id"]


@pytest.mark.parametrize("kind", ["technology", "event"])
def test_refs_text_escapes_control_characters(tmp_path, kind):
    game, _, config = initialised(tmp_path)
    if kind == "technology":
        (game / "common" / "technology" / "demo.txt").write_bytes(b'demo_tech={prerequisites={"evil\\x"}}')
        command = ["index", "--allow-partial"]
        root = "demo_tech"
    else:
        event_corpus(game)
        path = game / "events" / "demo.txt"
        path.write_bytes(path.read_bytes().replace(b'id=demo.2}', b'id="evil\x1b[31m"}'))
        command = ["index", "--include-events", "--allow-partial"]
        root = "demo.1"
    assert query(config, *command)[0] == 0
    process = subprocess.run([sys.executable, "-m", "stellaris_supporter", "--config", str(config),
                              "refs", root, "--kind", kind], capture_output=True, text=True, timeout=60)
    assert process.returncode == 0 and "\x1b" not in process.stdout
    json.dumps(query(config, "refs", root, "--kind", kind)[1])
