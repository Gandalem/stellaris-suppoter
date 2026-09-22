"""Generate the original synthetic corpus used by parser/localisation tests.

This script contains only project-authored fictional fixture content. It never reads a
Stellaris installation, user home directory, network resource, save file, DLC, or mod.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Fixture:
    path: str
    scenario: str
    encoding: str
    description: str
    content: bytes


def _text(
    path: str,
    scenario: str,
    description: str,
    content: str,
) -> Fixture:
    return Fixture(path, scenario, "utf-8", description, content.encode("utf-8"))


def fixtures() -> tuple[Fixture, ...]:
    deep = (
        "# origin: synthetic\n"
        + "demo_deep = "
        + ("{ level = " * 130)
        + "leaf"
        + (" }" * 130)
        + "\n"
    )
    return (
        _text(
            "corpus/common/technology/00_demo_normal.txt",
            "normal",
            "Fictional technology-like definitions with prerequisites, variables, "
            "conditions, and weights.",
            """# origin: synthetic
# Fictional test data authored for stellaris-suppoter; not copied from Stellaris.

@demo_cost = 321

demo_echo_theory = {
    area = society
    tier = 1
    cost = 111
    weight = 3
}

demo_prism_lattice = {
    area = physics
    tier = 2
    cost = @demo_cost
    prerequisites = { "demo_echo_theory" }
    potential = {
        has_country_flag = demo_prism_ready
    }
    weight = {
        base = 7
        modifier = {
            factor = 2
            has_country_flag = demo_double_weight
        }
    }
}

demo_english_only = {
    area = engineering
    tier = 1
    cost = 222
}

demo_missing_loc = {
    area = society
    tier = 3
    cost = 333
}
""",
        ),
        _text(
            "corpus/common/technology/01_demo_collision.txt",
            "collision",
            "Duplicate entity IDs, duplicate keys, and a mixed scalar/assignment block.",
            """# origin: synthetic
# Deliberate collisions for preservation tests.

demo_prism_lattice = {
    area = physics
    tier = 9
    cost = 999
    marker = collision_variant
}

demo_duplicate_fields = {
    value = first
    value = second
    mixed = { alpha beta key = gamma }
}
""",
        ),
        _text(
            "corpus/common/technology/02_demo_lexical_edges.txt",
            "lexical-edge",
            "Strings containing comment/brace characters, escaped quotes, comparisons, "
            "and a variable token.",
            r"""# origin: synthetic
# Lexical edge cases are intentionally fictional.

demo_lexical_edges = {
    quoted = "literal # hash and { brace } and \"quoted\""
    variable = @demo_cost
    score > 5
    score <= 9
    floor >= 2
    floor < 8
}
""",
        ),
        _text(
            "corpus/localisation/english/demo_l_english.yml",
            "localisation",
            "English names, English-only fallback, duplicate key, reference cycle, "
            "and dynamic text.",
            """# origin: synthetic
l_english:
 demo_echo_theory:0 "Echo Weaving"
 demo_prism_lattice:0 "Prismatic Lattice"
 demo_english_only:0 "English Only Signal"
 demo_cycle_a:0 "$demo_cycle_b$"
 demo_cycle_b:0 "$demo_cycle_a$"
 demo_dynamic:0 "Pilot [Root.GetName] sees $demo_prism_lattice$"
 demo_duplicate_loc:0 "English First"
 demo_duplicate_loc:0 "English Second"
""",
        ),
        _text(
            "corpus/localisation/korean/demo_l_korean.yml",
            "localisation",
            "Korean names plus a Korean-only key and dynamic/reference text.",
            """# origin: synthetic
l_korean:
 demo_echo_theory:0 "메아리 직조"
 demo_prism_lattice:0 "프리즘 격자"
 demo_korean_only:0 "한국어 전용 신호"
 demo_dynamic:0 "조종자 [Root.GetName]가 $demo_prism_lattice$ 관측"
""",
        ),
        _text(
            "corpus/localisation/korean/demo_l_korean_collision.yml",
            "collision",
            "A second Korean definition for the same localisation key.",
            """# origin: synthetic
