"""Integrated technology/weapon navigation; all asynchronous views pin their identity."""

from __future__ import annotations

import copy

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QPlainTextEdit,
    QPushButton,
    QStackedWidget,
    QTabWidget,
    QTreeWidget,
    QTreeWidgetItem,
    QVBoxLayout,
    QWidget,
)

from stellaris_supporter.card_information import FIELD_LABELS, field_text, readable_detail
from stellaris_supporter.weapon_cards import field_lines, numeric_detail_lines, project
from stellaris_supporter.weapons import SIZES, TAGS

from .presentation import collect_sources, source_label, text_view
from .settings import Card


def plain(text):
    label = QLabel(text)
    label.setTextFormat(Qt.TextFormat.PlainText)
    label.setWordWrap(True)
    return label


def action(text, callback, layout):
    button = QPushButton(text)
    button.clicked.connect(callback)
    layout.addWidget(button)
    return button


def readonly():
    text = QPlainTextEdit()
    text.setReadOnly(True)
    return text


class WeaponBrowser(QWidget):
    def __init__(self, manager):
        super().__init__()
        self.manager = manager
        self.generation = 0
        self.history = []
        self.current = None
        self.saved_scroll = 0
        self.expanded = set()
        outer = QVBoxLayout(self)
        top = QHBoxLayout()
        self.back_button = action("뒤로", self.back, top)
        self.title = plain("무기 검색")
        top.addWidget(self.title, 1)
        action("새 자료로 보기", self.open_latest, top)
        outer.addLayout(top)
        self.status = plain("")
        outer.addWidget(self.status)
        self.stack = QStackedWidget()
        outer.addWidget(self.stack, 1)
        self.build_search()
        self.build_weapon()
        self.build_technology()
        self.back_button.setEnabled(False)

    def panel(self):
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        self.stack.addWidget(widget)
        return widget, layout

    def build_search(self):
        self.search_panel, layout = self.panel()
        row = QHBoxLayout()
        self.query = QLineEdit()
        self.query.setMaxLength(512)
        self.query.setPlaceholderText("무기 이름 또는 부품 ID")
        self.query.returnPressed.connect(self.search)
        row.addWidget(self.query, 1)
        action("검색", self.search, row)
        self.size = QComboBox()
        self.size.addItem("모든 크기", "")
        for key, value in SIZES.items():
            self.size.addItem(value, key)
        self.tag = QComboBox()
        self.tag.addItem("모든 계열", "")
        for key, value in TAGS.items():
            self.tag.addItem(value, key)
        row.addWidget(self.size)
        row.addWidget(self.tag)
        layout.addLayout(row)
        self.search_tree = self.tree(layout)
        self.search_tree.itemDoubleClicked.connect(self.choose_weapon)
        self.search_tree.itemExpanded.connect(self.expand_group)
        self.search_tree.currentItemChanged.connect(lambda *args: self.refresh_pin_actions())
        self.search_pin = action("선택한 무기 카드 고정", lambda: self.pin_tree(self.search_tree), layout)
        self.more_search = action("더 보기", self.next_search, layout)

    def tree(self, layout):
        tree = QTreeWidget()
        tree.setHeaderLabels(["무기 / 계열", "크기", "정보"])
        tree.setColumnWidth(0, 360)
        tree.setColumnWidth(1, 110)
        layout.addWidget(tree, 1)
        return tree

    def build_weapon(self):
        self.weapon_panel, layout = self.panel()
        self.weapon_text = readonly()
        layout.addWidget(self.weapon_text, 2)
        self.weapon_pin = action("무기 카드 고정", self.pin_weapon, layout)
        self.link_list = QListWidget()
        self.link_list.itemDoubleClicked.connect(self.choose_link)
        layout.addWidget(plain("요구 기술 · 명시된 상위 부품"))
        layout.addWidget(self.link_list, 1)
        row = QHBoxLayout()
        self.link_pin = action("선택한 연결 카드 고정", self.pin_link, row)
        self.link_open = action("선택한 연결 상세 열기", self.open_selected_link, row)
        self.link_list.currentItemChanged.connect(lambda *args: self.refresh_pin_actions())
        layout.addLayout(row)
        self.weapon_sources = self.manager.source_list(layout)
        row = QHBoxLayout()
        self.section_buttons = {}
        for name in ("links", "resources", "conditions", "effects"):
            text = {
                "links": "연결",
                "resources": "자원",
                "conditions": "조건",
                "effects": "특수 작용",
            }[name]
            self.section_buttons[name] = action(
                text + " 더 보기", lambda checked=False, name=name: self.load_section(name), row
            )
        layout.addLayout(row)
        self.weapon_technical = readonly()
        self.weapon_technical.setMaximumHeight(110)
        self.weapon_technical.hide()
        action(
            "ID · 자료 기준 · 진단 보기",
            lambda: self.weapon_technical.setVisible(not self.weapon_technical.isVisible()),
            layout,
        )
        layout.addWidget(self.weapon_technical)

    def build_technology(self):
        self.tech_panel, layout = self.panel()
        self.tech_text = readonly()
        layout.addWidget(self.tech_text, 2)
        self.tech_sources = self.manager.source_list(layout)
        self.tech_links = QListWidget()
        self.tech_links.setMaximumHeight(110)
        self.tech_links.itemDoubleClicked.connect(self.choose_technology)
        layout.addWidget(self.tech_links)
        row = QHBoxLayout()
        action("기술 카드 고정", self.pin_technology, row)
        self.update_button = action("기존 카드 갱신", self.update_card, row)
        action("색인 화면", lambda: self.manager.navigate("홈"), row)
        layout.addLayout(row)
        self.tech_tabs = QTabWidget()
        related_panel = QWidget()
        related_layout = QVBoxLayout(related_panel)
        related_layout.addWidget(plain("이 기술을 요구하는 무기"))
        self.related_tree = self.tree(related_layout)
        self.related_tree.itemDoubleClicked.connect(self.choose_weapon)
        self.related_tree.itemExpanded.connect(self.expand_group)
        self.related_tree.currentItemChanged.connect(lambda *args: self.refresh_pin_actions())
        self.related_pin = action("선택한 무기 카드 고정", lambda: self.pin_tree(self.related_tree), related_layout)
        self.more_related = action("관련 무기 더 보기", self.next_related, related_layout)
        self.tech_proof = readonly()
        self.tech_technical = readonly()
        self.tech_tabs.addTab(related_panel, "관련 무기")
        self.tech_tabs.addTab(self.tech_proof, "값의 근거")
        self.tech_tabs.addTab(self.tech_technical, "ID · 자료 기준 · 진단")
        layout.addWidget(self.tech_tabs, 2)

    def settings_key(self):
        return (
            self.manager.prefs.language,
            self.manager.prefs.data_dir,
            self.manager.prefs.game_root,
            self.manager.settings_epoch,
        )

    def submit(self, kind, payload, callback, channel="weapon-browser"):
        generation = self.generation
        settings = self.settings_key()

        def receive(data):
            if generation == self.generation and settings == self.settings_key():
                callback(data)

        self.manager.submit(kind, payload, receive, channel)

    def capture(self):
        if self.current is None:
            return None
        value = copy.deepcopy(self.current)
        value["scroll"] = (
            self.search_tree.verticalScrollBar().value()
            if value["kind"] == "search"
            else self.weapon_text.verticalScrollBar().value()
            if value["kind"] == "weapon"
            else self.tech_text.verticalScrollBar().value()
        )
        value["expanded"] = list(self.expanded)
        value["tree_scroll"] = (
            (self.search_tree if value["kind"] == "search" else self.related_tree)
            .verticalScrollBar()
            .value()
        )
        value["tech_tab"] = self.tech_tabs.currentIndex()
        tree = self.search_tree if value["kind"] == "search" else self.related_tree
        current = tree.currentItem()
        value["selected"] = current.data(0, Qt.ItemDataRole.UserRole) if current else None
        return value

    def begin(self, kind, payload, push=True):
        if push:
            value = self.capture()
            if value:
                self.history.append(value)
                self.history = self.history[-32:]
        self.generation += 1
        self.expanded = set()
        self.current = {
            "kind": kind,
            "payload": copy.deepcopy(payload),
            "language": self.manager.prefs.language,
        }
        self.back_button.setEnabled(bool(self.history))
        self.status.setText("자료를 읽고 있습니다.")
        self.manager.navigate("무기 검색")

    def enter(self):
        if self.current is None:
            self.search()

    def search(self, checked=False, payload=None, push=True):
        p = payload or {
            "snapshot_id": self.manager.sid(),
            "text": self.query.text(),
            "size": self.size.currentData(),
            "tag": self.tag.currentData(),
            "grouped": True,
            "offset": 0,
            "limit": 20,
        }
        if not p.get("snapshot_id"):
            self.status.setText("홈에서 색인 / 변경 반영을 실행해주세요.")
            return
        self.begin("search", p, push)
        self.stack.setCurrentWidget(self.search_panel)
        self.title.setText("무기 검색")
        self.query.setText(p.get("text", ""))
        self.size.setCurrentIndex(max(0, self.size.findData(p.get("size", ""))))
        self.tag.setCurrentIndex(max(0, self.tag.findData(p.get("tag", ""))))
        self.search_tree.clear()
        self.submit("weapons", p, self.show_search)

    def fill(self, tree, data, append=False):
        if not append:
            tree.clear()
        for value in data.get("items", []):
            info = []
            if value.get("conditions"):
                info.append("추가 조건")
            if value.get("special"):
                info.append("특수 작용")
            if value.get("space_fauna"):
                info.append("우주생물 계열")
            if value.get("duplicate"):
                info.append("정의 후보 · " + source_label(value["source_ref"]))
            if value["type"] == "family":
                item = QTreeWidgetItem([value["name"], f"{value['count']}개", " · ".join(info)])
                item.setChildIndicatorPolicy(QTreeWidgetItem.ChildIndicatorPolicy.ShowIndicator)
            else:
                item = QTreeWidgetItem([value["name"], value["size_label"], " · ".join(info)])
                item.setToolTip(0, value["game_id"] + " · " + source_label(value["source_ref"]))
            item.setData(0, Qt.ItemDataRole.UserRole, value)
            tree.addTopLevelItem(item)

    def show_search(self, data):
        if self.error(data):
            return
        self.current["data"] = data
        p = self.current["payload"]
        self.title.setText("무기 검색")
        self.query.setText(p.get("text", ""))
        self.size.setCurrentIndex(max(0, self.size.findData(p.get("size", ""))))
        self.tag.setCurrentIndex(max(0, self.tag.findData(p.get("tag", ""))))
        self.fill(self.search_tree, data)
        self.more_search.setEnabled(data.get("truncated", False))
        self.status.setText(self.list_status(data))
        self.restore_tree(self.search_tree)

    def list_status(self, data):
        if not data.get("available"):
            return (
                "이 자료에는 무기 정보가 없습니다. 홈에서 색인하거나 새 자료로 보기를 선택해주세요."
            )
        if not data.get("coverage_complete"):
            return "일부 자료의 목록을 표시합니다."
        return f"{data.get('total', 0)}개 계열/항목 · 기본 게임 파일 기준" + (
            " · 이전 자료" if data["snapshot_id"] != self.manager.active_snapshot else ""
        )

    def error(self, data):
        if data.get("status") == "error":
            self.status.setText(
                "자료를 읽지 못했습니다: "
                + str(data.get("diagnostics", [{}])[0].get("code", "ERROR"))
            )
            if self.current:
                self.current["data"] = {}
            self.weapon_text.clear()
            self.weapon_sources.clear()
            self.refresh_pin_actions()
            self.tech_text.clear()
            self.search_tree.clear()
            self.related_tree.clear()
            self.link_list.clear()
            return True
        return False

    def expand_group(self, item):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if not value:
            return
        if value.get("type") == "more":
            self.fetch_group(item.parent(), value["offset"])
            return
        if value.get("type") != "family":
            return
        self.expanded.add(value["group_id"])
        if item.childCount():
            return
        self.fetch_group(item, 0)

    def fetch_group(self, item, offset):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        p = dict(
            self.current["related_payload"]
            if self.current["kind"] == "technology"
            else self.current["payload"]
        )
        p.update(group_id=value["group_id"], grouped=False, offset=offset)

        def loaded(data):
            if self.error(data):
                return
            for index in range(item.childCount() - 1, -1, -1):
                child = item.child(index)
                if (child.data(0, Qt.ItemDataRole.UserRole) or {}).get("type") == "more":
                    item.takeChild(index)
            for child_data in data.get("items", []):
                info = "추가 조건" if child_data["conditions"] else ""
                if child_data.get("duplicate"):
                    info += " · 정의 후보 · " + source_label(child_data["source_ref"])
                child = QTreeWidgetItem([child_data["name"], child_data["size_label"], info])
                child.setData(0, Qt.ItemDataRole.UserRole, child_data)
                item.addChild(child)
                if child_data == self.current.get("selected"):
                    item.treeWidget().setCurrentItem(child)
            if data.get("truncated"):
                child = QTreeWidgetItem(["더 보기"])
                child.setData(
                    0,
                    Qt.ItemDataRole.UserRole,
                    {"type": "more", "offset": offset + len(data["items"])},
                )
                item.addChild(child)

        self.submit("weapons", p, loaded, "weapon-group:" + value["group_id"])

    def choose_weapon(self, item, column=0):
        value = item.data(0, Qt.ItemDataRole.UserRole)
        if not value:
            return
        if value.get("type") == "more":
            self.fetch_group(item.parent(), value["offset"])
        elif value.get("type") == "family":
            item.setExpanded(True)
        else:
            self.open_weapon(
                {
                    "snapshot_id": value["snapshot_id"],
                    "entity_key": value["entity_key"],
                    "game_id": value["game_id"],
                }
            )

    def open_weapon(self, p, push=True, data=None, connections=False):
        self.begin("weapon", p, push)
        self.current["focus_links"] = connections
        self.stack.setCurrentWidget(self.weapon_panel)
        self.weapon_text.clear()
        self.link_list.clear()
        self.weapon_sources.clear()
        self.refresh_pin_actions()
        if data is not None:
            self.show_weapon(data)
        else:
            self.submit("weapon_detail", p, self.show_weapon)

    def show_weapon(self, data):
        if self.error(data):
            return
        self.weapon_sources.clear()
        self.current["data"] = data
        if data.get("status") in {"ambiguous", "not_found", "missing_data"}:
            self.weapon_text.setPlainText(
                "부품 정의를 선택해주세요."
                if data.get("items")
                else "이 자료에서 부품 정의를 읽을 수 없습니다."
            )
            for candidate in data.get("items", []):
                self.add_link(
                    {
                        **candidate,
                        "kind": "component_template",
                        "status": "resolved",
                        "name": candidate["name"],
                    }
                )
            self.status.setText("정의 선택 필요")
            return
        self.current["data"] = data
        self.current["section_offsets"] = {}
        self.current["resource_lines"] = set()
        self.title.setText(data["summary"]["name"])
        self.status.setText(
            "기본 게임 파일 기준"
            + (" · 일부 자료" if data["status"] == "partial" else "")
            + (
                " · 이전 자료"
                if data["identity"]["snapshot_id"] != self.manager.active_snapshot
                else ""
            )
        )
        summary = data["summary"]
        lines = [summary["name"], summary["size_label"], ""]
        lines.extend(numeric_detail_lines(data))
        if data["description"]:
            lines.extend(["", data["description"]])
        lines.extend(["", "기본 수치 기준 · 실전 보정은 적용하지 않습니다."])
        if data["effects"]:
            lines.append("특수 작용이 있습니다.")
        if not data["resources_complete"]:
            lines.append("자원 선언에 추가 원문이 있습니다.")
        self.weapon_text.setPlainText("\n".join(lines))
        self.append_section("resources", data["resources"])
        self.append_section("conditions", data["conditions"])
        self.append_section("effects", data["effects"])
        self.append_section("links", data["links"])
        for name in ("resources", "conditions", "effects", "links"):
            self.current["section_offsets"][name] = len(data[name])
            self.section_buttons[name].setEnabled(data.get(name + "_more", False))
        if not data["links"] and not data["links_complete"]:
            self.link_list.addItem("기술 요구 목록의 전체 범위를 확인하지 못했습니다.")
        identity = data["identity"]
        self.weapon_technical.setPlainText(
            "\n".join(
                [
                    "ID: " + identity["game_id"],
                    "스냅샷: " + identity["snapshot_id"],
                    "정의: " + identity["entity_key"],
                    "정책: " + data["policy"],
                    *data["diagnostics"],
                    source_label(data["source_ref"]),
                ]
            )
        )
        self.refresh_pin_actions()
        if self.current.get("focus_links"):
            self.link_list.setFocus()
            if self.link_list.count():
                self.link_list.setCurrentRow(0)
        self.weapon_sources.insertItem(0, "부품 정의 원문", data["source_ref"])
        self.weapon_sources.setCurrentIndex(0)
        self.weapon_text.verticalScrollBar().setValue(self.current.get("scroll", 0))

    def append_section(self, name, items):
        if name == "links":
            for value in items:
                self.add_link(value)
        elif name == "resources":
            view = project({**self.current["data"], "resources": items})
            for key in ("cost", "upkeep"):
                for line in field_lines(view, key):
                    if line not in self.current["resource_lines"]:
                        self.current["resource_lines"].add(line)
                        self.weapon_text.appendPlainText(line)
        else:
            for value in items:
                label = ("조건 · " if name == "conditions" else "특수 작용 · ") + value["name"]
                self.weapon_text.appendPlainText(label)
                self.weapon_sources.addItem(label, value["source_ref"])

    def add_link(self, value):
        label = ("요구 기술 · " if value["kind"] == "technology" else "부품 · ") + value["name"]
        if value.get("status") != "resolved":
            label += " · 정의 선택 필요"
        if value.get("duplicate") and value.get("source_ref"):
            label += " · " + source_label(value["source_ref"])
        item = QListWidgetItem(label)
        item.setData(Qt.ItemDataRole.UserRole, value)
        self.link_list.addItem(item)

    def choose_link(self, item):
        value = item.data(Qt.ItemDataRole.UserRole)
        if not value:
            return
        p = {
            "snapshot_id": self.current["payload"]["snapshot_id"],
            "game_id": value["game_id"],
            "entity_key": value.get("entity_key"),
            "card_uid": self.origin_uid(),
        }
        if value["kind"] == "technology":
            self.open_technology(p)
        else:
            self.open_weapon(p)

    def load_section(self, name):
        if not self.current or self.current["kind"] != "weapon":
            return
        offset = self.current.get("section_offsets", {}).get(name, 0)
        p = {**self.current["payload"], "section": name, "offset": offset, "limit": 20}

        def loaded(data):
            if self.error(data):
                return
            self.append_section(name, data.get("items", []))
            self.current["data"][name].extend(data.get("items", []))
            self.current["data"][name + "_more"] = data.get("more", False)
            self.section_buttons[name].setEnabled(data.get("more", False))
            self.current["section_offsets"][name] = offset + len(data.get("items", []))
            self.status.setText(
                "추가 항목을 표시했습니다." if data.get("items") else "추가 항목이 없습니다."
            )

        self.submit("weapon_detail", p, loaded, "weapon-section:" + name)

    def open_technology(self, p, push=True, data=None):
        self.begin("technology", p, push)
        self.stack.setCurrentWidget(self.tech_panel)
        self.tech_text.clear()
        self.tech_links.clear()
        self.related_tree.clear()
        self.tech_sources.clear()
        self.tech_proof.clear()
        self.tech_technical.clear()
        if data is not None:
            self.show_technology(data)
        else:
            self.submit("answer", p, self.show_technology)

    def show_technology(self, data):
        if self.error(data):
            return
        view = data.get("card_view")
        if not view:
            self.tech_text.setPlainText(text_view(data))
            for candidate in data.get("results", []):
                item = QListWidgetItem(
                    candidate["display_name"]
                    + " · "
                    + source_label(candidate["definition_source_ref"])
                )
                item.setData(
                    Qt.ItemDataRole.UserRole,
                    {
                        "snapshot_id": candidate["snapshot_id"],
                        "game_id": candidate["game_id"],
                        "entity_key": candidate["entity_key"],
                    },
                )
                self.tech_links.addItem(item)
            return
        self.current["data"] = data
        self.title.setText(view["name"])
        self.tech_text.setPlainText(readable_detail(view))
        proof = []
        for key, value in view["fields"].items():
            proof.extend(
                [
                    FIELD_LABELS[key] + "  " + field_text(view, key),
                    "원래 표현: " + str(value.get("raw")),
                ]
            )
            if value.get("reason"):
                proof.append(value["reason"])
            proof.extend(source_label(ref) for ref in value.get("sources", []))
            proof.append("")
        self.tech_proof.setPlainText("\n".join(proof))
        identity = view["identity"]
        metadata = [
            "ID: " + identity["game_id"],
            "스냅샷: " + identity["snapshot_id"],
            "정의: " + identity["entity_key"],
            "이름 대체: " + view["fallback"],
        ]
        metadata.extend(
            "SHA256: " + sha
            for sha in sorted({ref["file_sha256"] for ref in collect_sources(data)})
        )
        self.tech_technical.setPlainText("\n".join(metadata) + "\n\n" + text_view(data))
        self.tech_tabs.setCurrentIndex(self.current.get("tech_tab", 0))

        for ref in collect_sources(data):
            self.tech_sources.addItem(source_label(ref), ref)
        for value in view["prerequisites"]:
            item = QListWidgetItem("선행 · " + value["name"])
            item.setData(
                Qt.ItemDataRole.UserRole,
                {
                    "snapshot_id": view["identity"]["snapshot_id"],
                    "game_id": value["game_id"],
                    "entity_key": value["entity_key"],
                },
            )
            self.tech_links.addItem(item)
        self.current["card_uid"] = data.get("card_request", {}).get("uid") or self.current[
            "payload"
        ].get("card_uid")
        self.update_button.setEnabled(bool(self.current["card_uid"]))
        p = {
            "snapshot_id": view["identity"]["snapshot_id"],
            "technology_id": view["identity"]["game_id"],
            "grouped": True,
            "offset": 0,
            "limit": 20,
        }
        self.current["related_payload"] = p
        self.submit("weapons", p, self.show_related, "weapon-related")
        self.tech_text.verticalScrollBar().setValue(self.current.get("scroll", 0))

    def show_related(self, data):
        if self.error(data):
            return
        self.current["related_data"] = data
        self.fill(self.related_tree, data)
        self.more_related.setEnabled(data.get("truncated", False))
        self.status.setText(self.list_status(data))
        self.restore_tree(self.related_tree)

    def choose_technology(self, item):
        p = item.data(Qt.ItemDataRole.UserRole)
        if p:
            self.open_technology(p)

    def pin_technology(self):
        if (
            self.current
            and self.current["kind"] == "technology"
            and self.current.get("data", {}).get("card_view")
        ):
            identity = self.current["data"]["card_view"]["identity"]
            self.manager.pin(
                Card.create(
                    kind="technology",
                    **{key: identity[key] for key in ("snapshot_id", "game_id", "entity_key")},
                )
            )

    def update_card(self):
        uid = self.current.get("card_uid") if self.current else None
        if uid:
            self.manager.manage_card(uid)
            self.manager.update_card()

    def origin_uid(self):
        return self.current.get("payload", {}).get("card_uid") if self.current else None

    def pin_weapon(self):
        data = self.current.get("data", {}) if self.current and self.current["kind"] == "weapon" else {}
        if data.get("identity"):
            self.manager.pin_entity("component_template", data["identity"], self.origin_uid())

    def pin_tree(self, tree):
        item = tree.currentItem()
        value = item.data(0, Qt.ItemDataRole.UserRole) if item else None
        if value and value.get("type") not in {"family", "more"}:
            self.manager.pin_entity("component_template", value, self.origin_uid())

    def pin_link(self):
        item = self.link_list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        if value and self.current and self.current["kind"] == "weapon":
            self.manager.pin_entity(value["kind"], {**value, "snapshot_id": self.current["payload"]["snapshot_id"]}, self.origin_uid())

    def open_selected_link(self):
        if self.link_list.currentItem():
            self.choose_link(self.link_list.currentItem())

    def refresh_pin_actions(self):
        if not hasattr(self, "related_pin"):
            return
        data = self.current.get("data", {}) if self.current else {}
        identity = data.get("identity", {}) if self.current and self.current["kind"] == "weapon" else {}
        self.weapon_pin.setEnabled(bool(identity))
        def caption(kind, value, default):
            if value and self.manager.find_card(kind, value.get("snapshot_id"), value.get("game_id"), value.get("entity_key")):
                return "고정됨 · 기존 카드 선택"
            return default
        self.weapon_pin.setText(caption("weapon", identity, "무기 카드 고정"))
        for tree, control in ((self.search_tree, self.search_pin), (self.related_tree, self.related_pin)):
            item = tree.currentItem()
            value = item.data(0, Qt.ItemDataRole.UserRole) if item else None
            valid = bool(value and value.get("type") not in {"family", "more"})
            control.setEnabled(valid)
            control.setText(caption("weapon", value if valid else None, "선택한 무기 카드 고정"))
        item = self.link_list.currentItem()
        value = item.data(Qt.ItemDataRole.UserRole) if item else None
        valid = bool(value and self.current and self.current["kind"] == "weapon")
        self.link_pin.setEnabled(valid)
        self.link_open.setEnabled(valid)
        if valid:
            value = {**value, "snapshot_id": self.current["payload"]["snapshot_id"]}
        self.link_pin.setText(caption("technology" if value and value.get("kind") == "technology" else "weapon",
                                      value if valid else None, "선택한 연결 카드 고정"))

    def open_latest(self):
        sid = self.manager.active_snapshot
        if not sid or self.current is None or sid == self.current["payload"].get("snapshot_id"):
            self.manager.navigate("홈")
            return
        p = {**self.current["payload"], "snapshot_id": sid}
        if self.current["kind"] == "technology":
            p.pop("entity_key", None)
            self.open_technology(p)
        elif self.current["kind"] == "weapon":
            p.pop("entity_key", None)
            self.open_weapon(p)
        else:
            p["offset"] = 0
            self.search(payload=p)

    def next_search(self):
        if self.current and self.current.get("data", {}).get("truncated"):
            data = self.current["data"]
            p = {**self.current["payload"], "offset": data["offset"] + len(data["items"])}
            self.search(payload=p)

    def next_related(self):
        data = self.current.get("related_data", {}) if self.current else {}
        if not data.get("truncated"):
            return
        p = {**self.current["related_payload"], "offset": data["offset"] + len(data["items"])}
        self.generation += 1
        self.current["related_payload"] = p
        self.expanded = set()
        self.submit("weapons", p, self.show_related, "weapon-related")

    def restore_tree(self, tree):
        for index in range(tree.topLevelItemCount()):
            item = tree.topLevelItem(index)
            value = item.data(0, Qt.ItemDataRole.UserRole)
            if value.get("group_id") in self.current.get("expanded", []):
                item.setExpanded(True)
            if value == self.current.get("selected"):
                tree.setCurrentItem(item)
        tree.verticalScrollBar().setValue(self.current.get("tree_scroll", 0))

    def back(self):
        if not self.history:
            return
        value = self.history.pop()
        self.generation += 1
        self.current = value
        self.expanded = set(value.get("expanded", []))
        self.back_button.setEnabled(bool(self.history))
        if value["language"] != self.manager.prefs.language or "data" not in value:
            p = value["payload"]
            if value["kind"] == "technology":
                self.open_technology(p, push=False)
            elif value["kind"] == "weapon":
                self.open_weapon(p, push=False)
            else:
                self.search(payload=p, push=False)
            return
        self.manager.navigate("무기 검색")
        if value["kind"] == "search":
            self.stack.setCurrentWidget(self.search_panel)
            self.show_search(value["data"])
        elif value["kind"] == "weapon":
            self.stack.setCurrentWidget(self.weapon_panel)
            self.link_list.clear()
            self.show_weapon(value["data"])
        else:
            self.stack.setCurrentWidget(self.tech_panel)
            self.tech_links.clear()
            self.related_tree.clear()
            self.tech_sources.clear()
            self.show_technology(value["data"])
