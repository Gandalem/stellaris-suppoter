"""Race-safe first-run configuration creation, independent of load_settings()."""
from __future__ import annotations

import json
import os
import stat
import tempfile
from pathlib import Path

from stellaris_supporter.config import default_config_path, default_data_dir, paths_overlap
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.cache import _ensure_directory


def _check_components(path: Path) -> None:
    """Reject symlink and Windows reparse components without resolving them away."""
    absolute = Path(os.path.abspath(path.expanduser()))
    for component in (*reversed(absolute.parents), absolute):
        try:
            info = component.lstat()
        except FileNotFoundError:
            continue
        except OSError as exc:
            raise SnapshotError("PATH_REJECTED", "A configuration path is inaccessible.") from exc
        if stat.S_ISLNK(info.st_mode) or (
            int(getattr(info, "st_file_attributes", 0)) &
            getattr(stat, "FILE_ATTRIBUTE_REPARSE_POINT", 0x400)
        ):
            raise SnapshotError("PATH_REJECTED", "Configuration path contains a link.")


def initialise_config(
    *, config: Path | None, game_root: str | None,
    data_dir: str | None, language: str | None,
) -> dict[str, object]:
    if not game_root:
        raise SnapshotError("QUERY_INVALID", "init requires --game-root.")
    if language is not None and language.lower() not in {"ko", "en", "korean", "english"}:
        raise SnapshotError("QUERY_INVALID", "init supports Korean or English.")
    if "\x00" in game_root or (data_dir is not None and "\x00" in data_dir):
        raise SnapshotError("PATH_REJECTED", "A configured path is invalid.")

    target = Path(os.path.abspath((config or default_config_path()).expanduser()))
    game = Path(os.path.abspath(Path(game_root).expanduser()))
    private = Path(os.path.abspath(Path(data_dir).expanduser()
                                   if data_dir is not None else default_data_dir()))
    for location in (target, game, private):
        _check_components(location)
    if not game.is_dir():
        raise SnapshotError("GAME_ROOT_MISSING", "Requested game root does not exist.")
    if paths_overlap(game, private):
        raise SnapshotError("PATH_REJECTED", "Private data must be outside the game root.")
    if target.exists() or target.is_symlink():
        raise SnapshotError("CONFIG_EXISTS", "Configuration already exists.")
    if target.is_relative_to(game):
        raise SnapshotError("PATH_REJECTED", "Configuration must be outside the game root.")

    # Create only private directories, never any game path.
    _ensure_directory(target.parent)
    _ensure_directory(private)
    _check_components(target)
    if target.exists() or target.is_symlink():
        raise SnapshotError("CONFIG_EXISTS", "Configuration already exists.")

    toml = (
        "schema_version = 1\n"
        f"game_root = {json.dumps(str(game), ensure_ascii=False)}\n"
        f"data_dir = {json.dumps(str(private), ensure_ascii=False)}\n"
        f"language = {json.dumps((language or 'ko').lower())}\n"
        "[network]\nenabled = false\n"
    ).encode("utf-8")

    temporary: str | None = None
    published = False
    try:
        fd, temporary = tempfile.mkstemp(prefix=".config-pending-", dir=target.parent)
        try:
            if os.name == "posix":
                os.fchmod(fd, 0o600)
            with os.fdopen(fd, "wb") as out:
                out.write(toml)
                out.flush()
                os.fsync(out.fileno())
        except BaseException:
            # fdopen owns/closed fd after entering; os.close only if not wrapped.
            raise
        # Same-directory exclusive atomic publication, no overwrite race.
        try:
            os.link(temporary, target)
        except FileExistsError as exc:
            raise SnapshotError("CONFIG_EXISTS", "Configuration already exists.") from exc
        except OSError as exc:
            raise SnapshotError("CONFIG_WRITE_ERROR", "Atomic configuration publication failed.") from exc
        published = True
    except SnapshotError:
        raise
    except OSError as exc:
        raise SnapshotError("CONFIG_WRITE_ERROR", "Configuration write failed.") from exc
    finally:
        if temporary is not None:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass
            except OSError:
                if not published:
                    # Do not replace a failed init with a second unsafe write.
                    pass
    return {
        "schema_version": 1,
        "status": "ok", "command": "init",
        "network_enabled": False, "language": (language or "ko").lower(),
        "created": True, "diagnostics": [],
    }
