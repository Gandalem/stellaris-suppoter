"""Local desktop manager and independent small native card windows."""
from __future__ import annotations

import argparse
import copy
import ctypes
import os
import subprocess
import sys
import uuid
from dataclasses import asdict, replace
from pathlib import Path
from threading import Event

from PySide6.QtCore import QAbstractNativeEventFilter, QObject, Qt, QThread, QTimer, Signal
from PySide6.QtGui import QAction, QColor, QIcon, QPainter, QPixmap
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QDialog,
    QFileDialog,
    QFormLayout,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMenu,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizeGrip,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QStackedWidget,
    QSystemTrayIcon,
    QVBoxLayout,
    QWidget,
)

from stellaris_supporter.card_information import field_text, readable_detail
from stellaris_supporter.cli_setup import _check_components
from stellaris_supporter.config import paths_overlap
from stellaris_supporter.storage import SnapshotError
from stellaris_supporter.weapon_cards import FIELDS as WEAPON_FIELDS
from stellaris_supporter.weapon_cards import preview_text
from stellaris_supporter.weapon_cards import project as weapon_view

from .model import Mode, OverlayState, bounded_rect, place_card
from .presentation import STATUS, collect_sources, search_error_text, source_label, text_view
from .settings import (
    MAX_CARDS,
    Card,
    PreferencesStore,
    card_identity,
    load_preferences,
    preferences_path,
    save_preferences,
    split_duplicate_cards,
)
from .steam import discover_installations
from .technology_card import FieldsDialog, LimitedLabel, TechnologySummary
from .weapon_browser import WeaponBrowser
from .weapon_card import WeaponSummary
from .windows import Windows, parse_hotkey
from .worker import Worker

STYLE = """
QWidget {background:#171d25; color:#e4eaf2; font-family:'Segoe UI'; font-size:14px;}
QMainWindow {background:#10161e;}
QLabel#title {font-size:26px; font-weight:600; color:#c8e9ff;}
QListWidget,QPlainTextEdit,QLineEdit,QComboBox,QSpinBox {background:#101720; border:1px solid #324457; border-radius:5px; padding:7px;}
QPushButton {background:#25374a; border:1px solid #45617b; border-radius:5px; padding:8px 15px;}
QPushButton:hover {background:#375571;} QPushButton:disabled {color:#6b7a89;}
QListWidget::item {padding:9px;} QListWidget::item:selected {background:#294964;}
QFrame#card {border:1px solid #547b96; border-radius:8px; background:#172330;}
QLabel#muted {color:#92a9bd;}
"""


def label(text, name=None):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(True)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, layout):
    widget = QPushButton(text)
    widget.clicked.connect(callback)
    layout.addWidget(widget)
    return widget


def readonly():
    widget = QPlainTextEdit()
    widget.setReadOnly(True)
    return widget


def plain_question(parent, title, text):
    box = QMessageBox(parent)
    box.setWindowTitle(title)
    box.setIcon(QMessageBox.Icon.Question)
    box.setTextFormat(Qt.TextFormat.PlainText)
    box.setText(text)
    box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel)
    box.setDefaultButton(QMessageBox.StandardButton.Cancel)
    return box.exec()


class Bus(QObject):
    request = Signal(object)
    stop = Signal()


class Hotkeys(QAbstractNativeEventFilter):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager

    def nativeEventFilter(self, event_type, message):
        if os.name == "nt" and self.manager.native:
            from ctypes.wintypes import MSG
            event = MSG.from_address(int(message))
            if event.message == 0x0312:
                binding = self.manager.native.registrations.get(int(event.wParam))
                if binding:
                    QTimer.singleShot(0, self.manager.toggle_overlay if binding[1] == "toggle" else self.manager.hide_overlay)
                    return True, 0
        return False, 0


class CardWindow(QFrame):
    def __init__(self, manager, card):
        super().__init__(None)
        self.manager, self.card = manager, card
        self.mode = None
        self.drag = None
        self.geometry_pending = False
        self.setObjectName("card")
        self.setStyleSheet(STYLE)
        self.setMinimumSize(220, 160) if card.kind == "weapon" else self.setMinimumSize(180, 100)
        layout = QVBoxLayout(self)
        self.data = None
        layout.setContentsMargins(10, 10, 10, 10)
        layout.setSpacing(5)
        self.header = LimitedLabel(card.game_id or "변경 비교")
        self.header.mousePressEvent = self.press
        self.header.mouseMoveEvent = self.move_drag
        self.header.mouseReleaseEvent = self.release_drag
        layout.addWidget(self.header)
        self.body = readonly()
        self.content = QStackedWidget()
        self.content.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        self.summary = WeaponSummary() if card.kind == "weapon" else TechnologySummary()
        self.content.addWidget(self.body)
        self.content.addWidget(self.summary)
        layout.addWidget(self.content, 1)
        self.editing = label("편집 중", "muted")
        self.actions = QWidget()
        actions = QHBoxLayout(self.actions)
        actions.setContentsMargins(0, 0, 0, 0)
        actions.addWidget(self.editing)
        self.detail_button = button("상세 보기", lambda: manager.open_card_detail(card.uid), actions)
        self.links_button = None
        if card.kind == "weapon":
            self.links_button = button("연결 보기", lambda: manager.open_card_detail(card.uid, connections=True), actions)
        menu_button = button("카드 관리", lambda: None, actions)
        menu = QMenu(menu_button)
        for title, callback in (("카드 관리", lambda: manager.manage_card(card.uid)),
                                ("표시 항목", lambda: manager.edit_card_fields(card.uid)),
                                ("다시 읽기", lambda: manager.refresh_card_data([card.uid])),
                                ("고정 해제", lambda: manager.remove_card_uid(card.uid))):
            menu.addAction(title, callback)
        if card.kind == "weapon":
            menu.addAction("연결 보기", lambda: manager.open_card_detail(card.uid, connections=True))
        menu_button.setMenu(menu)
        for i in range(actions.count()):
            widget = actions.itemAt(i).widget()
            if isinstance(widget, QPushButton):
                widget.setStyleSheet("padding:3px 5px;")
        self.actions.hide()
        self.grip = QSizeGrip(self)
        actions.addWidget(self.grip)
        layout.addWidget(self.actions)
        self.debounce = QTimer(self)
        self.debounce.setSingleShot(True)
        self.debounce.timeout.connect(self.persist_geometry)

    def set_data(self, data):
        self.data = data
        if self.card.kind == "weapon":
            view = weapon_view(data)
            if view:
                self.header.setText(view["name"])
                self.summary.set_data(view, self.card.fields, self.card.snapshot_id != self.manager.active_snapshot)
                self.content.setCurrentWidget(self.summary)
            else:
                self.header.setText(self.card.game_id)
                self.body.setPlainText("자료 읽기 실패 · 편집 모드에서 다시 읽기 또는 카드 관리")
                self.content.setCurrentWidget(self.body)
            return
        self.body.setPlainText(text_view(data, self.card.fields))
        view = data.get("card_view")
        if self.card.kind == "technology" and view:
            self.header.setText(view["name"])
            self.summary.set_data(view, self.card.fields)
            self.content.setCurrentWidget(self.summary)
        else:
            self.content.setCurrentWidget(self.body)

    def press(self, event):
        if self.mode == Mode.INTERACTIVE and event.button() == Qt.MouseButton.LeftButton:
            self.drag = event.globalPosition().toPoint() - self.pos()

    def move_drag(self, event):
        if self.drag is not None:
            self.move(event.globalPosition().toPoint()-self.drag)

    def release_drag(self, event):
        self.drag = None
        self.persist_geometry()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if hasattr(self, "actions"):
            self.editing.setVisible(self.width() >= 420)
            if self.links_button:
                self.links_button.setVisible(self.width() >= 340)
        if hasattr(self, "debounce") and self.mode == Mode.INTERACTIVE:
            if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
                self.geometry_pending = True
            self.debounce.start(300)

    def persist_geometry(self):
        if self.mode != Mode.INTERACTIVE or not self.manager.target or not self.isVisible():
            return
        if QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.debounce.start(150)
            return
        from ctypes.wintypes import RECT
        rect = RECT()
        self.manager.native.user.GetWindowRect(int(self.winId()), ctypes.byref(rect))
        tx, ty, tw, th = self.manager.target.rect
        scale = self.manager.target.dpi/96
        before = list(self.card.rect)
        self.card.rect = list(bounded_rect((round((rect.left-tx)/scale), round((rect.top-ty)/scale),
                                           round((rect.right-rect.left)/scale), round((rect.bottom-rect.top)/scale)),
                                          round(tw/scale), round(th/scale)))
        self.geometry_pending = False
        if not self.manager.save():
            self.card.rect = before

    def present(self, mode, target):
        if mode == Mode.HIDDEN:
            self.hide()
            self.mode = mode
            return
        if self.mode != mode:
            flags = Qt.WindowType.Tool | Qt.WindowType.FramelessWindowHint | Qt.WindowType.WindowStaysOnTopHint
            if mode == Mode.PASSIVE:
                flags |= Qt.WindowType.WindowTransparentForInput | Qt.WindowType.WindowDoesNotAcceptFocus
            self.setWindowFlags(flags)
            self.setAttribute(Qt.WidgetAttribute.WA_ShowWithoutActivating, True)
            self.body.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents, mode == Mode.PASSIVE)
            self.grip.setVisible(mode == Mode.INTERACTIVE)
            self.actions.setVisible(mode == Mode.INTERACTIVE)
            self.mode = mode
        if self.geometry_pending and not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            self.persist_geometry()
        self.setWindowOpacity(self.manager.prefs.opacity/100)
        scale = target.dpi/96
        tx, ty, tw, th = target.rect
        rect = bounded_rect(self.card.rect, round(tw/scale), round(th/scale))
        self.show()
        self.manager.native.passive(int(self.winId()), mode == Mode.PASSIVE)
        if not QApplication.mouseButtons() & Qt.MouseButton.LeftButton:
            x, y, w, h = rect
            self.manager.native.user.SetWindowPos(int(self.winId()), -1, tx+round(x*scale), ty+round(y*scale),
                                                  round(w*scale), round(h*scale), 0x10)

    def closeEvent(self, event):
        event.ignore()
        self.manager.hide_overlay()


