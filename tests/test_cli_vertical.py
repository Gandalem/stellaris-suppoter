"""E-026: installed/module CLI end-to-end on authored technology fixtures only."""
from __future__ import annotations

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
    from stellaris_supporter.storage import SnapshotError
    from stellaris_supporter.storage.cache import live_source_relative_path
    with pytest.raises(SnapshotError):
        live_source_relative_path(other / "foreign.txt", game)


def test_e026_duplicate_game_ids_are_not_merged(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    path = game / "common/technology/demo.txt"
    path.write_bytes(path.read_bytes() + b"demo_tech = { tier = 9 }\n")
    assert query(config, "index")[0] == 0
    rc, result, _ = query(config, "show", "demo_tech")
    assert rc == 0 and result["status"] == "partial"
    assert len(result["results"]) == 2
    assert len({x["entity_key"] for x in result["results"]}) == 2
    assert {f["raw_expression"] for x in result["results"]
            for f in x["facts"] if f["field_name"] == "tier"} == {"2", "9"}


def test_e026_partial_explicit_opt_in_keeps_diagnostics(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    script = game / "common/technology/demo.txt"
    script.write_bytes(script.read_bytes().replace(b"tier = 2", b"tier = \xff"))
    failed_code, failed, _ = query(config, "index")
    assert failed_code == 5 and failed["status"] == "error"
    assert query(config, "snapshots")[1]["results"][0]["status"] == "partial"
    rc, permitted, _ = query(config, "index", "--allow-partial")
    assert rc == 0 and permitted["status"] == "partial"
    assert permitted["activated"] is True


def test_e026_allow_partial_never_bypasses_root_security(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    root = game / "common" / "technology"
    forbidden = root / "bad.txt"
    try:
        forbidden.symlink_to(tmp_path / "outside.txt")
    except (OSError, NotImplementedError):
        # Non-link platforms still exercise the path guard as a unit:
        from stellaris_supporter.storage import SnapshotError
        from stellaris_supporter.storage.cache import live_source_relative_path
        with pytest.raises(SnapshotError):
            live_source_relative_path(tmp_path / "outside.txt", game)
    else:
        code, result, _ = query(config, "index", "--allow-partial")
        assert code == 4 and result["status"] == "error"


def test_e026_inventory_to_capture_change_fails_before_staging(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.cli_index as integration
    from stellaris_supporter.config import load_settings
    from stellaris_supporter.storage import SnapshotError, SnapshotRepository

    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    previous = integration.index_technologies(repo, settings)["snapshot_id"]
    technology = game / "common/technology/demo.txt"
    original = integration._read_verified_file
    def mutate(path, *, expected_hash, expected_size):
        technology.write_bytes(technology.read_bytes().replace(b"tier = 2", b"tier = 3"))
        return original(path, expected_hash=expected_hash, expected_size=expected_size)
    monkeypatch.setattr(integration, "_read_verified_file", mutate)
    with pytest.raises(SnapshotError) as exc:
        integration.index_technologies(repo, settings)
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() == previous


def test_e026_modified_live_path_during_activation_preserves_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.cli_index as integration
    from stellaris_supporter.config import load_settings
    from stellaris_supporter.storage import SnapshotError, SnapshotRepository

    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    previous = integration.index_technologies(repo, settings)["snapshot_id"]
    technology = game / "common/technology/demo.txt"
    technology.write_bytes(technology.read_bytes().replace(b"tier = 2", b"tier = 3"))
    original = repo.activate
    def mutate(sid, **kwargs):
        technology.write_bytes(technology.read_bytes().replace(b"tier = 3", b"tier = 4"))
        return original(sid, **kwargs)
    monkeypatch.setattr(repo, "activate", mutate)
    with pytest.raises(SnapshotError) as exc:
        integration.index_technologies(repo, settings)
    assert exc.value.code == "SOURCE_CHANGED"
    assert repo.active_snapshot_id() == previous


def test_e026_writer_failure_preserves_prior_active(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.cli_index as integration
    from stellaris_supporter.config import load_settings
    from stellaris_supporter.storage import SnapshotError, SnapshotRepository

    game, data, config = initialised(tmp_path)
    settings = load_settings(config).settings
    repo = SnapshotRepository(data, game_root=game)
    previous = integration.index_technologies(repo, settings)["snapshot_id"]
    script = game / "common/technology/demo.txt"
    script.write_bytes(script.read_bytes().replace(b"tier = 2", b"tier = 3"))
    def locked(*args, **kwargs):
        raise SnapshotError("SQLITE_BUSY", "Synthetic writer lock.")
    monkeypatch.setattr(repo, "stage_from_results", locked)
    with pytest.raises(SnapshotError) as exc:
        integration.index_technologies(repo, settings)
    assert exc.value.code == "SQLITE_BUSY"
    assert repo.active_snapshot_id() == previous


def test_e026_cancel_maps_to_130_and_clean_json(
    tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch,
) -> None:
    import stellaris_supporter.cli as cli

    _, _, config = initialised(tmp_path)
    def stopped(*args, **kwargs):
        raise KeyboardInterrupt
    monkeypatch.setattr(cli, "index_technologies", stopped)
    code = cli.main(["--config", str(config), "--format", "json", "index"])
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    assert code == 130 and payload["status"] == "error"
    assert payload["diagnostics"][0]["code"] == "CANCELLED"
    assert "Traceback" not in stdout


def test_e026_cache_corruption_is_not_returned_as_fact(tmp_path: Path) -> None:
    import hashlib

    game, data, config = initialised(tmp_path)
    assert query(config, "index")[0] == 0
    script = (game / "common/technology/demo.txt").read_bytes()
    digest = hashlib.sha256(script).hexdigest()
    cache = data / "cache" / "blobs" / digest[:2] / digest
    assert cache.is_file()
    cache.write_bytes(b"x" * len(script))
    rc, result, _ = query(config, "show", "demo_tech")
    assert rc in {5, 6}
    assert result["status"] == "error" and result["results"] == []


def test_e026_bounded_snapshot_listing_and_text(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    assert query(config, "index")[0] == 0
    script = game / "common/technology/demo.txt"
    script.write_bytes(script.read_bytes().replace(b"tier = 2", b"tier = 3"))
    assert query(config, "index")[0] == 0
    rc, snapshots, _ = query(config, "snapshots", "--limit", "1")
    assert rc == 0 and len(snapshots["results"]) == 1 and snapshots["truncated"]
    out = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", "--config", str(config),
         "show", "demo_tech"], text=True, capture_output=True, check=False,
    )
    assert out.returncode == 0
    assert "demo_tech" in out.stdout
    assert "common/technology/demo.txt" in out.stdout


def test_e026_config_file_symlink_rejected_where_supported(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    link = tmp_path / "linked.toml"
    try:
        link.symlink_to(config)
    except (OSError, NotImplementedError):
        from stellaris_supporter.cli_setup import _check_components
        # The file system may prohibit symlinks on this Windows account.
        # Keep the portable safe-path check without a skipped test.
        assert _check_components(config) is None
    else:
        rc, result, _ = invoke("--format", "json", "--config", str(link), "index")
        assert rc == 4 and result["diagnostics"][0]["code"] == "PATH_REJECTED"


def test_e026_installed_console_script_smoke(tmp_path: Path) -> None:
    import shutil

    entrypoint = shutil.which("stellaris-supporter")
    assert entrypoint is not None
    game, data, config = corpus(tmp_path)
    process = subprocess.run(
        [entrypoint, "init", "--format", "json", "--config", str(config),
         "--game-root", str(game), "--data-dir", str(data)],
        text=True, capture_output=True, check=False,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["status"] == "ok"
    process = subprocess.run(
        [entrypoint, "--format", "json", "--config", str(config), "index"],
        text=True, capture_output=True, check=False,
    )
    assert process.returncode == 0
    assert json.loads(process.stdout)["snapshot_id"]


def test_e026_limit_failure_does_not_replace_active(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    previous = query(config, "index")[1]["snapshot_id"]
    script = game / "common/technology/demo.txt"
    script.write_bytes(script.read_bytes() + b"# additional comments exceed limit\n")
    with config.open("a", encoding="utf-8") as handle:
        handle.write("\n[limits]\nfile_bytes = 16\n")
    code, result, _ = query(config, "index", "--allow-partial")
    assert code == 4 and result["status"] == "error"
    code, listings, _ = query(config, "snapshots")
    assert code == 0
    assert next(x for x in listings["results"] if x["active"])["snapshot_id"] == previous


@pytest.mark.parametrize("arguments", [
    ("--format", "json", "search"),
    ("--format", "json", "search", "demo_tech", "--limit", "not-an-int"),
    ("--format", "json", "show"),
    ("--format", "json", "unsupported-subcommand"),
])
def test_e026_argparse_failure_is_single_sanitized_json(arguments: tuple[str, ...]) -> None:
    result = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", *arguments],
        text=True, capture_output=True, check=False,
    )
    assert result.returncode == 2
    obj = json.loads(result.stdout)
    assert obj["schema_version"] == 1
    assert obj["status"] == "error"
    assert obj["diagnostics"][0]["code"] == "QUERY_INVALID"
    assert "Traceback" not in result.stderr


def test_e026_partial_localisation_can_only_activate_with_consent(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    loc = game / "localisation/korean/demo_l_korean.yml"
    loc.write_bytes(b"l_korean:\n demo_tech:0 \xff\n")
    rc, failed, _ = query(config, "index")
    assert rc == 5 and failed["status"] == "error"
    rc, listed, _ = query(config, "snapshots")
    assert rc == 0
    assert listed["results"][0]["status"] == "partial"
    assert not listed["results"][0]["active"]
    rc, accepted, _ = query(config, "index", "--allow-partial")
    assert rc == 0
    assert accepted["status"] == "partial"
    assert accepted["activated"] is True


def test_e026_sqlite_writer_failure_is_exit_six_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import stellaris_supporter.cli as cli
    from stellaris_supporter.storage import SnapshotError

    _, _, config = initialised(tmp_path)

    def unavailable(*args, **kwargs):
        raise SnapshotError("SQLITE_BUSY", "Synthetic write conflict.")

    monkeypatch.setattr(cli, "index_technologies", unavailable)
    code = cli.main(["--config", str(config), "--format", "json", "index"])
    result = json.loads(capsys.readouterr().out)
    assert code == 6 and result["status"] == "error"
    assert result["results"] == []
    assert result["diagnostics"][0]["code"] == "SQLITE_BUSY"


def test_e026_snapshot_identity_ignores_private_root_spelling(tmp_path: Path) -> None:
    _, _, config_a = initialised(tmp_path / "first")
    _, _, config_b = initialised(tmp_path / "second location")
    rc_a, one, _ = query(config_a, "index")
    rc_b, two, _ = query(config_b, "index")
    assert rc_a == rc_b == 0
    assert one["snapshot_id"] == two["snapshot_id"]


def test_e026_network_enabled_config_rejected_before_writing(tmp_path: Path) -> None:
    game, data, config = initialised(tmp_path)
    contents = config.read_text(encoding="utf-8")
    config.write_text(
        contents.replace("enabled = false", "enabled = true"), encoding="utf-8"
    )
    rc, result, _ = query(config, "index")
    assert rc == 4 and result["status"] == "error"
    assert not data.joinpath("snapshots.sqlite3").exists()
    assert game.joinpath("common/technology/demo.txt").is_file()


def test_e026_invalid_nul_config_path_returns_security_exit(
    tmp_path: Path, capsys: pytest.CaptureFixture[str],
) -> None:
    import stellaris_supporter.cli as cli

    game, _, _ = corpus(tmp_path)
    rc = cli.main(["--format", "json", "--config", "unsafe\x00config",
                   "init", "--game-root", str(game)])
    result = json.loads(capsys.readouterr().out)
    assert rc == 4 and result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "PATH_REJECTED"


def test_e026_malformed_toml_returns_config_exit_three(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    config.write_bytes(b"schema_version = [unclosed\n")
    code, result, stderr = query(config, "index")
    assert code == 3
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"].startswith("CONFIG_")
    assert "Traceback" not in stderr


def test_e026_private_data_directory_missing_returns_exit_three(tmp_path: Path) -> None:
    _, data, config = initialised(tmp_path)
    data.rmdir()
    code, result, _ = query(config, "index")
    assert code == 3
    assert result["status"] == "error"
    assert result["diagnostics"][0]["code"] == "DATA_DIR_MISSING"


def test_e026_pre_stage_technology_root_id_validation(tmp_path: Path) -> None:
    import hashlib
    from dataclasses import replace

    import stellaris_supporter.cli_index as integration
    from stellaris_supporter.domain import SourceContext, adapt_technologies
    from stellaris_supporter.parsing import parse_bytes
    from stellaris_supporter.storage import SnapshotError, SourceFileInput

    game, _, _ = corpus(tmp_path)
    data = (game / "common/technology/demo.txt").read_bytes()
    source = SourceFileInput(
        "base", "base_install", "common/technology/demo.txt", data
    )
    ctx = SourceContext(
        "a" * 64, "base", "base_install",
        source.relative_path, hashlib.sha256(data).hexdigest(),
    )
    adapted = adapt_technologies(parse_bytes(data), data, ctx)
    assert len(adapted.candidates) == 1
    forged = replace(adapted, candidates=(
        replace(adapted.candidates[0], game_id="demo_forged"),
    ))
    with pytest.raises(SnapshotError) as exc:
        integration._verify_adapted_ids(source, forged)
    assert exc.value.code == "SOURCE_CHANGED"
    integration._verify_adapted_ids(source, adapted)


def test_e026_large_search_payload_abstains_without_partial_json(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    import stellaris_supporter.cli as cli

    # A synthetic retrieval payload with an oversized static display value.
    # Existing E-026 subprocess tests separately prove normal search service
    # integration; this case isolates the complete stdout serialization gate.
    huge = {
        "schema_version": 1, "command": "search", "status": "ok",
        "results": [{"display_name": "합금" * 400_000}],
        "diagnostics": [],
    }
    monkeypatch.setattr(cli, "_run_command", lambda _args: (0, huge))
    rc = cli.main(["--format", "json", "search", "demo_tech"])
    stdout = capsys.readouterr().out
    result = json.loads(stdout)
    assert rc == 4 and result["status"] == "error"
    assert result["results"] == []
    assert result["diagnostics"][0]["code"] == "LIMIT_EXCEEDED"
    assert len(stdout.encode("utf-8")) < 1024




# TASK-013 R1-R5: authored synthetic regression cases (never game files).

@pytest.mark.parametrize("code", [
    "LIMIT_EXCEEDED", "PARSE_DEPTH_LIMIT", "PARSE_NODE_LIMIT", "PARSE_DIAGNOSTIC_LIMIT",
])
def test_review_r1_technology_bound_is_not_partial_consent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, code: str,
) -> None:
    from dataclasses import replace
    import stellaris_supporter.cli_index as pipeline
    from stellaris_supporter.config import load_settings
    from stellaris_supporter.domain import TechnologyDiagnostic
    from stellaris_supporter.storage import SnapshotError, SnapshotRepository

    game, data, config = initialised(tmp_path)
    repo = SnapshotRepository(data, game_root=game)
    settings = load_settings(config).settings
    original_active = pipeline.index_technologies(repo, settings)["snapshot_id"]
    target = game / "common/technology/demo.txt"
    target.write_bytes(target.read_bytes().replace(b"tier = 2", b"tier = 3"))
    adapter = pipeline.adapt_technologies

    def resource_diagnostic(*args, **kwargs):
        result = adapter(*args, **kwargs)
        diagnostic = TechnologyDiagnostic(
            code, "error", "Synthetic parser or lexer bound.",
            result.candidates[0].source_ref, origin="parser",
        )
        return replace(result, diagnostics=(*result.diagnostics, diagnostic),
                       complete=False)

    monkeypatch.setattr(pipeline, "adapt_technologies", resource_diagnostic)
    with pytest.raises(SnapshotError) as exc:
        pipeline.index_technologies(repo, settings, allow_partial=True)
    assert exc.value.code == "LIMIT_EXCEEDED"
    assert repo.active_snapshot_id() == original_active


def test_review_r1_deep_static_localisation_reference_is_never_activated(
    tmp_path: Path,
) -> None:
    game, _, config = initialised(tmp_path)
    active = query(config, "index")[1]["snapshot_id"]
    chain = [
        f' layer_{index}:0 "$layer_{index + 1}$"'
        for index in range(68)
    ]
    (game / "localisation/korean/demo_l_korean.yml").write_text(
        'l_korean:\n demo_tech:0 "$layer_0$"\n' +
        "\n".join(chain) + '\n layer_68:0 "끝"\n', encoding="utf-8"
    )
    for args in ((), ("--allow-partial",)):
        rc, failed, _ = query(config, "index", *args)
        assert rc == 4 and failed["status"] == "error"
        assert failed["diagnostics"][0]["code"] == "LIMIT_EXCEEDED"
        assert next(x for x in query(config, "snapshots")[1]["results"]
                    if x["active"])["snapshot_id"] == active


def test_review_r2_non_target_file_size_does_not_consume_budget(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    (game / "common/technology/unrelated.bin").write_bytes(b"x" * 1024)
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nfile_bytes = 200\n")
    rc, result, _ = query(config, "index")
    assert rc == 0 and result["activated"]


def test_review_r2_non_target_file_count_does_not_consume_budget(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    for n in range(6):
        (game / "common/technology" / f"unrelated_{n}.bin").write_bytes(b"ignored")
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nmax_files = 3\n")
    rc, result, _ = query(config, "index")
    assert rc == 0 and result["source_count"] == 3


def test_review_r2_target_budget_and_cross_root_aggregate(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    (game / "common/technology/excess.txt").write_bytes(b"X" * 256)
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nfile_bytes = 200\n")
    assert query(config, "index")[0] == 4
    (game / "common/technology/excess.txt").unlink()
    config.write_text(config.read_text().replace("file_bytes = 200", "max_files = 2"),
                      encoding="utf-8")
    rc, result, _ = query(config, "index")
    assert rc == 4 and result["diagnostics"][0]["code"] == "LIMIT_EXCEEDED"


def test_review_r2_supported_symlink_remains_rejected(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    target = tmp_path / "elsewhere.txt"
    target.write_text("never index", encoding="utf-8")
    path = game / "common/technology/unsafe.txt"
    try:
        path.symlink_to(target)
    except (OSError, NotImplementedError):
        from stellaris_supporter.storage.cache import live_source_relative_path
        from stellaris_supporter.storage import SnapshotError
        with pytest.raises(SnapshotError):
            live_source_relative_path(target, game)
    else:
        rc, result, _ = query(config, "index", "--allow-partial")
        assert rc == 4 and result["diagnostics"][0]["code"] == "PATH_REJECTED"


@pytest.mark.parametrize("text,rc", [("demo", 0), ("demos", 4)])
def test_review_r3_configured_query_char_boundary_search(
    tmp_path: Path, text: str, rc: int,
) -> None:
    _, _, config = initialised(tmp_path)
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nquery_chars = 4\n")
    assert query(config, "index")[0] == 0
    code, result, _ = query(config, "search", text)
    assert code == rc
    assert result["status"] == ("error" if rc else "not_found")


def test_review_r3_configured_result_default_and_explicit_limit(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    source = game / "common/technology/demo.txt"
    source.write_bytes(source.read_bytes() + b"demo_other = { tier = 9 }\n")
    for name, lang in (("korean", "korean"), ("english", "english")):
        loc = game / f"localisation/{name}/demo_l_{lang}.yml"
        loc.write_text(loc.read_text(encoding="utf-8") +
                       f' demo_other:0 "Other Tech"\n', encoding="utf-8")
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nmax_results = 1\n")
    assert query(config, "index")[0] == 0
    for command, identifier in (("search", "demo_tech"), ("show", "demo_tech")):
        code, found, _ = query(config, command, identifier)
        assert code == 0 and len(found["results"]) == 1
        code, found, _ = query(config, command, identifier, "--limit", "1")
        assert code == 0
        code, failed, _ = query(config, command, identifier, "--limit", "2")
        assert code == 4 and failed["diagnostics"][0]["code"] == "LIMIT_EXCEEDED"
    assert query(config, "search", "demo_tech", "--limit", "0")[0] == 2


def test_review_r3_show_applies_configured_query_chars(tmp_path: Path) -> None:
    _, _, config = initialised(tmp_path)
    with config.open("a", encoding="utf-8") as stream:
        stream.write("\n[limits]\nquery_chars = 4\n")
    assert query(config, "index")[0] == 0
    code, answer, _ = query(config, "show", "demo_tech")
    assert code == 4 and answer["status"] == "error"
    assert answer["diagnostics"][0]["code"] == "LIMIT_EXCEEDED"


def test_review_r4_snapshot_text_contains_full_row_metadata(tmp_path: Path) -> None:
    game, _, config = initialised(tmp_path)
    assert query(config, "index")[0] == 0
    script = game / "common/technology/demo.txt"
    script.write_bytes(script.read_bytes().replace(b"tier = 2", b"tier = 3"))
    assert query(config, "index")[0] == 0
    _, rows, _ = query(config, "snapshots")
    assert len(rows["results"]) >= 2
    active = next(x for x in rows["results"] if x["active"])
    other = next(x for x in rows["results"] if not x["active"])
    result = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", "--config", str(config),
         "snapshots"], capture_output=True, text=True, check=False,
    )
    assert result.returncode == 0
    assert active["snapshot_id"] in result.stdout
    assert other["snapshot_id"] in result.stdout
    for item in (active, other):
        expected = "true" if item["active"] else "false"
        assert f"active: {expected}" in result.stdout
        assert f"status: {item['status']}" in result.stdout
        for field in ("context_kind", "branch", "created_at", "checked_at"):
            assert f"{field}: {item[field]}" in result.stdout
        assert "game_version: unknown" in result.stdout
    paged = subprocess.run(
        [sys.executable, "-m", "stellaris_supporter", "--config", str(config),
         "snapshots", "--limit", "1", "--offset", "1"],
        capture_output=True, text=True, check=False,
    )
    assert paged.returncode == 0
    assert "limit: 1" in paged.stdout and "offset: 1" in paged.stdout


def test_review_r5_terminal_controls_escaped_only_in_text(tmp_path: Path) -> None:
    import stellaris_supporter.cli as cli

    unsafe = "합금\x1bc\r\b\u202e Research"
    payload = {
        "command": "search", "status": "ok", "schema_version": 1,
        "results": [{"game_id": "demo_tech", "display_name": unsafe, "status": "ok"}],
        "diagnostics": [{"code": "DEMO", "message": unsafe}],
    }
    from io import StringIO
    from contextlib import redirect_stdout
    output = StringIO()
    with redirect_stdout(output):
        cli._emit_text(payload)
    text = output.getvalue()
    assert "\x1b" not in text and "\r" not in text and "\b" not in text
    assert "\u202e" not in text
    assert "\\x1b" in text and "\\r" in text and "\\b" in text
    assert "\\u202e" in text
    assert "합금" in text and "Research" in text
    assert json.loads(cli._bounded_json(payload))["results"][0]["display_name"] == unsafe
