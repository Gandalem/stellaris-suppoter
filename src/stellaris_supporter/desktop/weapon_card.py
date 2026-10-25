"""Bounded, plain-text weapon overlay summary with complete numeric tokens."""

from PySide6.QtCore import QPointF
from PySide6.QtGui import QPainter
from PySide6.QtWidgets import QSizePolicy, QWidget

from stellaris_supporter.weapon_cards import (
    DEFAULT_FIELDS,
    POLICY_NOTICE,
    field_lines,
    policy_keys,
    summary_text,
)

from .technology_card import wrapped


class WeaponSummary(QWidget):
    def __init__(self):
        super().__init__()
        self.view = None
        self.fields = []
        self.historical = False
        self.visible_lines = []
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)

    def set_data(self, view, fields, historical=False):
        self.view, self.fields, self.historical = view, list(dict.fromkeys(fields)), historical
        self.setAccessibleName(summary_text(view, self.fields))
        self.update()

    def rows(self, width, height):
        if self.view is None:
            return []
        metrics = self.fontMetrics()
        capacity = height // max(1, metrics.lineSpacing())
        if capacity <= 0:
            return []
        view = self.view
        footer = (
            "기본 게임 파일 기준"
            + (" · 일부 자료" if view["partial"] else "")
            + (" · 이전 자료" if self.historical else "")
        )
        badges = [view["size"]]
        badges.extend(
            label
            for label, on in (("추가 조건", view["conditions"]), ("특수 작용", view["effects"]))
            if on
        )
        badge = " · ".join(badges)
        fixed = (
            wrapped(badge, self.font(), width, 1)
            if metrics.horizontalAdvance(badge) <= width
            else wrapped(view["size"], self.font(), width, 1)
            + wrapped(" · ".join(badges[1:]), self.font(), width, 1)
        )
        groups = [[set(), wrapped(view["family"], self.font(), width, 1)]] if view["family"] else []
        policy = policy_keys(view, self.fields)
        if policy:
            groups.append([policy, wrapped(POLICY_NOTICE, self.font(), width, 2)])
        hidden = set()
        keys = self.fields
        done = set()
        for key in keys:
            if key in done:
                continue
            done.add(key)
            members = {key}
            lines = field_lines(view, key)
            tracking_lines = field_lines(view, "tracking")
            if (
                key == "accuracy"
                and lines
                and tracking_lines
                and "tracking" in keys
                and "tracking" not in done
            ):
                combined = lines[0] + " · " + tracking_lines[0]
                if metrics.horizontalAdvance(combined) <= width:
                    lines = [combined]
                    members.add("tracking")
                    done.add("tracking")
            visible = []
            for line in lines:
                if metrics.horizontalAdvance(line) <= width:
                    visible.append(line)
                elif key == "prerequisites":
                    visible += wrapped(line, self.font(), width, 2)
                else:
                    # Keep the numeric suffix intact, and wrap only the label.
                    label, separator, value = line.rpartition("  ")
                    if separator and metrics.horizontalAdvance(value) <= width:
                        visible += wrapped(label, self.font(), width, 2) + [value]
                    else:
                        hidden.update(members)
            if key in {"cost", "upkeep", "prerequisites"} and len(visible) > 3:
                visible = visible[:2] + ["추가 항목 있음"]
                hidden.update(members)
            if visible:
                groups.append([members, visible])
            elif key not in policy:
                hidden.update(members)

        def total():
            return len(fixed) + sum(len(lines) for _, lines in groups) + 1 + bool(hidden)

        # Optional groups fold before the six essentials, respecting selected order within each class.
        for essential in (False, True):
            for index in range(len(groups) - 1, -1, -1):
                if total() <= capacity:
                    break
                members, lines = groups[index]
                if bool(members & set(DEFAULT_FIELDS)) == essential:
                    hidden.update(members)
                    groups.pop(index)
        if len(fixed) + 1 + bool(hidden) > capacity:
            fixed = fixed[: max(0, capacity - 1 - bool(hidden))]
        result = fixed + [line for _, lines in groups for line in lines]
        if hidden:
            result.append(f"추가 {len(hidden)}항목 · 상세 보기")
        result += wrapped(footer, self.font(), width, 1)
        return result[:capacity]

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setPen(self.palette().windowText().color())
        metrics = self.fontMetrics()
        self.visible_lines = self.rows(self.width(), self.height())
        for index, line in enumerate(self.visible_lines):
            painter.drawText(QPointF(0, metrics.ascent() + index * metrics.lineSpacing()), line)
