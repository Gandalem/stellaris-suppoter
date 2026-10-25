"""Bounded private desktop preferences; no game data is persisted here."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import uuid
from dataclasses import asdict, dataclass, field, replace
from pathlib import Path

from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.config import default_config_path, load_settings
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.storage.cache import _ensure_directory
from stellaris_supporter.weapon_cards import DEFAULT_FIELDS, FIELDS

HEX = re.compile(r"[0-9a-f]{64}\Z")
MAX_CARDS = 24


@dataclass
class Card:
    uid: str
    kind: str
    snapshot_id: str
    game_id: str
    entity_key: str | None = None
    domain: str = "technology"
    before_snapshot: str | None = None
    depth: int = 1
    fields: list[str] = field(default_factory=lambda: ["area", "tier", "cost", "prerequisites"])
    rect: list[int] = field(default_factory=lambda: [24, 24, 360, 260])

    @classmethod
    def create(cls, **values):
        if values.get("kind") == "weapon":
            values.setdefault("domain", "component_template")
            values.setdefault("fields", list(DEFAULT_FIELDS))
            values.setdefault("rect", [24, 24, 360, 300])
        return cls(uid=uuid.uuid4().hex, **values)


@dataclass
class Preferences:
    schema_version: int = 1
    game_root: str = ""
    executable: str = ""
    data_dir: str = ""
    language: str = "korean"
    toggle_hotkey: str = "Ctrl+Shift+Space"
    hide_hotkey: str = "Ctrl+Shift+H"
    opacity: int = 90
    close_to_tray: bool = False
    cards: list[Card] = field(default_factory=list)

    def validate(self):
        if self.schema_version != 1 or self.language not in {"korean", "english"}:
            raise ValueError("설정 형식 또는 언어가 올바르지 않습니다.")
        if type(self.opacity) is not int or not 30 <= self.opacity <= 100:
            raise ValueError("투명도는 30~100 사이여야 합니다.")
        if type(self.close_to_tray) is not bool or len(self.cards) > MAX_CARDS:
            raise ValueError("카드/트레이 설정이 올바르지 않습니다.")
        for value in (self.game_root, self.executable, self.data_dir):
            if not isinstance(value, str) or len(value) > 4096 or "\x00" in value:
                raise ValueError("경로가 올바르지 않습니다.")
            if value and not Path(value).is_absolute():
                raise ValueError("절대 경로를 지정해주세요.")
        seen = set()
        for card in self.cards:
            if (card.kind not in {"technology", "reference", "diff", "weapon"}
                    or (card.kind == "weapon" and (card.domain != "component_template" or card.entity_key is None
                        or card.before_snapshot is not None or card.depth != 1
                        or len(set(card.fields)) != len(card.fields) or any(v not in FIELDS for v in card.fields)))
                    or (card.kind != "weapon" and card.domain not in {"technology", "event"})
                    or not HEX.fullmatch(card.snapshot_id)
                    or card.entity_key is not None and not HEX.fullmatch(card.entity_key)
                    or card.before_snapshot is not None and not HEX.fullmatch(card.before_snapshot)
                    or card.kind == "diff" and card.before_snapshot is None
                    or type(card.depth) is not int or not 1 <= card.depth <= 16
                    or not isinstance(card.game_id, str) or len(card.game_id) > 512
                    or not re.fullmatch(r"[0-9a-f]{32}", card.uid) or card.uid in seen
                    or len(card.rect) != 4 or any(type(n) is not int or abs(n) > 100000 for n in card.rect)
                    or len(card.fields) > 20 or any(not isinstance(v, str) or len(v) > 80 for v in card.fields)):
                raise ValueError("카드 설정이 올바르지 않습니다.")
            seen.add(card.uid)
        return self

    def services(self):
        base = load_settings(default_config_path()).settings
        return replace(base, game_root=Path(self.game_root) if self.game_root else base.game_root,
                       data_dir=Path(self.data_dir) if self.data_dir else base.data_dir,
                       language=self.language, network_enabled=False)


def preferences_path():
    return default_config_path().with_name("desktop.json")


def load_preferences(path: Path | None = None):
    path = path or preferences_path()
    _check_components(path)
    if not path.exists():
        base = load_settings(default_config_path()).settings
        return Preferences(game_root=str(base.game_root or ""), data_dir=str(base.data_dir),
                           language=base.language if base.language in {"korean", "english"} else "korean")
    if path.stat().st_size > 256 * 1024:
        raise ValueError("설정 파일이 너무 큽니다.")
    raw = path.read_bytes()
    data = json.loads(raw.decode("utf-8"))
    cards = []
    for item in data.get("cards", []):
        item = dict(item)
        if item.get("kind") == "weapon":
            item.setdefault("domain", "component_template")
            item.setdefault("fields", list(DEFAULT_FIELDS))
            item.setdefault("rect", [24, 24, 360, 300])
        cards.append(Card(**item))
    data["cards"] = cards
    prefs = Preferences(**data).validate()
    prefs._loaded_digest = hashlib.sha256(raw).hexdigest()
    return prefs


def save_preferences(prefs: Preferences, path: Path | None = None):
    prefs.validate()
    path = path or preferences_path()
    service = prefs.services()
    for protected in (service.game_root,):
        if protected and (path == protected or protected in path.parents):
            raise ValueError("설정은 게임 폴더 밖에 저장해야 합니다.")
    _check_components(path)
    _ensure_directory(path.parent)
    raw = json.dumps(asdict(prefs), ensure_ascii=False, indent=2).encode("utf-8")
    if len(raw) > 256 * 1024:
        raise ValueError("설정 파일이 너무 큽니다.")
    fd, temp = tempfile.mkstemp(prefix="desktop-", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        _check_components(path)
        os.replace(temp, path)
    finally:
        Path(temp).unlink(missing_ok=True)


def card_identity(card):
    return (card.kind, card.snapshot_id, card.game_id, card.entity_key,
            card.domain, card.before_snapshot, card.depth)


def split_duplicate_cards(cards):
    kept, duplicates, seen = [], [], set()
    for card in cards:
        key = (card_identity(card), tuple(card.fields))
        if key in seen:
            duplicates.append(card)
        else:
            kept.append(card)
            seen.add(key)
    return kept, duplicates


def preference_digest(path):
    _check_components(path)
    if not path.exists():
        return None
    if path.stat().st_size > 256 * 1024:
        raise ValueError("설정 파일이 너무 큽니다.")
    return hashlib.sha256(path.read_bytes()).hexdigest()


class PreferencesStore:
    """Short per-path write lock and compare-before-replace, preserving external edits."""
    def __init__(self, path, prefs):
        self.path = path
        self.expected = getattr(prefs, "_loaded_digest", preference_digest(path))
        self.backup = None
        self.weapon_backed_up = any(card.kind == "weapon" for card in prefs.cards)

    def save(self, prefs):
        from PySide6.QtCore import QLockFile
        prefs.validate()
        protected = prefs.services().game_root
        if protected and (self.path == protected or protected in self.path.parents):
            raise ValueError("설정은 게임 폴더 밖에 저장해야 합니다.")
        _check_components(self.path)
        _ensure_directory(self.path.parent)
        lock_path = self.path.with_name(self.path.name + ".write.lock")
        _check_components(lock_path)
        lock = QLockFile(str(lock_path))
        if not lock.tryLock(0):
            raise SnapshotError("PREFERENCES_BUSY", "Another settings writer is active.")
        try:
            if preference_digest(self.path) != self.expected:
                raise SnapshotError("PREFERENCES_CHANGED", "Settings changed; reload before saving.")
            if not self.weapon_backed_up and any(card.kind == "weapon" for card in prefs.cards):
                if self.path.exists():
                    backup = self.path.with_name(self.path.stem + ".before-weapons-" + uuid.uuid4().hex[:8] + ".json")
                    _check_components(backup)
                    raw = self.path.read_bytes()
                    with backup.open("xb") as stream:
                        stream.write(raw)
                        stream.flush()
                        os.fsync(stream.fileno())
                    self.backup = backup
                self.weapon_backed_up = True
            save_preferences(prefs, self.path)
            self.expected = preference_digest(self.path)
        finally:
            lock.unlock()
