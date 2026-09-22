from __future__ import annotations

import hashlib
import json
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent / "fixtures" / "synthetic"
MANIFEST_PATH = ROOT / "manifest.json"
GENERATOR = Path(__file__).resolve().parents[1] / "scripts" / "generate_synthetic_corpus.py"


def load_manifest() -> dict[str, object]:
    return json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))


def manifest_files() -> list[dict[str, object]]:
    manifest = load_manifest()
    files = manifest["files"]
    assert isinstance(files, list)
    return files


def test_manifest_declares_original_synthetic_provenance() -> None:
    manifest = load_manifest()

    assert manifest["schema_version"] == 1
    assert manifest["origin"] == "synthetic"
    assert manifest["deterministic"] is True
    assert "No Stellaris game" in str(manifest["provenance"])


def test_required_scenario_families_are_present() -> None:
    manifest = load_manifest()
    required = set(manifest["required_scenarios"])
    scenarios = {str(entry["scenario"]) for entry in manifest_files()}

    assert required == {"normal", "error", "localisation", "collision"}
    assert required <= scenarios


def test_manifest_hashes_sizes_and_paths_match_committed_bytes() -> None:
    for entry in manifest_files():
        relative = Path(str(entry["path"]))
        assert not relative.is_absolute()
        assert ".." not in relative.parts

        content = (ROOT / relative).read_bytes()
        assert len(content) == entry["size"]
        assert hashlib.sha256(content).hexdigest() == entry["sha256"]


def test_generator_reproduces_committed_bytes(tmp_path: Path) -> None:
    generated = tmp_path / "generated"
    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(generated)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0, result.stderr
    expected_paths = ["manifest.json", *(str(entry["path"]) for entry in manifest_files())]
    for relative in expected_paths:
        assert (generated / relative).read_bytes() == (ROOT / relative).read_bytes()


def test_generator_refuses_nonempty_output_without_force(tmp_path: Path) -> None:
    output = tmp_path / "existing"
    output.mkdir()
    sentinel = output / "keep.txt"
    sentinel.write_text("do not replace", encoding="utf-8")

    result = subprocess.run(
        [sys.executable, str(GENERATOR), "--output", str(output)],
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode != 0
    assert sentinel.read_text(encoding="utf-8") == "do not replace"


def test_encoding_edges_keep_exact_intentional_bytes() -> None:
    bom = (ROOT / "corpus/encoding/bom_crlf.txt").read_bytes()
    assert bom.startswith(b"\xef\xbb\xbf")
    assert b"\r\n" in bom
    assert b"\n" not in bom.replace(b"\r\n", b"")

    invalid = (ROOT / "corpus/encoding/invalid_utf8.txt").read_bytes()
    assert invalid.startswith(b"# origin: synthetic\n")
    with pytest.raises(UnicodeDecodeError):
        invalid.decode("utf-8")


def test_every_fixture_is_marked_synthetic_at_byte_level() -> None:
    for entry in manifest_files():
        content = (ROOT / str(entry["path"])).read_bytes()
        if content.startswith(b"\xef\xbb\xbf"):
            content = content[3:]
        assert content.startswith(b"# origin: synthetic")


def test_collision_and_localisation_fixture_invariants() -> None:
    normal = (ROOT / "corpus/common/technology/00_demo_normal.txt").read_bytes()
    collision = (ROOT / "corpus/common/technology/01_demo_collision.txt").read_bytes()
    english = (ROOT / "corpus/localisation/english/demo_l_english.yml").read_bytes()
    korean = (ROOT / "corpus/localisation/korean/demo_l_korean.yml").read_bytes()

    assert normal.count(b"demo_prism_lattice = {") == 1
    assert collision.count(b"demo_prism_lattice = {") == 1
    assert english.count(b"demo_duplicate_loc:0") == 2
    assert b"demo_english_only:0" in english
    assert b"demo_english_only:0" not in korean
    assert b"demo_korean_only:0" in korean
    assert b"demo_korean_only:0" not in english
    assert b"demo_missing_loc:0" not in english + korean
    assert b'demo_cycle_a:0 "$demo_cycle_b$"' in english
    assert b'demo_cycle_b:0 "$demo_cycle_a$"' in english
