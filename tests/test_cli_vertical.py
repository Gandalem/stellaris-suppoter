"""E-026: installed/module CLI end-to-end on authored technology fixtures only."""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest



def invoke(*args: str) -> tuple[int, dict, str]:
    process = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", *args],
        capture_output=True, text=True, check=False, timeout=60,
    )
    assert not process.stdout.startswith("Traceback")
    return process.returncode, json.loads(process.stdout), process.stderr


def corpus(tmp_path: Path) -> tuple[Path, Path, Path]:
    game, data, config = tmp_path / "game", tmp_path / "data", tmp_path / "config.toml"
    tech = game / "common" / "technology"
    ko = game / "localisation" / "korean"
    en = game / "localisation" / "english"
    for parent in (tech, ko, en):
        parent.mkdir(parents=True)
    (tech / "demo.txt").write_bytes(
        b"\xef\xbb\xbfdemo_tech = {\r\n cost = @demo_cost\r\n tier = 2\r\n}\r\n"
    )
    (ko / "demo_l_korean.yml").write_text(
        'l_korean:\n demo_tech:0 "합금 연구"\n', encoding="utf-8"
    )
    (en / "demo_l_english.yml").write_text(
        'l_english:\n demo_tech:0 "Alloy Research"\n', encoding="utf-8"
    )
    return game, data, config


def initialised(tmp_path: Path) -> tuple[Path, Path, Path]:
    game, data, config = corpus(tmp_path)
    rc, payload, err = invoke(
        "--format", "json", "--config", str(config), "init",
        "--game-root", str(game), "--data-dir", str(data),
    )
    assert rc == 0, (payload, err)
    assert payload["status"] == "ok"
    assert config.is_file() and data.is_dir()
    return game, data, config


def query(config: Path, command: str, *args: str) -> tuple[int, dict, str]:
    return invoke("--config", str(config), "--format", "json", command, *args)


def test_e026_real_subprocess_vertical_flow_and_exact_citations(tmp_path: Path) -> None:
    game, data, config = initialised(tmp_path)
    original = (game / "common/technology/demo.txt").read_bytes()
    _, doctor, _ = query(config, "doctor")
    assert doctor["status"] in {"ok", "warning"}
    rc, built, err = query(config, "index")
    assert rc == 0, (built, err)
    assert built["status"] == "ok" and built["activated"]
    sid = built["snapshot_id"]
    assert len(sid) == 64
    for text in ("demo_tech", "합금 연구", "Alloy Research"):
        rc, found, _ = query(config, "search", text)
        assert rc == 0
        assert found["results"] and found["results"][0]["game_id"] == "demo_tech"
    rc, show, _ = query(config, "show", "demo_tech")
    assert rc == 0
    assert show["results"][0]["game_id"] == "demo_tech"
    assert show["context"]["snapshot_id"] == sid
    fields = show["results"][0]["facts"]
    assert next(f["raw_expression"] for f in fields if f["field_name"] == "cost") == "@demo_cost"
    for fact in fields:
        ref = fact["value_source_ref"]
        assert ref and original[ref["byte_start"]:ref["byte_end"]].decode() == fact["raw_expression"]
    assert show["results"][0]["localisation_source_ref"]["relative_path"].startswith("localisation/")
    rc, snapshots, _ = query(config, "snapshots")
    assert rc == 0
    assert any(x["snapshot_id"] == sid and x["active"] for x in snapshots["results"])
    rc, repeated, _ = query(config, "index")
    assert rc == 0 and repeated["snapshot_id"] == sid
    assert repeated["reused"] is True
    assert original == (game / "common/technology/demo.txt").read_bytes()
    assert data.joinpath("snapshots.sqlite3").is_file()


def test_e026_init_exclusive_and_options_after_command(tmp_path: Path) -> None:
    game, data, config = initialised(tmp_path)
    rc, error, _ = invoke("init", "--format", "json", "--config", str(config),
                          "--game-root", str(game), "--data-dir", str(data))
    assert rc == 4
    assert error["diagnostics"][0]["code"] == "CONFIG_EXISTS"
    assert config.read_text(encoding="utf-8").startswith("schema_version = 1")