l_korean:
 demo_prism_lattice:0 "프리즘 격자 대체안"
""",
        ),
        _text(
            "corpus/malformed/unclosed_string.txt",
            "error",
            "Quoted value deliberately reaches EOF without a closing quote.",
            """# origin: synthetic
demo_unclosed_string = {
    text = "this string never closes
}
""",
        ),
        _text(
            "corpus/malformed/unclosed_block.txt",
            "error",
            "Block deliberately reaches EOF before a closing brace.",
            """# origin: synthetic
demo_unclosed_block = {
    value = 10
    nested = {
        enabled = yes
    }
""",
        ),
        _text(
            "corpus/malformed/unsupported_operator.txt",
            "error",
            "Deliberately unsupported operator that must not receive invented semantics.",
            """# origin: synthetic
demo_unsupported_operator = {
    mystery ^= 42
}
""",
        ),
        _text(
            "corpus/snapshots/alpha/common/technology/00_demo_snapshot.txt",
            "collision",
            "Synthetic snapshot alpha defines demo_snapshot_probe differently from beta.",
            """# origin: synthetic
demo_snapshot_probe = {
    cost = 10
    marker = alpha
}
""",
        ),
        _text(
            "corpus/snapshots/beta/common/technology/00_demo_snapshot.txt",
            "collision",
            "Synthetic snapshot beta defines demo_snapshot_probe differently from alpha.",
            """# origin: synthetic
demo_snapshot_probe = {
    cost = 20
    marker = beta
}
""",
        ),
        Fixture(
            "corpus/encoding/bom_crlf.txt",
            "encoding",
            "utf-8-bom-crlf",
            "UTF-8 BOM and CRLF line endings with a quoted hash/brace payload.",
            b"\xef\xbb\xbf# origin: synthetic\r\ndemo_bom_crlf = {\r\n"
            b'    text = "# { stays text }"\r\n}\r\n',
        ),
        Fixture(
            "corpus/encoding/invalid_utf8.txt",
            "error",
            "invalid-utf8",
            "Deliberately invalid UTF-8 bytes after an ASCII synthetic-origin marker.",
            b"# origin: synthetic\ninvalid_bytes = \xff\xfe\x80\n",
        ),
        _text(
            "corpus/limits/depth_130.txt",
            "error",
            "130 nested blocks for a future default depth limit of 128.",
            deep,
        ),
    )


def manifest(fixtures_to_write: tuple[Fixture, ...]) -> dict[str, object]:
    files = []
    for fixture in sorted(fixtures_to_write, key=lambda item: item.path):
        files.append(
            {
                "path": fixture.path,
                "scenario": fixture.scenario,
                "encoding": fixture.encoding,
                "description": fixture.description,
                "size": len(fixture.content),
                "sha256": hashlib.sha256(fixture.content).hexdigest(),
            }
        )
    return {
        "schema_version": 1,
        "origin": "synthetic",
        "generator": "scripts/generate_synthetic_corpus.py",
        "provenance": (
            "All fixture names, values, strings, and expected scenario labels were "
            "authored for this project. No Stellaris game, DLC, mod, localisation, "
            "or save-file content was copied."
        ),
        "deterministic": True,
        "required_scenarios": ["normal", "error", "localisation", "collision"],
        "files": files,
    }


OWNER_ORIGIN = "synthetic"
OWNER_GENERATOR = "scripts/generate_synthetic_corpus.py"


def _safe_relative_path(value: str) -> Path:
    relative = Path(value)
    if relative.is_absolute() or ".." in relative.parts or not relative.parts:
        raise ValueError("manifest contains an unsafe managed path")
    if relative.parts[0] != "corpus":
        raise ValueError("managed fixture paths must remain under corpus/")
    return relative


def _validate_output_path(raw_output: Path) -> Path:
    if raw_output.is_symlink():
        raise ValueError("output path must not be a symbolic link")
    try:
        expanded = raw_output.expanduser()
        absolute = expanded if expanded.is_absolute() else Path.cwd() / expanded
        resolved = absolute.resolve(strict=False)
        repository_root = Path(__file__).resolve().parents[1]
        home = Path.home().resolve(strict=False)
    except (OSError, RuntimeError, ValueError) as exc:
        raise ValueError("output path cannot be resolved safely") from exc

    filesystem_root = Path(resolved.anchor)
    if resolved in {filesystem_root, repository_root, home}:
        raise ValueError("refusing a dangerous output root")
    return resolved


def _managed_target(output: Path, relative: Path) -> Path:
    current = output
    for part in relative.parts:
        current = current / part
        if current.is_symlink():
            raise ValueError("managed paths must not traverse symbolic links")
    return current


def _load_owned_paths(output: Path) -> set[str]:
    manifest_path = output / "manifest.json"
    if manifest_path.is_symlink():
        raise ValueError("synthetic manifest must not be a symbolic link")
    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FileExistsError(
            "non-empty output is not generator-owned: manifest.json is missing"
        ) from exc
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("existing synthetic manifest cannot prove ownership") from exc

    if data.get("origin") != OWNER_ORIGIN or data.get("generator") != OWNER_GENERATOR:
        raise ValueError("existing manifest is not owned by this synthetic generator")
    entries = data.get("files")
    if not isinstance(entries, list):
        raise ValueError("existing synthetic manifest has no valid files list")

    owned: set[str] = set()
    for entry in entries:
        if not isinstance(entry, dict) or not isinstance(entry.get("path"), str):
            raise ValueError("existing synthetic manifest contains an invalid file entry")
        relative = _safe_relative_path(entry["path"])
        owned.add(relative.as_posix())
    return owned


def _write_payload(output: Path, all_fixtures: tuple[Fixture, ...]) -> None:
    for fixture in all_fixtures:
        target = output / _safe_relative_path(fixture.path)
        target.parent.mkdir(parents=True, exist_ok=True)
        target.write_bytes(fixture.content)

    manifest_bytes = (
        json.dumps(manifest(all_fixtures), ensure_ascii=False, indent=2) + "\n"
    ).encode("utf-8")
    (output / "manifest.json").write_bytes(manifest_bytes)


def write_corpus(output: Path, *, force: bool = False) -> None:
    output = _validate_output_path(output)
    output.parent.mkdir(parents=True, exist_ok=True)

    if output.exists() and not output.is_dir():
        raise NotADirectoryError("output exists but is not a directory")

    existing_entries = list(output.iterdir()) if output.exists() else []
    owned: set[str] = set()
    if existing_entries:
        if not force:
            raise FileExistsError(
                f"output directory is not empty: {output}; pass --force to refresh owned files"
            )
        owned = _load_owned_paths(output)

    all_fixtures = fixtures()
    new_paths = {fixture.path for fixture in all_fixtures}

    for relative_text in sorted(owned | new_paths):
        relative = _safe_relative_path(relative_text)
        target = _managed_target(output, relative)
        if relative_text in new_paths and target.exists() and relative_text not in owned:
            raise FileExistsError(
                "refusing to overwrite an unmanaged file that collides with a generated path"
            )
        if target.exists() and target.is_dir():
            raise IsADirectoryError("managed fixture path unexpectedly became a directory")

    output.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=".stellaris-supporter-synthetic-", dir=output.parent
    ) as temp_dir:
        staging = Path(temp_dir) / "payload"
        staging.mkdir()
        _write_payload(staging, all_fixtures)

        for relative_text in sorted(owned - new_paths):
            target = _managed_target(output, _safe_relative_path(relative_text))
            if target.exists():
                target.unlink()

        for fixture in all_fixtures:
            relative = _safe_relative_path(fixture.path)
            target = _managed_target(output, relative)
            target.parent.mkdir(parents=True, exist_ok=True)
            os.replace(staging / relative, target)

        os.replace(staging / "manifest.json", output / "manifest.json")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", required=True, type=Path)
    parser.add_argument("--force", action="store_true")
    args = parser.parse_args()
    try:
        write_corpus(args.output, force=args.force)
    except (
        FileExistsError,
        IsADirectoryError,
        NotADirectoryError,
        OSError,
        RuntimeError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
