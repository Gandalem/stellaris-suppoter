"""Single DB/service owner thread. Requests and responses contain data, never widgets."""
from __future__ import annotations

import hashlib
import os
from dataclasses import asdict

from PySide6.QtCore import QObject, Signal, Slot

from stellaris_supporter.card_information import CardInformation
from stellaris_supporter.cli_index import index_technologies
from stellaris_supporter.comparison import DiffQuery, DiffService
from stellaris_supporter.domain import SourceRef
from stellaris_supporter.references import ReferenceQuery, ReferenceService
from stellaris_supporter.retrieval import Query, SearchService
from stellaris_supporter.storage import SnapshotError, SnapshotRepository
from stellaris_supporter.weapons import WeaponService

from .diagnostics import record_error


class Worker(QObject):
    result = Signal(object)
    closed = Signal()
    progress = Signal(object)

    def __init__(self, latest):
        super().__init__()
        self.latest = latest
        self.settings = self.repo = self.search = None
        self.card_information = None
        self.weapons = None

    def configure(self, settings):
        if self.settings != settings:
            if self.weapons is not None:
                self.weapons.close()
            if self.card_information is not None:
                self.card_information.close()
            if self.search is not None:
                self.search.close()
            self.search = self.repo = None
            self.repo = SnapshotRepository(settings.data_dir, game_root=settings.game_root)
            self.search = SearchService(self.repo, error_reporter=
                                        lambda stage, error: record_error(settings.data_dir, stage, error, self.storage_state()))
            self.card_information = CardInformation(self.repo, self.search)
            self.weapons = WeaponService(self.repo, self.card_information)
            self.settings = settings

    def storage_state(self):
        if self.repo is None:
            return {}
        state = {"path_hash": hashlib.sha256(os.path.normcase(str(self.repo.db_path)).encode()).hexdigest()}
        try:
            stat = self.repo.db_path.stat()
            state.update(file_id=str(stat.st_ino), file_size=stat.st_size)
            with self.repo._connection(read_only=True) as connection:
                rows = connection.execute("SELECT status,count(*) FROM snapshots GROUP BY status").fetchall()
                state["snapshots"] = {row[0]: row[1] for row in rows}
                active = connection.execute("SELECT value FROM settings WHERE key='active_snapshot'").fetchone()
                state["active_snapshot"] = active[0] if active else None
        except (OSError, SnapshotError):
            state["unavailable"] = True
        return state

    def answer(self, payload):
        return self.card_information.answer(payload, self.settings.language)

    def card_request(self, card):
        return {**{k: card.get(k) for k in ("uid", "snapshot_id", "game_id", "entity_key")},
                "language": self.settings.language}

    def weapon_detail(self, payload):
        data = self.weapons.detail(payload, self.settings.language)
        identity = data.get("identity")
        if identity and (identity["snapshot_id"] != payload["snapshot_id"]
                         or payload.get("game_id") and identity["game_id"] != payload["game_id"]):
            raise SnapshotError("QUERY_INVALID", "Weapon identity does not match the request.")
        return data

    def perform(self, kind, p):
        if kind == "snapshots":
            rows, truncated = self.repo.list_snapshots(limit=100)
            return {"rows": rows, "truncated": truncated, "active": self.repo.active_snapshot_id(),
                    "storage": self.storage_state()}
        if kind == "index":
            return index_technologies(self.repo, self.settings,
                                      include_events=p.get("events", False),
                                      allow_partial=p.get("partial", False), full=p.get("full", False),
                                      cancel=p["cancel"].is_set, progress=self.progress.emit)
        if kind == "search":
            return asdict(self.search.search(Query(p["text"], snapshot_id=p.get("snapshot_id"),
                                                  language=self.settings.language)))
        if kind == "weapons":
            return self.weapons.search(p, self.settings.language)
        if kind == "weapon_detail":
            return self.weapon_detail(p)
        if kind == "pin_target":
            return (self.answer(p) if p["target_kind"] == "technology"
                    else self.weapon_detail(p))
        if kind == "answer":
            return self.answer(p)
        if kind == "refs":
            return ReferenceService(self.repo).refs(ReferenceQuery(**p)).to_dict()
        if kind == "diff":
            return DiffService(self.repo).compare(DiffQuery(**p)).to_dict()
        if kind == "source":
            return ReferenceService(self.repo).source_text(SourceRef(**p))
        if kind == "card_preview":
            if p["before"].get("kind") == "weapon" and p["after"].get("kind") == "weapon":
                return {"before": self.weapon_detail(p["before"]),
                        "after": self.weapon_detail(p["after"])}
            return {"before": self.answer(p["before"]), "after": self.answer(p["after"])}
        if kind == "card":
            card = p["card"]
            if card["kind"] == "weapon":
                if card.get("domain") != "component_template" or not card.get("entity_key"):
                    raise SnapshotError("QUERY_INVALID", "Weapon card requires an exact definition.")
                return {**self.weapon_detail(card), "card_request": self.card_request(card)}
            if card["kind"] == "technology":
                return {**self.answer(card), "card_request": self.card_request(card)}
            if card["kind"] == "reference":
                return ReferenceService(self.repo).refs(ReferenceQuery(
                    card["game_id"], card["domain"], card["snapshot_id"], card["entity_key"], card["depth"], 20)).to_dict()
            if card["kind"] == "diff":
                return DiffService(self.repo).compare(DiffQuery(
                    card["before_snapshot"], card["snapshot_id"], kind=card["domain"],
                    game_id=card["game_id"] or None)).to_dict()
            raise SnapshotError("QUERY_INVALID", "Unknown card kind.")
        raise ValueError("Unknown job")

    @Slot(object)
    def run(self, job):
        channel = job["channel"]
        if self.latest.get(channel) != job["id"]:
            return
        try:
            self.configure(job["settings"])
            data = self.perform(job["kind"], job["payload"])
            if isinstance(data, dict) and data.get("status") == "error":
                codes = [item.get("code") for item in data.get("diagnostics", ())]
                code = next((value for value in codes if isinstance(value, str)), "SERVICE_ERROR")
                record_error(job["settings"].data_dir, job["kind"] + "_response",
                             SnapshotError(code, "Service returned an error response."), self.storage_state())
            response = {**job, "data": data, "error": None}
        except Exception as exc:
            if job.get("settings"):
                record_error(job["settings"].data_dir, job["kind"], exc)
            # No arbitrary exception repr, game bytes or private paths in public diagnostics.
            code = exc.code if isinstance(exc, SnapshotError) else type(exc).__name__
            response = {**job, "data": None, "error": code}
        if self.latest.get(channel) == job["id"]:
            self.result.emit(response)

    @Slot()
    def stop(self):
        if self.weapons is not None:
            self.weapons.close()
        if self.card_information is not None:
            self.card_information.close()
        if self.search is not None:
            self.search.close()
        self.search = self.repo = None
        self.closed.emit()