def test_e026_missing_and_invalid_query_exits(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    rc, missing, _ = query(config, "search", "demo_tech")
    assert rc == 3 and missing["status"] == "error"
    assert query(config, "index")[0] == 0
    assert query(config, "search", "absent_id")[1]["status"] == "not_found"
    assert query(config, "show", "absent_id")[1]["status"] == "not_found"
    rc, invalid, _ = query(config, "search", "demo_tech", "--limit", "0")
    assert rc == 2 and invalid["status"] == "error"
    rc, invalid, _ = query(config, "search", "demo_tech", "--kind", "unsupported")
    assert rc == 2
    assert invalid["diagnostics"][0]["code"] == "QUERY_INVALID"


def test_e026_show_never_mistakes_name_for_id(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    assert query(config, "index")[0] == 0
    assert query(config, "search", "합금 연구")[1]["results"]
    assert query(config, "show", "합금 연구")[1]["status"] == "not_found"
    assert query(config, "show", "demo_tec")[1]["status"] == "not_found"


def test_e026_explicit_snapshot_does_not_switch_active(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    first = query(config, "index")[1]["snapshot_id"]
    tech = game / "common/technology/demo.txt"
    tech.write_bytes(tech.read_bytes().replace(b"tier = 2", b"tier = 3"))
    second = query(config, "index")[1]["snapshot_id"]
    assert first != second
    assert query(config, "show", "demo_tech", "--snapshot", first)[1]["context"]["snapshot_id"] == first
    assert query(config, "show", "demo_tech")[1]["context"]["snapshot_id"] == second
    assert next(x for x in query(config, "snapshots")[1]["results"] if x["active"])["snapshot_id"] == second


def test_e026_bad_unicode_partial_never_activates_unapproved(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    first = query(config, "index")[1]["snapshot_id"]
    (game / "common/technology/demo.txt").write_bytes(b"demo_tech = { cost = \xff }\n")
    rc, result, _ = query(config, "index")
    assert rc == 5 and result["status"] == "error"
    assert next(x for x in query(config, "snapshots")[1]["results"] if x["active"])["snapshot_id"] == first


def test_e026_path_overlap_and_no_private_path_error_leak(tmp_path: Path) -> None:
    game, _, _ = corpus(tmp_path)
    conf = tmp_path / "overlap.toml"
    rc, data, stderr = invoke(
        "init", "--format", "json", "--config", str(conf),
        "--game-root", str(game), "--data-dir", str(game / "private"),
    )
    assert rc == 4
    assert not conf.exists()
    assert str(tmp_path) not in json.dumps(data) + stderr


def test_e026_snapshot_missing_and_bad_sha(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    assert query(config, "index")[0] == 0
    assert query(config, "search", "demo_tech", "--snapshot", "a" * 64)[0] == 3
    assert query(config, "search", "demo_tech", "--snapshot", "bad")[0] == 2


def test_e026_large_query_and_json_stdout_clean(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    query(config, "index")
    rc, message, stderr = query(config, "search", "x" * 513)
    assert rc == 2
    assert message["diagnostics"][0]["code"] == "QUERY_INVALID"
    assert not stderr.startswith("Traceback")


def test_e026_cli_version_help_and_console_entrypoint() -> None:
    from stellaris_supporter.cli import build_parser
    assert "--version" in build_parser().format_help()
    assert all(name in build_parser().format_help() for name in (
        "init", "doctor", "index", "search", "show", "snapshots"
    ))
    proc = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", "--version"],
        text=True, capture_output=True, check=False,
    )
    assert proc.returncode == 0
    assert proc.stdout.strip() == "stellaris-supporter 0.0.1"


def test_e026_init_language_and_format_before_after_conflict(tmp_path: Path) -> None:
    game, data, config = corpus(tmp_path)
    rc, obj, _ = invoke(
        "--format", "text", "--config", str(config), "init",
        "--format", "json", "--game-root", str(game), "--data-dir", str(data),
    )
    assert rc == 0 and obj["status"] == "ok"


def test_e026_config_missing_returns_json_error(tmp_path: Path) -> None:
    code, obj, _ = invoke(
        "--format", "json", "--config", str(tmp_path / "missing.toml"), "index"
    )
    assert code == 3
    assert obj["status"] == "error"


def test_e026_symlink_component_rejected_where_supported(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    other = tmp_path / "outside"
    other.mkdir()
    # If the OS forbids creating links, use the invalid absolute source-root
    # boundary test rather than creating a platform-specific skipped test.
    link = game / "common" / "technology" / "foreign.txt"
    try:
        link.symlink_to(other / "foreign.txt")
    except (OSError, NotImplementedError):
        pass
    else:
        rc, obj, _ = query(config, "index")
        assert rc == 4 and obj["status"] == "error"
        return
    # This validates the path guard on platforms that cannot create links.
    from stellaris_supporter.storage.cache import live_source_relative_path
    from stellaris_supporter.storage import SnapshotError
    with pytest.raises(SnapshotError):
        live_source_relative_path(other / "foreign.txt", game)
