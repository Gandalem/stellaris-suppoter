"""Plain-text technology summary and explicit management actions."""

from __future__ import annotations

from PySide6.QtCore import QEvent, QPointF, QSize, Qt
from PySide6.QtGui import QPainter, QTextLayout, QTextOption
from PySide6.QtWidgets import (
    QDialog,
    QDialogButtonBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from stellaris_supporter.card_information import (
    FIELD_LABELS,
    STATE_TEXT,
    field_text,
    readable_detail,
)

from .presentation import collect_sources, source_label


def wrapped(text, font, width, maximum=2):
    """Qt shapes Unicode first; elide only the last visible line."""
    layout = QTextLayout(str(text).replace("\n", " "), font)
    option = QTextOption()
    option.setWrapMode(QTextOption.WrapMode.WrapAtWordBoundaryOrAnywhere)
    layout.setTextOption(option)
    layout.beginLayout()
    lines = []
    while len(lines) < maximum:
        line = layout.createLine()
        if not line.isValid():
            break
        line.setLineWidth(max(1, width))
        lines.append((line.textStart(), line.textLength()))
    more = layout.createLine().isValid()
    layout.endLayout()
    from PySide6.QtGui import QFontMetrics

    metrics = QFontMetrics(font)
    # QString positions are UTF-16 offsets, unlike Python indices.
    raw = layout.text().encode("utf-16-le")
    result = []
    for index, (start, length) in enumerate(lines):
        end = None if index == len(lines) - 1 and more else (start + length) * 2
        part = raw[start * 2 : end].decode("utf-16-le")
        result.append(metrics.elidedText(part, Qt.TextElideMode.ElideRight, max(1, width)))
    return result


class LimitedLabel(QLabel):
    def __init__(self, text):
        super().__init__(text)
        self.setTextFormat(Qt.TextFormat.PlainText)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Fixed)
        self.setFixedHeight(self.fontMetrics().lineSpacing() * 2 + 2)
        self.setAccessibleName(text)

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() == QEvent.Type.FontChange:
            self.setFixedHeight(self.fontMetrics().lineSpacing() * 2 + 2)

    def setText(self, text):
        super().setText(text)
        self.setAccessibleName(text)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        for index, line in enumerate(wrapped(self.text(), self.font(), self.width())):
            painter.drawText(
                0, self.fontMetrics().ascent() + index * self.fontMetrics().lineSpacing(), line
            )