class Manager(QMainWindow):
    def __init__(self, prefs, preference_file=None):
        super().__init__()
        self.prefs, self.preference_file = prefs, preference_file
        self.preference_store = PreferencesStore(preference_file or preferences_path(), prefs)
        self.settings_epoch = 0
        self.pending_pins = set()
        self.native = Windows() if os.name == "nt" else None
        self.state = OverlayState()
        self.target = None
        self.cards = {}
        self.active_snapshot = None
        self.snapshots_loaded = False
        self.current_hit = self.current_refs = self.current_diff = None
        self.callbacks, self.latest, self.serial = {}, {}, 0
        self.index_cancel = None
        self.query_revision = 0
        self.index_query_revision = None
        self.exiting = self.allow_close = False
        self.setWindowTitle("Stellaris Supporter")
        self.resize(1180, 780)
        self.setStyleSheet(STYLE)
        content = QWidget()
        self.setCentralWidget(content)
        outer = QHBoxLayout(content)
        self.nav = QListWidget()
        self.nav.setFixedWidth(185)
        self.stack = QStackedWidget()
        self.page_indices = {}
        outer.addWidget(self.nav)
        outer.addWidget(self.stack, 1)
        self.build_home()
        self.build_search()
        self.build_weapons()
        self.build_refs()
        self.build_diff()
        self.build_cards()
        self.build_settings()
        self.nav.currentRowChanged.connect(self.changed_page)
        self.navigate("홈")
        self.bus = Bus()
        self.thread = QThread(self)
        self.worker = Worker(self.latest)
        self.worker.moveToThread(self.thread)
        self.bus.request.connect(self.worker.run)
        self.bus.stop.connect(self.worker.stop)
        self.worker.result.connect(self.result)
        self.worker.closed.connect(self.thread.quit)
        self.worker.closed.connect(self.worker.deleteLater)
        self.thread.finished.connect(self.finished_exit)
        self.thread.start()
        self.index_bus = Bus()
        self.index_thread = QThread(self)
        self.index_worker = Worker(self.latest)
        self.index_worker.moveToThread(self.index_thread)
        self.index_bus.request.connect(self.index_worker.run)
        self.index_bus.stop.connect(self.index_worker.stop)
        self.index_worker.result.connect(self.result)
        self.index_worker.progress.connect(self.index_progress)
        self.index_worker.closed.connect(self.index_thread.quit)
        self.index_worker.closed.connect(self.index_worker.deleteLater)
        self.index_thread.finished.connect(self.finished_exit)
        self.index_thread.start()
        self.tray = QSystemTrayIcon(self.make_icon(), self)
        menu = QMenu()
        for title, callback in (("관리창 열기", self.open_manager), ("오버레이 숨기기", self.hide_overlay), ("종료", self.exit_app)):
            action = QAction(title, self)
            action.triggered.connect(callback)
            menu.addAction(action)
        self.tray.setContextMenu(menu)
        self.tray.activated.connect(lambda reason: self.open_manager() if reason == QSystemTrayIcon.ActivationReason.DoubleClick else None)
        self.tray.show()
        self.native_filter = Hotkeys(self)
        QApplication.instance().installNativeEventFilter(self.native_filter)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.poll_game)
        self.timer.start(350)
        self.rebuild_cards()
        QTimer.singleShot(0, self.initialise)

    def make_icon(self):
        pix = QPixmap(32, 32)
        pix.fill(QColor("#152637"))
        painter = QPainter(pix)
        painter.setPen(QColor("#9edfff"))
        painter.drawText(pix.rect(), Qt.AlignmentFlag.AlignCenter, "S")
        painter.end()
        return QIcon(pix)

    def page(self, name, title):
        page = QWidget()
        layout = QVBoxLayout(page)
        layout.addWidget(label(title, "title"))
        self.page_indices[name] = self.stack.count()
        self.nav.addItem(name)
        self.stack.addWidget(page)
        return layout

    def navigate(self, name):
        self.nav.setCurrentRow(self.page_indices[name])

    def changed_page(self, index):
        self.stack.setCurrentIndex(index)
        if index == self.page_indices.get("무기 검색"):
            self.weapon_browser.enter()

    def build_weapons(self):
        layout = self.page("무기 검색", "무기 · 관련 기술")
        self.weapon_browser = WeaponBrowser(self)
        layout.addWidget(self.weapon_browser)

    def initialise(self):
        if self.exiting:
            return
        self.discover(auto=True)
        if self.native:
            try:
                self.native.bind_hotkeys(int(self.winId()), self.prefs.toggle_hotkey, self.prefs.hide_hotkey)
            except ValueError as exc:
                self.notify(str(exc))
        self.refresh_snapshots()
        self.refresh_card_data()

    def notify(self, text):
        self.statusBar().showMessage(text)

    def submit(self, kind, payload, callback, channel=None):
        if self.exiting:
            return
        self.serial += 1
        channel = channel or kind
        old = self.latest.get(channel)
        self.callbacks.pop(old, None)
        self.latest[channel] = self.serial
        self.callbacks[self.serial] = callback
        bus = self.index_bus if kind == "index" else self.bus
        bus.request.emit({"id": self.serial, "channel": channel, "kind": kind,
                               "payload": payload, "settings": self.prefs.services()})

    def result(self, job):
        callback = self.callbacks.pop(job["id"], None)
        if callback is None or self.latest.get(job["channel"]) != job["id"]:
            return
        if job["error"]:
            if job["kind"] == "card":
                card = job["payload"]["card"]
                callback({"status": "error", "results": [], "diagnostics": [{"code": job["error"]}],
                          "card_request": {**{key: card.get(key) for key in ("uid", "snapshot_id", "game_id", "entity_key")},
                                           "language": job["settings"].language}})
                return
            if job["kind"] in {"search", "weapons", "weapon_detail", "pin_target", "card_preview"}:
                callback({"status": "error", "results": [], "diagnostics": [{"code": job["error"]}]})
                return
            self.notify("작업을 완료하지 못했습니다: " + job["error"])
            if job["kind"] == "index":
                self.index_done(None)
                if job["error"] == "PARTIAL_INDEX":
                    choice = QMessageBox.question(
                        self, "읽은 데이터 사용", "일부 표현은 완전히 해석되지 않았습니다.\n"
                        "원문과 일부 정보 표시를 유지하면서 읽은 데이터를 사용할까요?",
                        QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                        QMessageBox.StandardButton.No)
                    if choice == QMessageBox.StandardButton.Yes:
                        self.partial.setChecked(True)
                        self.start_index()
                    else:
                        self.data_status.setText("읽은 데이터가 있습니다. 사용하려면 일부 구문 사용을 선택하고 색인을 다시 실행해주세요.")
            return
        callback(job["data"])

    def save(self, candidate=None):
        try:
            self.preference_store.save(candidate or self.prefs)
            return True
        except (OSError, ValueError, SnapshotError) as exc:
            message = "설정 파일이 다른 곳에서 변경됐습니다. 앱을 다시 열어 설정을 읽어주세요." if isinstance(exc, SnapshotError) and exc.code == "PREFERENCES_CHANGED" else "설정을 저장하지 못했습니다: " + (exc.code if isinstance(exc, SnapshotError) else type(exc).__name__)
            self.notify(message)
            return False

    def build_home(self):
        layout = self.page("홈", "Stellaris Supporter")
        layout.addWidget(label("게임을 켜면 고정한 카드가 표시됩니다. 단축키로 검색과 카드 편집을 엽니다.", "muted"))
        self.game_status = label("게임 대기 중")
        self.data_status = label("데이터 확인 중")
        layout.addWidget(self.game_status)
        layout.addWidget(self.data_status)
        row = QHBoxLayout()
        button("게임 실행 / 열기", self.launch_game, row)
        button("카드 표시 켜기", self.enable_overlay, row)
        button("오버레이 숨기기", self.hide_overlay, row)
        layout.addLayout(row)
        self.snapshot = QComboBox()
        self.snapshot.currentIndexChanged.connect(lambda: self.invalidate_queries())
        layout.addWidget(label("조회할 스냅샷"))
        layout.addWidget(self.snapshot)
        row = QHBoxLayout()
        self.index_button = button("색인 / 변경 반영", self.start_index, row)
        self.cancel_button = button("작업 취소", self.cancel_index, row)
        self.cancel_button.setEnabled(False)
        button("목록 새로고침", self.refresh_snapshots, row)
        layout.addLayout(row)
        self.events = QCheckBox("이벤트 ID 참조도 포함")
        self.partial = QCheckBox("일부 구문을 처리하지 못해도 스냅샷 사용")
        self.full = QCheckBox("전체 다시 처리")
        for control in (self.events, self.partial, self.full):
            layout.addWidget(control)
        layout.addStretch()
        button("프로그램 종료", self.exit_app, layout)

    def build_search(self):
        layout = self.page("기술 검색", "기술 검색")
        layout.addWidget(label("한국어·영어 이름 또는 기술 ID로 찾습니다.", "muted"))
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("예: 레이저 / laser / tech_lasers_1")
        self.search_input.returnPressed.connect(self.do_search)
        row = QHBoxLayout()
        row.addWidget(self.search_input)
        self.search_button = button("검색", self.do_search, row)
        self.search_input.setEnabled(False)
        self.search_button.setEnabled(False)
        layout.addLayout(row)
        self.search_results = QListWidget()
        self.search_results.currentItemChanged.connect(self.select_hit)
        layout.addWidget(self.search_results)
        self.answer_text = readonly()
        layout.addWidget(self.answer_text, 2)
        row = QHBoxLayout()
        button("기술 카드 고정", self.pin_technology, row)
        button("선행 관계 열기", self.hit_refs, row)
        button("상세·출처", self.open_hit_detail, row)
        layout.addLayout(row)
        self.answer_sources = self.source_list(layout)

    def source_list(self, layout):
        sources = QComboBox()
        row = QHBoxLayout()
        row.addWidget(sources, 1)
        button("원문 보기", lambda: self.open_source(sources.currentData()), row)
        layout.addLayout(row)
        return sources

    def display(self, target, sources, data):
        target.setPlainText(readable_detail(data["card_view"]) if data.get("card_view") else text_view(data))
        sources.clear()
        for ref in collect_sources(data):
            sources.addItem(source_label(ref), ref)

    def sid(self):
        return self.snapshot.currentData()

    def invalidate_queries(self):
        self.query_revision += 1
        for channel in ("search", "answer", "refs", "diff", "update-card", "overlay-search"):
            old = self.latest.pop(channel, None)
            self.callbacks.pop(old, None)
        self.current_hit = self.current_refs = self.current_diff = None
        if hasattr(self, "search_results"):
            self.search_results.clear()
            self.answer_text.clear()

    def do_search(self):
        if not self.sid():
            self.show_search({"status": "error", "results": [], "diagnostics": [{"code": "SNAPSHOT_NOT_READY"}]})
            return
        text = self.search_input.text().strip()
        if text:
            self.notify("검색 데이터를 조회하고 있습니다.")
            self.current_hit = None
            self.answer_text.clear()
            self.callbacks.pop(self.latest.pop("answer", None), None)
            self.submit("search", {"text": text, "snapshot_id": self.sid()}, self.show_search)

    def show_search(self, data):
        self.search_results.clear()
        self.answer_text.clear()
        if data["status"] == "error":
            message = search_error_text(data)
            self.notify(message.replace("\n", " · "))
            self.answer_text.setPlainText(message)
            self.answer_sources.clear()
            return
        self.notify(f"검색 결과 {len(data['results'])}개 · {STATUS.get(data['status'], data['status'])}")
        for hit in data["results"]:
            item = QListWidgetItem(f"{hit['display_name']}  ·  {hit['game_id']}  ·  {hit['definition_source_ref']['relative_path']}")
            item.setData(Qt.ItemDataRole.UserRole, hit)
            self.search_results.addItem(item)
        if self.search_results.count():
            self.search_results.setCurrentRow(0)

    def select_hit(self, current, previous=None):
        self.current_hit = current.data(Qt.ItemDataRole.UserRole) if current else None
        if self.current_hit:
            hit = self.current_hit
            self.submit("answer", {k: hit[k] for k in ("snapshot_id", "game_id", "entity_key")},
                        lambda data: self.display(self.answer_text, self.answer_sources, data))

    def open_hit_detail(self):
        if self.current_hit:
            payload = {key: self.current_hit[key] for key in ("snapshot_id", "game_id", "entity_key")}
            language = self.prefs.language
            self.submit("answer", payload, lambda data: self.open_detail(data) if self.prefs.language == language else None,
                        "hit-detail")

    def open_detail(self, data):
        if data.get("card_view"):
            identity = data["card_view"]["identity"]
            self.show()
            self.raise_()
            self.weapon_browser.open_technology({key: identity[key] for key in ("snapshot_id", "game_id", "entity_key")}, data=data)
        else:
            self.notify("표시할 기술 정보를 찾지 못했습니다.")

    def open_prerequisite(self, view, prerequisite):
        self.refs_id.setText(prerequisite["game_id"])
        self.refs_kind.setCurrentText("technology")
        self.navigate("선행·정적 참조")
        self.do_refs(entity_key=prerequisite["entity_key"], snapshot_id=view["identity"]["snapshot_id"])
        self.show()
        self.raise_()

    def hit_refs(self):
        if self.current_hit:
            self.refs_id.setText(self.current_hit["game_id"])
            self.refs_kind.setCurrentText("technology")
            self.navigate("선행·정적 참조")
            self.do_refs(entity_key=self.current_hit["entity_key"], snapshot_id=self.current_hit["snapshot_id"])

    def build_refs(self):
        layout = self.page("선행·정적 참조", "선행 기술 · 이벤트 참조")
        layout.addWidget(label("기술·이벤트의 정확한 ID로 조회합니다. 중복 정의는 목록에서 선택합니다.", "muted"))
        row = QHBoxLayout()
        self.refs_id = QLineEdit()
        self.refs_id.returnPressed.connect(self.do_refs)
        self.refs_kind = QComboBox()
        self.refs_kind.addItems(["technology", "event"])
        self.depth = QSpinBox()
        self.depth.setRange(1, 16)
        row.addWidget(self.refs_id, 1)
        row.addWidget(self.refs_kind)
        row.addWidget(self.depth)
        button("참조 조회", self.do_refs, row)
        layout.addLayout(row)
        self.refs_nodes = QListWidget()
        self.refs_nodes.itemDoubleClicked.connect(self.navigate_ref)
        layout.addWidget(self.refs_nodes)
        self.refs_text = readonly()
        layout.addWidget(self.refs_text, 2)
        self.refs_sources = self.source_list(layout)
        button("참조 카드 고정", self.pin_reference, layout)

    def do_refs(self, checked=False, *, entity_key=None, snapshot_id=None):
        if self.refs_id.text().strip():
            self.submit("refs", {"game_id": self.refs_id.text().strip(), "kind": self.refs_kind.currentText(),
                                 "snapshot_id": snapshot_id or self.sid(), "entity_key": entity_key,
                                 "depth": self.depth.value()}, self.show_refs)

    def show_refs(self, data):
        self.current_refs = data
        self.display(self.refs_text, self.refs_sources, data)
        self.refs_nodes.clear()
        for node in data["candidates"] if not data["root_entity_key"] else data["nodes"]:
            item = QListWidgetItem(f"{node['game_id']} · {source_label(node['source_ref'])}")
            item.setData(Qt.ItemDataRole.UserRole, node)
            self.refs_nodes.addItem(item)
        if data["candidates"] and not data["root_entity_key"]:
            self.notify("중복 정의가 있습니다. 원하는 출처를 두 번 눌러 선택해주세요.")

    def navigate_ref(self, item):
        node = item.data(Qt.ItemDataRole.UserRole)
        self.refs_id.setText(node["game_id"])
        self.refs_kind.setCurrentText(node["kind"])
        self.do_refs(entity_key=node["entity_key"], snapshot_id=node["source_ref"]["snapshot_id"])

    def build_diff(self):
        layout = self.page("패치 변경 비교", "스냅샷 변경 비교")
        self.before, self.after = QComboBox(), QComboBox()
        form = QFormLayout()
        form.addRow("이전", self.before)
        form.addRow("이후", self.after)
        self.diff_id = QLineEdit()
        self.diff_id.setPlaceholderText("관심 ID를 쉼표로 구분 · 비우면 전체")
        form.addRow("관심 ID", self.diff_id)
        self.diff_kind = QComboBox()
        self.diff_kind.addItems(["technology", "event"])
        form.addRow("분류", self.diff_kind)
        layout.addLayout(form)
        row = QHBoxLayout()
        button("변경 비교", self.do_diff, row)
        button("다음 변경", self.next_diff, row)
        button("변경 카드 고정", self.pin_diff, row)
        layout.addLayout(row)
        self.diff_text = readonly()
        layout.addWidget(self.diff_text)
        self.diff_sources = self.source_list(layout)

    def do_diff(self, checked=False, offset=0):
        if not self.before.currentData() or not self.after.currentData():
            self.notify("비교할 스냅샷 두 개를 선택해주세요.")
            return
        ids = tuple(x.strip() for x in self.diff_id.text().split(",") if x.strip())
        self.submit("diff", {"before_snapshot": self.before.currentData(), "after_snapshot": self.after.currentData(),
                             "kind": self.diff_kind.currentText(), "interest_ids": ids, "offset": offset}, self.show_diff)

    def next_diff(self):
        if self.current_diff and self.current_diff["truncated"]:
            self.do_diff(offset=self.current_diff["query"]["offset"]+20)

    def show_diff(self, data):
        self.current_diff = data
        self.display(self.diff_text, self.diff_sources, data)

    def build_cards(self):
        layout = self.page("고정 카드", "게임 위에 표시할 카드")
        layout.addWidget(label("카드는 고정 당시 스냅샷을 유지합니다. 최신 정의로 바꾸려면 먼저 비교 후 직접 갱신합니다.", "muted"))
        self.card_list = QListWidget()
        layout.addWidget(self.card_list)
        row = QHBoxLayout()
        button("위로", lambda: self.move_card(-1), row)
        button("아래로", lambda: self.move_card(1), row)
        button("제거", self.remove_card, row)
        button("중복 정리", self.cleanup_duplicate_cards, row)
        button("표시 항목", self.card_fields, row)
        layout.addLayout(row)
        row = QHBoxLayout()
        button("현재 데이터와 비교", self.compare_card, row)
        button("최신 정의 선택·갱신", self.update_card, row)
        layout.addLayout(row)

    def selected_card(self):
        row = self.card_list.currentRow()
        return self.prefs.cards[row] if 0 <= row < len(self.prefs.cards) else None

    def find_card(self, kind, snapshot_id, game_id, entity_key):
        return next((c for c in self.prefs.cards if (c.kind, c.snapshot_id, c.game_id, c.entity_key) ==
                     (kind, snapshot_id, game_id, entity_key)), None)

    def settings_key(self):
        return (self.prefs.language, self.prefs.data_dir, self.prefs.game_root, self.settings_epoch)

    def card_guard(self, uid):
        card = next((c for c in self.prefs.cards if c.uid == uid), None)
        return (card_identity(card), tuple(card.fields), self.settings_key()) if card else None

    def commit_cards(self, cards):
        candidate = replace(self.prefs, cards=cards)
        if not self.save(candidate):
            return False
        self.prefs = candidate
        self.rebuild_cards()
        return True

    def select_existing_card(self, card):
        for row, value in enumerate(self.prefs.cards):
            if value.uid == card.uid:
                self.card_list.setCurrentRow(row)
                break
        window = self.cards.get(card.uid)
        if window and window.isVisible() and window.mode == Mode.INTERACTIVE:
            window.setStyleSheet(STYLE + "\nQFrame#card {border:2px solid #b6e4ff;}")
            def restore():
                if self.cards.get(card.uid) is window:
                    window.setStyleSheet(STYLE)
            QTimer.singleShot(700, restore)
        self.notify("이미 고정된 카드입니다. 기존 카드를 선택했습니다.")

    def pin(self, card, origin_uid=None):
        existing = self.find_card(card.kind, card.snapshot_id, card.game_id, card.entity_key)
        if existing:
            self.select_existing_card(existing)
            return
        if len(self.prefs.cards) >= MAX_CARDS:
            self.manage_card(self.prefs.cards[-1].uid)
            self.notify(f"카드는 최대 {MAX_CARDS}개입니다. 고정 카드에서 정리해주세요.")
            return
        scale = self.target.dpi / 96 if self.target else 1
        width, height = (round(self.target.rect[2] / scale), round(self.target.rect[3] / scale)) if self.target else (1280, 720)
        origin = next((c.rect for c in self.prefs.cards if c.uid == origin_uid), None)
        card.rect = place_card(card.rect, [c.rect for c in self.prefs.cards], width, height, origin)
        old_backup = self.preference_store.backup
        if not self.commit_cards([*self.prefs.cards, card]):
            return
        self.refresh_card_data([card.uid])
        self.notify("카드를 고정했습니다." + (" 기존 설정 백업: " + str(self.preference_store.backup)
                    if self.preference_store.backup != old_backup else ""))

    def pin_entity(self, kind, payload, origin_uid=None):
        if kind not in {"technology", "component_template"}:
            self.notify("고정할 수 있는 기술 또는 무기를 선택해주세요.")
            return
        p = {k: payload[k] for k in ("snapshot_id", "game_id", "entity_key") if payload.get(k) is not None}
        card_kind = "technology" if kind == "technology" else "weapon"
        existing = self.find_card(card_kind, p.get("snapshot_id"), p.get("game_id"), p.get("entity_key"))
        if existing:
            self.select_existing_card(existing)
            return
        key = (kind, p.get("snapshot_id"), p.get("game_id"), p.get("entity_key"))
        if key in self.pending_pins:
            return
        self.pending_pins.add(key)
        settings = self.settings_key()
        def resolved(data):
            self.pending_pins.discard(key)
            if settings != self.settings_key() or self.exiting:
                return
            if data.get("status") == "error":
                self.notify("고정할 정보를 읽지 못했습니다.")
                return
            view = data.get("card_view") if kind == "technology" else data
            identity = view.get("identity") if view else None
            if identity:
                if identity["snapshot_id"] != p.get("snapshot_id") or identity["game_id"] != p.get("game_id"):
                    self.notify("선택한 대상과 고정 자료가 다릅니다.")
                    return
                self.pin(Card.create(kind=card_kind, **{k: identity[k] for k in ("snapshot_id", "game_id", "entity_key")}), origin_uid)
                return
            candidates = data.get("results", []) if kind == "technology" else data.get("items", [])
            if not candidates:
                self.notify("이 자료에서 고정할 정의를 찾지 못했습니다.")
                return
            labels = [c.get("name", c.get("display_name", c["game_id"])) + " · " +
                      source_label(c.get("source_ref") or c["definition_source_ref"]) for c in candidates]
            text, ok = QInputDialog.getItem(self, "고정할 정의", "사용할 개별 정의를 선택하세요.", labels, 0, False)
            if ok and settings == self.settings_key():
                candidate = candidates[labels.index(text)]
                self.pin_entity(kind, {**p, "entity_key": candidate["entity_key"]}, origin_uid)
        self.submit("pin_target", {**p, "target_kind": kind}, resolved, "pin:" + uuid.uuid4().hex)

    def cleanup_duplicate_cards(self):
        kept, duplicates = split_duplicate_cards(self.prefs.cards)
        if not duplicates:
            self.notify("중복된 카드가 없습니다.")
            return
        choice = QMessageBox.question(
            self, "중복 카드 정리", f"내용과 표시 항목이 같은 카드 {len(duplicates)}개를 정리할까요?\n"
            "첫 카드를 유지하고 기존 설정은 백업합니다.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No, QMessageBox.StandardButton.No)
        if choice != QMessageBox.StandardButton.Yes:
            return
        path = self.preference_file or preferences_path()
        backup = path.with_name(path.stem + ".before-card-cleanup-" + uuid.uuid4().hex[:8] + ".json")
        try:
            save_preferences(self.prefs, backup)
        except (OSError, ValueError, SnapshotError):
            self.notify("설정을 백업하지 못해 중복 정리를 중단했습니다.")
            return
        old = self.prefs.cards
        self.prefs.cards = kept
        if not self.save():
            self.prefs.cards = old
            return
        for card in duplicates:
            token = self.latest.pop("card:" + card.uid, None)
            self.callbacks.pop(token, None)
        self.rebuild_cards()
        self.refresh_card_data()
        self.notify(f"중복 카드 {len(duplicates)}개를 정리했습니다. 기존 설정은 백업했습니다.")

    def pin_technology(self):
        if self.current_hit:
            self.pin(Card.create(kind="technology", **{k: self.current_hit[k] for k in ("snapshot_id", "game_id", "entity_key")}))

    def pin_reference(self):
        data = self.current_refs
        if data and data["root_entity_key"]:
            self.pin(Card.create(kind="reference", snapshot_id=data["snapshot_id"], game_id=data["query"]["game_id"],
                                 entity_key=data["root_entity_key"], domain=data["query"]["kind"], depth=data["query"]["depth"]))
        elif data:
            self.notify("고정할 정의를 먼저 선택해주세요.")

    def pin_diff(self):
        if self.current_diff:
            query = self.current_diff["query"]
            ids = query.get("interest_ids", ())
            if len(ids) != 1:
                self.notify("변경 카드는 관심 ID 하나를 지정해 고정해주세요.")
                return
            self.pin(Card.create(kind="diff", before_snapshot=query["before_snapshot"],
                                 snapshot_id=query["after_snapshot"], game_id=ids[0], domain=query["kind"]))

    def rebuild_cards(self):
        selected = self.selected_card() if hasattr(self, "card_list") else None
        wanted = {card.uid: card for card in self.prefs.cards}
        for uid in list(self.cards):
            if uid not in wanted:
                window = self.cards.pop(uid)
                window.hide()
                window.deleteLater()
                for prefix in ("card:", "detail:"):
                    token = self.latest.pop(prefix + uid, None)
                    self.callbacks.pop(token, None)
        self.card_list.clear()
        for card in self.prefs.cards:
            window = self.cards.get(card.uid)
            if window is None:
                window = self.cards[card.uid] = CardWindow(self, card)
            else:
                window.card = card
                if card.kind == "weapon" and window.data and not self.matches_card(card.uid, window.data.get("card_request")):
                    window.set_data({"status": "loading"})
            self.card_list.addItem(self.card_label(card, window.data))
            if selected and selected.uid == card.uid:
                self.card_list.setCurrentRow(self.card_list.count() - 1)
        if hasattr(self, "weapon_browser"):
            self.weapon_browser.refresh_pin_actions()

    def card_label(self, card, data):
        name = card.game_id
        if data:
            if card.kind == "weapon" and data.get("summary"):
                name = data["summary"]["name"] + " · " + data["summary"]["size_label"]
            elif card.kind == "technology" and data.get("card_view"):
                name = data["card_view"]["name"]
        return name + " · " + {"weapon": "무기", "technology": "기술", "reference": "참조", "diff": "변경"}[card.kind] + " · " + card.snapshot_id[:12]

    def refresh_card_data(self, uids=None):
        for card in self.prefs.cards:
            if uids is not None and card.uid not in uids:
                continue
            uid = card.uid
            guard = self.card_guard(uid)
            def show(data, uid=uid, guard=guard):
                if guard == self.card_guard(uid):
                    self.show_card(uid, data)
            self.submit("card", {"card": asdict(card)}, show, channel="card:" + uid)

    def matches_card(self, uid, request):
        card = next((value for value in self.prefs.cards if value.uid == uid), None)
        return card is not None and request == {
            **{key: getattr(card, key) for key in ("uid", "snapshot_id", "game_id", "entity_key")},
            "language": self.prefs.language}

    def show_card(self, uid, data):
        window = self.cards.get(uid)
        if not window:
            return
        if window.card.kind in {"technology", "weapon"} and not self.matches_card(uid, data.get("card_request")):
            return
        window.set_data(data)
        for row, card in enumerate(self.prefs.cards):
            if card.uid == uid:
                self.card_list.item(row).setText(self.card_label(card, data))
                break

    def manage_card(self, uid):
        for row, card in enumerate(self.prefs.cards):
            if card.uid == uid:
                self.navigate("고정 카드")
                self.card_list.setCurrentRow(row)
                self.show()
                self.raise_()
                return

    def open_card_detail(self, uid, connections=False):
        card = next((value for value in self.prefs.cards if value.uid == uid), None)
        if card is None:
            return
        if card.kind not in {"technology", "weapon"}:
            self.manage_card(uid)
            return
        guard = self.card_guard(uid)
        def opened(data):
            if guard != self.card_guard(uid) or not self.matches_card(uid, data.get("card_request")):
                return
            if card.kind == "weapon":
                self.weapon_browser.open_weapon({"snapshot_id": card.snapshot_id, "game_id": card.game_id,
                    "entity_key": card.entity_key, "card_uid": uid}, data=data, connections=connections)
                self.open_manager()
            else:
                self.open_detail(data)
        window = self.cards.get(uid)
        if window and window.data and self.matches_card(uid, window.data.get("card_request")):
            opened(window.data)
        else:
            self.submit("card", {"card": asdict(card)}, opened, "detail:" + uid)

    def move_card(self, delta):
        row = self.card_list.currentRow()
        target = row + delta
        if 0 <= row < len(self.prefs.cards) and 0 <= target < len(self.prefs.cards):
            cards = list(self.prefs.cards)
            cards[row], cards[target] = cards[target], cards[row]
            if self.commit_cards(cards):
                self.card_list.setCurrentRow(target)

    def remove_card(self):
        card = self.selected_card()
        if card:
            self.remove_card_uid(card.uid)

    def remove_card_uid(self, uid):
        if any(c.uid == uid for c in self.prefs.cards):
            self.commit_cards([c for c in self.prefs.cards if c.uid != uid])

    def card_fields(self):
        card = self.selected_card()
        if card:
            self.edit_card_fields(card.uid)

    def edit_card_fields(self, uid):
        card = next((c for c in self.prefs.cards if c.uid == uid), None)
        if card and card.kind in {"technology", "weapon"}:
            guard = self.card_guard(uid)
            dialog = FieldsDialog(card.fields, self, labels=WEAPON_FIELDS if card.kind == "weapon" else None)
            if dialog.exec() == FieldsDialog.DialogCode.Accepted and guard == self.card_guard(uid):
                candidate = replace(card, fields=dialog.selected())
                if not self.commit_cards([candidate if c.uid == uid else c for c in self.prefs.cards]):
                    return
                window = self.cards[uid]
                if window.data:
                    window.set_data(window.data)
                else:
                    self.refresh_card_data([uid])

    def compare_card(self):
        card = self.selected_card()
        if card and card.kind == "weapon":
            if self.active_snapshot:
                self.update_weapon_card(card, self.active_snapshot, apply=False)
            return
        if card and self.active_snapshot:
            self.before.setCurrentIndex(self.before.findData(card.snapshot_id))
            self.after.setCurrentIndex(self.after.findData(self.active_snapshot))
            self.diff_id.setText(card.game_id)
            self.diff_kind.setCurrentText(card.domain)
            self.navigate("패치 변경 비교")
            self.do_diff()

    def update_card(self):
        card = self.selected_card()
        if not card or not self.active_snapshot:
            return
        sid = self.active_snapshot
        if card.kind == "weapon":
            self.update_weapon_card(card, sid)
            return
        if card.kind == "technology":
            self.update_technology_card(card, sid)
            return
        if card.kind == "diff":
            card.before_snapshot, card.snapshot_id = card.snapshot_id, sid
            self.save()
            self.rebuild_cards()
            self.refresh_card_data()
            return
        def select(data):
            candidates = data["candidates"] or data["nodes"][:1]
            if not candidates:
                self.notify("최신 스냅샷에서 정의를 찾지 못했습니다.")
                return
            labels = [f"{n['game_id']} · {source_label(n['source_ref'])} · {n['entity_key'][:12]}" for n in candidates]
            selected, ok = QInputDialog.getItem(self, "최신 정의로 갱신", "사용할 정의를 선택해주세요.", labels, 0, False)
            if ok and card in self.prefs.cards:
                card.snapshot_id, card.entity_key = sid, candidates[labels.index(selected)]["entity_key"]
                self.save()
                self.rebuild_cards()
                self.refresh_card_data()
        self.submit("refs", {"game_id": card.game_id, "kind": card.domain, "snapshot_id": sid}, select, "update-card")

    def update_collision(self, candidate):
        existing = next((value for value in self.prefs.cards if value.uid != candidate.uid
                         and card_identity(value) == card_identity(candidate)), None)
        if existing is None:
            return False
        choice = plain_question(self, "이미 있는 카드", "이 정의의 카드가 이미 있습니다. 기존 새 카드를 선택할까요?")
        if choice == QMessageBox.StandardButton.Yes:
            self.manage_card(existing.uid)
        return True

    def update_weapon_card(self, card, sid, apply=True):
        guard = self.card_guard(card.uid)
        before = asdict(card)
        def choose(data):
            if guard != self.card_guard(card.uid):
                return
            identity = data.get("identity")
            if not identity:
                candidates = data.get("items", [])
                if not candidates:
                    self.notify("선택한 자료에서 이 무기를 찾지 못했습니다.")
                    return
                labels = [c["name"] + " · " + c["size_label"] + " · " + source_label(c["source_ref"]) for c in candidates]
                text, ok = QInputDialog.getItem(self, "갱신할 무기 정의", "사용할 정의를 선택하세요.", labels, 0, False)
                if not ok or guard != self.card_guard(card.uid):
                    return
                identity = candidates[labels.index(text)]
            after = {**before, "snapshot_id": sid, "entity_key": identity["entity_key"]}
            def preview(result):
                if guard != self.card_guard(card.uid):
                    return
                old, new = result.get("before", {}), result.get("after", {})
                left, right = preview_text(old, card.fields), preview_text(new, card.fields)
                if not left or not right:
                    self.notify("전후 자료를 읽지 못해 갱신을 중단했습니다.")
                    return
                text = "기존\n" + left + "\n\n변경 후\n" + right
                if not apply:
                    dialog = QDialog(self)
                    dialog.setWindowTitle("카드 자료 전후 비교")
                    dialog.resize(680, 640)
                    layout = QVBoxLayout(dialog)
                    view = readonly()
                    view.setPlainText(text)
                    layout.addWidget(view)
                    button("닫기", dialog.accept, layout)
                    dialog.exec()
                    return
                candidate = replace(card, snapshot_id=sid, entity_key=after["entity_key"])
                if self.update_collision(candidate) or guard != self.card_guard(card.uid):
                    return
                if plain_question(self, "무기 카드 데이터 변경", text + "\n\n이 카드에 적용할까요?") != QMessageBox.StandardButton.Yes:
                    return
                if guard != self.card_guard(card.uid):
                    return
                confirmed = copy.deepcopy(result)
                def rechecked(current):
                    if guard != self.card_guard(card.uid):
                        return
                    if current != confirmed:
                        self.notify("확인한 자료가 바뀌었습니다. 갱신 내용을 다시 확인해주세요.")
                        return
                    live = next((c for c in self.prefs.cards if c.uid == card.uid), None)
                    if live is None:
                        return
                    replacement = replace(live, snapshot_id=sid, entity_key=after["entity_key"])
                    if self.update_collision(replacement) or guard != self.card_guard(card.uid):
                        return
                    if self.commit_cards([replacement if c.uid == live.uid else c for c in self.prefs.cards]):
                        self.refresh_card_data([live.uid])
                        self.manage_card(live.uid)
                self.submit("card_preview", {"before": before, "after": after}, rechecked, "weapon-update:" + card.uid)
            self.submit("card_preview", {"before": before, "after": after}, preview, "weapon-update:" + card.uid)
        self.submit("weapon_detail", {"snapshot_id": sid, "game_id": card.game_id}, choose, "weapon-update:" + card.uid)

    def update_technology_card(self, card, sid):
        request = {**{key: getattr(card, key) for key in ("uid", "snapshot_id", "game_id", "entity_key")},
                   "language": self.prefs.language}
        def select(data):
            if not self.matches_card(card.uid, request):
                return
            candidates = data["candidates"] or data["nodes"][:1]
            if not candidates:
                self.notify("선택한 데이터에서 정의를 찾지 못했습니다.")
                return
            selected = candidates[0]
            if len(candidates) > 1:
                labels = [f"{n['game_id']} · {source_label(n['source_ref'])} · {n['entity_key'][:12]}" for n in candidates]
                text, ok = QInputDialog.getItem(self, "갱신할 정의", "사용할 정의를 선택하세요.", labels, 0, False)
                if not ok:
                    return
                selected = candidates[labels.index(text)]
            candidate = replace(card, snapshot_id=sid, entity_key=selected["entity_key"])
            if self.update_collision(candidate):
                return
            def preview(result):
                if not self.matches_card(card.uid, request):
                    return
                before, after = result["before"].get("card_view"), result["after"].get("card_view")
                if not before or not after:
                    self.notify("전후 기술 정보를 읽지 못해 갱신을 중단했습니다.")
                    return
                def summary(view):
                    names = ", ".join(value["name"] for value in view["prerequisites"])
                    if not names:
                        names = "없음" if view["prerequisites_complete"] else "자료 확인 필요"
                    return f"{view['name']}\n기본 연구 비용: {field_text(view, 'cost')}\n선행 기술: {names}"
                choice = plain_question(self, "카드 데이터 변경", "기존\n"+summary(before)+"\n\n변경 후\n"+summary(after)+
                                        "\n\n이 카드에 적용할까요?")
                if choice != QMessageBox.StandardButton.Yes or not self.matches_card(card.uid, request):
                    return
                if self.update_collision(candidate):
                    return
                old = card.snapshot_id, card.entity_key
                card.snapshot_id, card.entity_key = candidate.snapshot_id, candidate.entity_key
                if not self.save():
                    card.snapshot_id, card.entity_key = old
                    return
                self.rebuild_cards()
                self.refresh_card_data([card.uid])
                self.manage_card(card.uid)
            self.submit("card_preview", {"before": asdict(card), "after": asdict(candidate)}, preview, "update-card")
        self.submit("refs", {"game_id": card.game_id, "kind": card.domain, "snapshot_id": sid}, select, "update-card")

    def build_settings(self):
        layout = self.page("설정", "설치 경로 · 화면 설정")
        form = QFormLayout()
        self.game_path = QLineEdit(self.prefs.game_root)
        self.exe_path = QLineEdit(self.prefs.executable)
        self.data_path = QLineEdit(self.prefs.data_dir)
        for title, control, is_exe in (("게임 폴더", self.game_path, False), ("게임 실행 파일 (선택)", self.exe_path, True), ("데이터 폴더", self.data_path, False)):
            row = QHBoxLayout()
            row.addWidget(control)
            button("찾아보기", lambda checked=False, control=control, is_exe=is_exe: self.choose_path(control, is_exe), row)
            form.addRow(title, row)
        self.installations = QComboBox()
        self.installations.currentIndexChanged.connect(lambda: self.game_path.setText(self.installations.currentData() or self.game_path.text()))
        form.addRow("Steam 탐색 결과", self.installations)
        self.language = QComboBox()
        self.language.addItems(["korean", "english"])
        self.language.setCurrentText(self.prefs.language)
        form.addRow("표시 언어", self.language)
        self.toggle_key = QLineEdit(self.prefs.toggle_hotkey)
        self.hide_key = QLineEdit(self.prefs.hide_hotkey)
        form.addRow("검색·편집 단축키", self.toggle_key)
        form.addRow("완전히 숨기기 단축키", self.hide_key)
        self.opacity = QSlider(Qt.Orientation.Horizontal)
        self.opacity.setRange(30, 100)
        self.opacity.setValue(self.prefs.opacity)
        form.addRow("카드 불투명도", self.opacity)
        self.close_tray = QCheckBox("관리창을 닫으면 트레이에 두기")
        self.close_tray.setChecked(self.prefs.close_to_tray)
        form.addRow(self.close_tray)
        layout.addLayout(form)
        row = QHBoxLayout()
        button("Steam 설치 찾기", self.discover, row)
        self.apply_button = button("설정 저장", self.apply_settings, row)
        layout.addLayout(row)
        layout.addStretch()

    def choose_path(self, control, is_exe):
        value = QFileDialog.getOpenFileName(self, "게임 실행 파일", control.text(), "실행 파일 (*.exe)")[0] if is_exe else QFileDialog.getExistingDirectory(self, "폴더 선택", control.text())
        if value:
            control.setText(value)

    def discover(self, checked=False, auto=False):
        previous = self.game_path.text()
        found = discover_installations()
        self.installations.blockSignals(True)
        self.installations.clear()
        self.installations.addItem("설치를 선택해주세요.", "")
        for root in found:
            self.installations.addItem(str(root), str(root))
        selected = self.installations.findData(previous)
        self.installations.setCurrentIndex(max(0, selected))
        self.installations.blockSignals(False)
        if len(found) == 1 and not previous:
            self.game_path.setText(str(found[0]))
            if auto:
                candidate = replace(self.prefs, game_root=str(found[0]))
                if self.save(candidate):
                    self.prefs = candidate
        if not auto:
            self.notify(f"Steam 설치 {len(found)}개를 찾았습니다. 목록에서 선택하거나 폴더를 직접 지정해주세요.")

    def apply_settings(self):
        if self.index_cancel is not None:
            self.notify("색인 작업이 끝난 뒤 경로를 변경해주세요.")
            return
        candidate = replace(self.prefs, game_root=self.game_path.text().strip(), executable=self.exe_path.text().strip(),
                            data_dir=self.data_path.text().strip(), language=self.language.currentText(),
                            toggle_hotkey=self.toggle_key.text().strip(), hide_hotkey=self.hide_key.text().strip(),
                            opacity=self.opacity.value(), close_to_tray=self.close_tray.isChecked())
        try:
            candidate.validate()
            settings = candidate.services()
            if not settings.game_root or not (settings.game_root / "common" / "technology").is_dir():
                raise ValueError("common/technology가 있는 게임 폴더를 지정해주세요.")
            if paths_overlap(settings.game_root, settings.data_dir):
                raise ValueError("데이터 폴더는 게임 폴더 밖에 지정해주세요.")
            for path in (settings.game_root, settings.data_dir):
                _check_components(path)
            executable = Path(candidate.executable) if candidate.executable else settings.game_root / "stellaris.exe"
            _check_components(executable)
            if not executable.is_file():
                raise ValueError("게임 실행 파일을 찾지 못했습니다.")
            parse_hotkey(candidate.toggle_hotkey)
            parse_hotkey(candidate.hide_hotkey)
            if self.native:
                self.native.bind_hotkeys(int(self.winId()), candidate.toggle_hotkey, candidate.hide_hotkey)
            self.preference_store.save(candidate)
        except (OSError, ValueError, SnapshotError) as exc:
            if self.native:
                try:
                    self.native.bind_hotkeys(int(self.winId()), self.prefs.toggle_hotkey, self.prefs.hide_hotkey)
                except ValueError:
                    pass
            self.notify(str(exc) if isinstance(exc, ValueError) else "경로 또는 설정을 저장할 수 없습니다. 외부 변경이면 앱을 다시 열어주세요.")
            return
        self.prefs = candidate
        self.settings_epoch += 1
        self.pending_pins.clear()
        for window in self.cards.values():
            window.data = None
            if window.card.kind == "weapon":
                window.set_data({"status": "loading"})
        self.invalidate_queries()
        self.refresh_snapshots()
        self.refresh_card_data()
        self.notify("설정을 저장했습니다.")

    def refresh_snapshots(self, *, preferred_snapshot=None):
        self.submit("snapshots", {}, lambda data: self.show_snapshots(data, preferred_snapshot=preferred_snapshot))

    def show_snapshots(self, data, *, preferred_snapshot=None):
        self.snapshots_loaded = True
        self.active_snapshot = data["active"]
        available = any(row["status"] in {"ready", "partial"} for row in data["rows"])
        self.data_status.setText("활성 스냅샷 " + self.active_snapshot[:12] if self.active_snapshot else
                                 "조회할 데이터를 선택해주세요." if available else
                                 "아직 검색 데이터가 없습니다. 아래의 색인 / 변경 반영을 실행해주세요.")
        for combo in (self.snapshot, self.before, self.after):
            previous = combo.currentData()
            combo.blockSignals(True)
            combo.clear()
            for row in data["rows"]:
                if row["status"] in {"ready", "partial"}:
                    combo.addItem(row["snapshot_id"][:12] + " · " + row["status"], row["snapshot_id"])
            desired = preferred_snapshot if combo is self.snapshot and preferred_snapshot else previous or self.active_snapshot
            selected = combo.findData(desired)
            combo.setCurrentIndex(max(0, selected))
            combo.blockSignals(False)
        self.invalidate_queries()
        self.update_search_availability()
        for window in self.cards.values():
            if window.card.kind == "weapon" and window.data:
                window.set_data(window.data)
        if data["truncated"]:
            self.notify("최근 스냅샷 100개를 표시합니다.")

    def update_search_availability(self):
        ready = bool(self.sid())
        self.search_input.setEnabled(ready)
        self.search_button.setEnabled(ready)
        self.search_input.setPlaceholderText("예: 레이저 / laser / tech_lasers_1" if ready else
                                             "홈에서 먼저 색인 / 변경 반영을 실행해주세요.")
        if hasattr(self, "overlay_input"):
            self.overlay_input.setEnabled(ready)
            self.overlay_results.clear()
            if not ready:
                item = QListWidgetItem("관리창의 홈에서 먼저 색인 / 변경 반영을 실행해주세요.")
                item.setFlags(Qt.ItemFlag.NoItemFlags)
                self.overlay_results.addItem(item)

    def start_index(self):
        if self.index_cancel is not None:
            return
        self.index_query_revision = self.query_revision
        self.index_cancel = Event()
        self.index_button.setEnabled(False)
        self.apply_button.setEnabled(False)
        self.cancel_button.setEnabled(True)
        for control in (self.events, self.partial, self.full):
            control.setEnabled(False)
        self.data_status.setText("데이터 준비 중 · 설치 파일을 확인하고 있습니다.")
        self.notify("색인 작업 중입니다. 다른 화면은 계속 사용할 수 있습니다.")
        self.submit("index", {"events": self.events.isChecked(), "partial": self.partial.isChecked(),
                              "full": self.full.isChecked(), "cancel": self.index_cancel}, self.index_done)

    def index_progress(self, progress):
        phases = {"inventory": "설치 파일 확인", "parse": "데이터 읽기", "store": "데이터 저장",
                  "search": "검색 데이터 준비", "publish": "데이터 반영", "done": "데이터 준비 완료"}
        text = phases.get(progress["phase"], "데이터 준비")
        if progress["total"]:
            text += f" · {progress['done']}/{progress['total']} 파일"
        self.data_status.setText(text)
        self.notify(text)

    def cancel_index(self):
        if self.index_cancel:
            self.index_cancel.set()
            self.notify("현재 처리 구간이 끝나면 취소합니다.")

    def index_done(self, data):
        self.index_cancel = None
        self.index_button.setEnabled(True)
        self.apply_button.setEnabled(True)
        self.cancel_button.setEnabled(False)
        for control in (self.events, self.partial, self.full):
            control.setEnabled(True)
        if data:
            stored = data.get("storage", {})
            count = stored.get("localisation_entries")
            self.notify("데이터를 반영했습니다." + (f" 번역 {count:,}항목" if count is not None else ""))
            preferred = data.get("snapshot_id") if self.query_revision == self.index_query_revision else None
            self.refresh_snapshots(preferred_snapshot=preferred)
        else:
            self.data_status.setText("데이터 준비를 완료하지 못했습니다. 아래 상태 메시지를 확인해주세요.")

    def open_source(self, ref):
        if ref:
            def show(text):
                dialog = QMainWindow(self)
                dialog.setWindowTitle("원문 · " + source_label(ref))
                body = readonly()
                body.setPlainText(text)
                dialog.setCentralWidget(body)
                dialog.resize(800, 560)
                dialog.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
                dialog.show()
            self.submit("source", ref, show)

    def executable(self):
        if self.prefs.executable:
            return self.prefs.executable
        return str(Path(self.prefs.game_root)/"stellaris.exe") if self.prefs.game_root else ""

    def launch_game(self):
        if self.native:
            target = self.native.track(self.executable())
            if target:
                self.native.focus(target)
                return
        exe = Path(self.executable())
        try:
            _check_components(exe)
            if not exe.is_absolute() or not exe.is_file() or exe.suffix.lower() != ".exe":
                raise ValueError()
            subprocess.Popen([str(exe)], cwd=str(exe.parent), shell=False)
        except (OSError, ValueError, SnapshotError):
            self.notify("설정에서 게임 실행 경로를 확인해주세요.")

    def eligible(self):
        if not self.native or not self.target:
            return False
        foreground = self.native.foreground()
        own = set()
        for window in self.cards.values():
            if window.isVisible():
                own.add(int(window.winId()))
                own.update(int(menu.winId()) for menu in window.findChildren(QMenu) if menu.isVisible())
        if hasattr(self, "overlay_search") and self.overlay_search.isVisible():
            own.add(int(self.overlay_search.winId()))
        return foreground == self.target.hwnd or self.state.mode == Mode.INTERACTIVE and foreground in own

    def poll_game(self):
        if not self.native or self.exiting:
            return
        try:
            self.target = self.native.track(self.executable())
            self.game_status.setText("게임 연결됨" if self.target else "게임 대기 중")
            mode = self.state.observe(self.eligible())
            for window in self.cards.values():
                window.present(mode, self.target)
            if hasattr(self, "overlay_search"):
                if mode != Mode.INTERACTIVE:
                    self.overlay_search.hide()
                elif self.target:
                    tx, ty, tw, th = self.target.rect
                    scale = self.target.dpi/96
                    self.native.user.SetWindowPos(int(self.overlay_search.winId()), -1,
                        tx+max(0, tw-round(480*scale)), ty, min(tw, round(480*scale)), min(th, round(540*scale)), 0x10)
        except (OSError, ValueError):
            self.target = None
            self.state.observe(False)
            for window in self.cards.values():
                window.hide()
            if hasattr(self, "overlay_search"):
                self.overlay_search.hide()

    def enable_overlay(self):
        self.state.enabled = True
        self.notify("게임으로 돌아가면 고정 카드가 표시됩니다.")

    def hide_overlay(self):
        if self.target and self.native and self.eligible() and self.native.foreground() != self.target.hwnd:
            self.native.focus(self.target)
        self.state.hide()
        for window in self.cards.values():
            window.present(Mode.HIDDEN, None)
        if hasattr(self, "overlay_search"):
            self.overlay_search.hide()

    def toggle_overlay(self):
        self.target = self.native.track(self.executable()) if self.native else None
        if not self.target:
            return
        eligible = self.eligible() or self.native.foreground() == self.target.hwnd
        if not eligible:
            return
        mode = self.state.toggle(True)
        if mode == Mode.INTERACTIVE:
            self.show_overlay_search()
        else:
            if hasattr(self, "overlay_search"):
                self.overlay_search.hide()
            self.native.focus(self.target)
        self.poll_game()

    def show_overlay_search(self):
        if not hasattr(self, "overlay_search"):
            self.overlay_search = QWidget(None, Qt.WindowType.Tool | Qt.WindowType.WindowStaysOnTopHint)
            self.overlay_search.setWindowTitle("Stellaris · 검색 및 카드 편집")
            self.overlay_search.setStyleSheet(STYLE)
            layout = QVBoxLayout(self.overlay_search)
            layout.addWidget(label("기술 검색 · 카드 제목을 끌어 이동", "muted"))
            self.overlay_input = QLineEdit()
            self.overlay_input.setPlaceholderText("기술 이름 또는 ID")
            self.overlay_input.returnPressed.connect(self.overlay_query)
            layout.addWidget(self.overlay_input)
            self.overlay_results = QListWidget()
            self.overlay_results.itemDoubleClicked.connect(self.overlay_pin)
            layout.addWidget(self.overlay_results)
            layout.addWidget(label("검색 결과를 두 번 누르면 카드를 고정합니다.", "muted"))
            button("카드 보기로 돌아가기", self.toggle_overlay, layout)
            button("완전히 숨기기", self.hide_overlay, layout)
            self.overlay_search.closeEvent = self.close_overlay_search
        self.update_search_availability()
        self.overlay_search.show()
        self.overlay_search.raise_()
        self.overlay_search.activateWindow()
        self.overlay_input.setFocus()

    def close_overlay_search(self, event):
        event.ignore()
        self.hide_overlay()

    def overlay_query(self):
        text = self.overlay_input.text().strip()
        if text:
            def show(data):
                self.overlay_results.clear()
                if data["status"] == "error":
                    item = QListWidgetItem(search_error_text(data))
                    item.setFlags(Qt.ItemFlag.NoItemFlags)
                    self.overlay_results.addItem(item)
                    return
                for hit in data["results"]:
                    item = QListWidgetItem(hit["display_name"]+" · "+hit["game_id"])
                    item.setData(Qt.ItemDataRole.UserRole, hit)
                    self.overlay_results.addItem(item)
            self.submit("search", {"text": text, "snapshot_id": self.sid()}, show, "overlay-search")

    def overlay_pin(self, item):
        hit = item.data(Qt.ItemDataRole.UserRole)
        if not hit:
            return
        self.pin(Card.create(kind="technology", **{k: hit[k] for k in ("snapshot_id", "game_id", "entity_key")}))

    def open_manager(self):
        self.showNormal()
        self.raise_()
        self.activateWindow()

    def closeEvent(self, event):
        if self.allow_close:
            event.accept()
        elif self.prefs.close_to_tray and self.tray.isSystemTrayAvailable():
            event.ignore()
            self.hide()
        else:
            event.ignore()
            self.exit_app()

    def exit_app(self):
        if self.exiting:
            return
        self.exiting = True
        self.timer.stop()
        self.hide_overlay()
        self.cancel_index()
        self.latest.clear()
        self.callbacks.clear()
        if self.native:
            self.native.release()
        self.notify("종료 중입니다.")
        self.bus.stop.emit()
        self.index_bus.stop.emit()

    def finished_exit(self):
        if self.exiting and not self.thread.isRunning() and not self.index_thread.isRunning():
            self.tray.hide()
            self.allow_close = True
            self.close()
            QApplication.instance().quit()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Stellaris Supporter desktop")
    parser.add_argument("--preferences", type=Path, help="Private desktop settings path")
    parser.add_argument("--smoke", action="store_true", help="Construct UI and exit without game operations")
    parser.add_argument("--diagnose-weapon-card", help="Read an existing weapon card through the desktop worker, then exit")
    parser.add_argument("--diagnose-weapon", help="Read one weapon through the desktop worker, then exit")
    parser.add_argument("--diagnose-search", help="Run a read-only search through the desktop worker, then exit")
    parser.add_argument("--diagnostics-output", type=Path, help="Private JSON diagnostic output")
    args = parser.parse_args(argv)
    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    try:
        prefs = load_preferences(args.preferences)
    except (OSError, ValueError, TypeError, KeyError, SnapshotError):
        QMessageBox.critical(None, "설정 읽기 실패", "개인 desktop.json 설정 형식을 확인해주세요. 기존 파일은 유지됩니다.")
        return 2
    manager = Manager(prefs, args.preferences)
    manager.show()
    if args.diagnose_weapon_card:
        import json
        outcome = {"completed": False}
        def capture_card(job):
            card = job.get("payload", {}).get("card", {})
            if job["kind"] != "card" or card.get("kind") != "weapon" or card.get("game_id") != args.diagnose_weapon_card:
                return
            data = job.get("data") or {}
            view = weapon_view(data)
            outcome.update(completed=bool(view), error=job.get("error"), identity=data.get("identity"))
            if view:
                outcome.update(text=preview_text(data, card["fields"]),
                               summary_lines=manager.cards[card["uid"]].summary.rows(330, 220))
            QTimer.singleShot(100, manager.exit_app)
        manager.worker.result.connect(capture_card)
        QTimer.singleShot(30000, manager.exit_app)
        status = app.exec()
        if args.diagnostics_output:
            from stellaris_supporter.storage.cache import _ensure_directory
            _check_components(args.diagnostics_output)
            _ensure_directory(args.diagnostics_output.parent)
            args.diagnostics_output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        return status if outcome["completed"] and not outcome.get("error") else 1
    if args.diagnose_weapon:
        import json
        outcome = {"completed": False}
        def capture_weapon(job):
            if job["kind"] != "weapon_detail":
                return
            data = job.get("data") or {}
            outcome.update(completed=True, error=job.get("error"), status=data.get("status"), identity=data.get("identity"),
                           fields=data.get("fields"), link_count=len(data.get("links", [])))
            QTimer.singleShot(100, manager.exit_app)
        manager.worker.result.connect(capture_weapon)
        timer = QTimer(manager)
        def begin_weapon():
            if manager.snapshots_loaded:
                timer.stop()
                manager.weapon_browser.open_weapon({"snapshot_id": manager.sid(), "game_id": args.diagnose_weapon})
        timer.timeout.connect(begin_weapon)
        timer.start(100)
        QTimer.singleShot(30000, manager.exit_app)
        status = app.exec()
        if args.diagnostics_output:
            from stellaris_supporter.storage.cache import _ensure_directory
            _check_components(args.diagnostics_output)
            _ensure_directory(args.diagnostics_output.parent)
            args.diagnostics_output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        return status if outcome["completed"] and outcome.get("identity") and not outcome.get("error") else 1
    if args.diagnose_search:
        import json
        outcome = {"completed": False}
        def capture(job):
            data = job.get("data") or {}
            if job["kind"] == "snapshots":
                outcome["storage"] = data.get("storage")
            if job["kind"] == "answer":
                view = data.get("card_view")
                outcome["card_completed"] = bool(view)
                outcome["card_error"] = job.get("error")
                if view:
                    outcome["card"] = {"identity": view["identity"],
                        "cost": view["fields"]["cost"]["value"],
                        "cost_status": view["fields"]["cost"]["status"],
                        "cost_proof_count": len(view["fields"]["cost"]["sources"])}
                QTimer.singleShot(100, manager.exit_app)
                return
            if job["kind"] != "search":
                return
            outcome.update(completed=True, worker_error=job.get("error"),
                           status=data.get("status"), result_count=len(data.get("results", ())),
                           diagnostics=data.get("diagnostics", ()))
            if job.get("error") or not data.get("results"):
                QTimer.singleShot(100, manager.exit_app)
        manager.worker.result.connect(capture)
        timer = QTimer(manager)
        def begin():
            if manager.snapshots_loaded:
                timer.stop()
                manager.search_input.setText(args.diagnose_search)
                if manager.sid():
                    manager.do_search()
                else:
                    manager.submit("search", {"text": args.diagnose_search, "snapshot_id": None}, manager.show_search)
        timer.timeout.connect(begin)
        timer.start(100)
        QTimer.singleShot(15000, manager.exit_app)
        status = app.exec()
        if args.diagnostics_output:
            from stellaris_supporter.storage.cache import _ensure_directory
            _check_components(args.diagnostics_output)
            _ensure_directory(args.diagnostics_output.parent)
            args.diagnostics_output.write_text(json.dumps(outcome, ensure_ascii=False, indent=2), encoding="utf-8")
        return status if (outcome["completed"] and outcome.get("status") != "error"
                          and (not outcome.get("result_count") or outcome.get("card_completed"))) else 1
    if args.smoke:
        QTimer.singleShot(1600, manager.exit_app)
    return app.exec()
