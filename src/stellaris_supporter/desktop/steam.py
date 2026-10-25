"""Read Steam registry/library manifests only; never crawl drives or start indexing."""
from __future__ import annotations

import os
import re
from pathlib import Path

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.storage import SnapshotError

_TOKEN = re.compile(r'\s+|//[^\n]*|"((?:[^"\\]|\\.)*)"|([{}])')


def read_vdf(path: Path):
    _check_components(path)
    if path.stat().st_size > 1024 * 1024:
        raise ValueError("Steam manifest exceeds bound")
    text = path.read_bytes().decode("utf-8-sig")
    tokens = []
    offset = 0
    for match in _TOKEN.finditer(text):
        if match.start() != offset:
            raise ValueError("Unsupported Steam manifest syntax")
        offset = match.end()
        if match.group(1) is not None:
            value = re.sub(r'\\(["\\])', r'\1', match.group(1))
            tokens.append(("string", value))
        elif match.group(2):
            tokens.append((match.group(2), match.group(2)))
        if len(tokens) > 50000:
            raise ValueError("Steam manifest token bound")
    if offset != len(text):
        raise ValueError("Malformed Steam manifest")
    position = 0

    def pairs(depth=0):
        nonlocal position
        if depth > 16:
            raise ValueError("Steam manifest depth bound")
        result = []
        while position < len(tokens) and tokens[position][0] != "}":
            kind, key = tokens[position]
            position += 1
            if kind != "string" or position >= len(tokens):
                raise ValueError("Missing Steam manifest value")
            kind, value = tokens[position]
            position += 1
            if kind == "{":
                value = pairs(depth+1)
                if position >= len(tokens) or tokens[position][0] != "}":
                    raise ValueError("Unclosed Steam manifest")
                position += 1
            elif kind != "string":
                raise ValueError("Invalid Steam manifest value")
            result.append((key, value))
        return result
    result = pairs()
    if position != len(tokens):
        raise ValueError("Unexpected Steam manifest close")
    return result


def _one(pairs, key):
    values = [v for k, v in pairs if k.casefold() == key.casefold()]
    if len(values) != 1:
        raise ValueError("Missing/ambiguous Steam manifest key")
    return values[0]


def steam_roots():
    roots = []
    if os.name == "nt":
        import winreg
        for hive, key, name in ((winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath"),
                                (winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath")):
            try:
                with winreg.OpenKey(hive, key) as handle:
                    roots.append(Path(winreg.QueryValueEx(handle, name)[0]))
            except OSError:
                continue
        for env in ("ProgramFiles(x86)", "ProgramFiles"):
            if os.environ.get(env):
                roots.append(Path(os.environ[env]) / "Steam")
    return tuple(dict.fromkeys(roots))


def discover_installations(roots=None):
    libraries = list(steam_roots() if roots is None else roots)
    for root in tuple(libraries):
        try:
            entries = _one(read_vdf(root / "steamapps" / "libraryfolders.vdf"), "libraryfolders")
            for key, value in entries:
                if key.isdigit():
                    raw = _one(value, "path") if isinstance(value, list) else value
                    candidate = Path(raw)
                    if candidate.is_absolute() and len(libraries) < 128:
                        libraries.append(candidate)
        except (OSError, ValueError, TypeError, SnapshotError):
            continue
    found = []
    for library in dict.fromkeys(libraries):
        try:
            state = _one(read_vdf(library / "steamapps" / "appmanifest_281990.acf"), "AppState")
            if _one(state, "appid") != "281990":
                continue
            name = _one(state, "installdir")
            if not isinstance(name, str) or name in {"", ".", ".."} or any(c in name for c in '/\\:'):
                continue
            root = library / "steamapps" / "common" / name
            _check_components(root)
            if (root / "common" / "technology").is_dir() and (root / "stellaris.exe").is_file():
                found.append(root)
        except (OSError, ValueError, TypeError, SnapshotError):
            continue
    return tuple(dict.fromkeys(found))