class TechnologySummary(QWidget):
    def __init__(self):
        super().__init__()
        self.view = None
        self.fields = []
        self.visible_lines = []
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def minimumSizeHint(self):
        return QSize(0, 0)

    def set_data(self, view, fields):
        self.view, self.fields = view, list(fields)
        self.setAccessibleName(readable_detail(view))
        self.update()

    def rows(self, width, height):
        view = self.view
        if view is None:
            return []
        line_height = self.fontMetrics().lineSpacing()
        capacity = max(0, height // max(1, line_height))
        footer = "기본 게임 파일 기준" + (" · 일부 자료" if view["partial"] else "")
        groups = []
        done = set()
        members = {}
        for position, key in enumerate(self.fields):
            if key in done:
                continue
            done.add(key)
            if key in {"area", "tier"}:
                # Adjacent area/tier have a compact single-line presentation.
                other = "tier" if key == "area" else "area"
                values = [field_text(view, key)]
                if (
                    position + 1 < len(self.fields)
                    and self.fields[position + 1] == other
                    and other not in done
                ):
                    values.append(field_text(view, other))
                    done.add(other)
                    members[key] = {key, other}
                groups.append((key, [" · ".join(values)]))
            elif key == "prerequisites":
                items = view["prerequisites"]
                lines = ["선행 기술"]
                for item in items[:3]:
                    lines.extend(wrapped(item["name"], self.font(), width, 2))
                if len(items) > 3:
                    lines.append(f"외 {len(items) - 3}개")
                if not items:
                    lines.append("없음" if view["prerequisites_complete"] else "자료 확인 필요")
                elif not view["prerequisites_complete"]:
                    lines.append("일부 목록")
                groups.append((key, lines))
            elif key == "description":
                if view["fields"][key]["value"]:
                    groups.append((key, wrapped(field_text(view, key), self.font(), width, 2)))
            elif key in FIELD_LABELS:
                groups.append(
                    (
                        key,
                        wrapped(
                            FIELD_LABELS[key] + "  " + field_text(view, key), self.font(), width, 2
                        ),
                    )
                )
            else:
                groups.append((key, ["기타 항목 · 상세 보기"]))
        if view["flags"]:
            groups.append(("flags", [" · ".join(view["flags"])]))
        hidden = set()

        def total():
            return sum(len(lines) for _, lines in groups) + 1 + (1 if hidden else 0)

        # Optional information folds first, regardless of the chosen display order.
        for key in ("description", "category", "flags"):
            if total() > capacity:
                for index, (name, _) in enumerate(groups):
                    if name == key:
                        groups.pop(index)
                        hidden.update(members.get(key, {key}))
                        break
        for index, (key, lines) in enumerate(groups):
            if key == "prerequisites" and total() > capacity and len(lines) > 1:
                count = len(view["prerequisites"])
                groups[index] = (
                    key,
                    [
                        f"선행 기술 {count}개"
                        + (" · 일부 목록" if not view["prerequisites_complete"] else "")
                    ],
                )
                hidden.add(key)
        while groups and total() > capacity:
            key, _ = groups.pop()
            hidden.update(members.get(key, {key}))
        result = [line for _, lines in groups for line in lines]
        if hidden:
            result.append(f"추가 {len(hidden)}항목 · 상세 보기")
        result.append(footer)
        return result[-capacity:] if capacity else []

    def paintEvent(self, event):
        if self.view is None:
            return
        painter = QPainter(self)
        metrics = self.fontMetrics()
        self.visible_lines = self.rows(self.width(), self.height())
        for index, line in enumerate(self.visible_lines):
            painter.setPen(self.palette().windowText().color())
            text = metrics.elidedText(line, Qt.TextElideMode.ElideRight, max(1, self.width()))
            painter.drawText(QPointF(0, metrics.ascent() + index * metrics.lineSpacing()), text)


class FieldsDialog(QDialog):
    def __init__(self, fields, parent=None, labels=None):
        super().__init__(parent)
        self.setWindowTitle("카드 표시 항목")
        self.resize(390, 440)
        layout = QVBoxLayout(self)
        layout.addWidget(QLabel("표시할 항목을 선택하고 순서를 바꾸세요."))
        self.items = QListWidget()
        labels = labels or FIELD_LABELS
        keys = list(fields) + [key for key in labels if key not in fields]
        for key in keys:
            item = QListWidgetItem(labels.get(key, "기타: " + key))
            item.setData(Qt.ItemDataRole.UserRole, key)
            item.setFlags(item.flags() | Qt.ItemFlag.ItemIsUserCheckable)
            item.setCheckState(Qt.CheckState.Checked if key in fields else Qt.CheckState.Unchecked)
            self.items.addItem(item)
        layout.addWidget(self.items)
        row = QHBoxLayout()
        for title, delta in (("위로", -1), ("아래로", 1)):
            button = QPushButton(title)
            button.clicked.connect(lambda checked=False, delta=delta: self.move_item(delta))
            row.addWidget(button)
        layout.addLayout(row)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def accept(self):
        if len(self.selected()) > 20:
            QMessageBox.information(
                self, "카드 표시 항목", "항목은 최대 20개까지 선택할 수 있습니다."
            )
            return
        super().accept()

    def move_item(self, delta):
        row = self.items.currentRow()
        if 0 <= row + delta < self.items.count():
            self.items.insertItem(row + delta, self.items.takeItem(row))
            self.items.setCurrentRow(row + delta)

    def selected(self):
        return [
            self.items.item(i).data(Qt.ItemDataRole.UserRole)
            for i in range(self.items.count())
            if self.items.item(i).checkState() == Qt.CheckState.Checked
        ]


class TechnologyDetail(QDialog):
    def __init__(self, data, manager):
        super().__init__(manager)
        view = data["card_view"]
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(view["name"] + " · 기술 상세")
        self.resize(760, 760)
        layout = QVBoxLayout(self)
        readable = QPlainTextEdit(readable_detail(view))
        readable.setReadOnly(True)
        layout.addWidget(readable, 3)
        layout.addWidget(QLabel("선행 기술을 두 번 누르면 같은 데이터의 참조를 엽니다."))
        prerequisites = QListWidget()
        prerequisites.setMaximumHeight(110)
        for value in view["prerequisites"]:
            item = QListWidgetItem(value["name"])
            item.setData(Qt.ItemDataRole.UserRole, value)
            prerequisites.addItem(item)
        prerequisites.itemDoubleClicked.connect(
            lambda item: manager.open_prerequisite(view, item.data(Qt.ItemDataRole.UserRole))
        )
        layout.addWidget(prerequisites)
        lines = []
        for key, value in view["fields"].items():
            lines.append(FIELD_LABELS[key] + "  " + field_text(view, key))
            lines.append("원래 표현: " + str(value.get("raw") or "없음"))
            if value["status"] != "resolved":
                lines.append("상태: " + STATE_TEXT.get(value["status"], value["status"]))
            if value.get("reason"):
                lines.append(value["reason"])
            if key == "cost":
                if value.get("candidate_count", 0) > 32:
                    lines.append(f"변수 후보 {value['candidate_count']}개 중 출처 32개 표시")
                lines.extend("정의·값 출처: " + source_label(ref) for ref in value["sources"])
        proof = QPlainTextEdit("\n".join(lines))
        proof.setReadOnly(True)
        layout.addWidget(QLabel("값의 근거"))
        layout.addWidget(proof, 2)
        sources = manager.source_list(layout)
        for ref in collect_sources(data):
            sources.addItem(source_label(ref), ref)
        technical = QGroupBox("기술 정보 · ID / 데이터 기준 / 원문 / 진단")
        technical.setCheckable(True)
        technical.setChecked(False)
        technical_layout = QVBoxLayout(technical)
        from .presentation import text_view

        identity = view["identity"]
        details = [
            "ID: " + identity["game_id"],
            "스냅샷: " + identity["snapshot_id"],
            "정의: " + identity["entity_key"],
            "이름 대체: " + view["fallback"],
        ]
        details.extend("SHA256: " + ref["file_sha256"] for ref in collect_sources(data))
        raw = QPlainTextEdit("\n".join(details) + "\n\n" + text_view(data))
        raw.setReadOnly(True)
        raw.setVisible(False)
        technical.toggled.connect(raw.setVisible)
        technical_layout.addWidget(raw)
        layout.addWidget(technical)
