"""Toolkit-independent overlay transitions and bounded client-relative geometry."""
from dataclasses import dataclass
from enum import StrEnum


class Mode(StrEnum):
    HIDDEN = "hidden"
    PASSIVE = "passive"
    INTERACTIVE = "interactive"


@dataclass
class OverlayState:
    enabled: bool = True
    mode: Mode = Mode.HIDDEN

    def observe(self, eligible: bool):
        if not eligible or not self.enabled:
            self.mode = Mode.HIDDEN
        elif self.mode == Mode.HIDDEN:
            self.mode = Mode.PASSIVE
        return self.mode

    def toggle(self, eligible: bool):
        if eligible:
            self.enabled = True
            self.mode = Mode.PASSIVE if self.mode == Mode.INTERACTIVE else Mode.INTERACTIVE
        return self.mode

    def hide(self):
        self.enabled = False
        self.mode = Mode.HIDDEN


def bounded_rect(rect, width, height):
    x, y, w, h = rect
    w, h = min(max(180, w), width), min(max(100, h), height)
    return max(0, min(x, width-w)), max(0, min(y, height-h)), w, h


def place_card(rect, occupied, width, height, origin=None):
    """Prefer free client-relative space; never move an existing card."""
    rect = bounded_rect(rect, width, height)
    _, _, w, h = rect
    candidates = []
    if origin:
        x, y, ow, oh = origin
        candidates.extend(((x + ow + 12, y), (x, y + oh + 12)))
    candidates.extend((x, y) for y in range(12, max(13, height - h + 1), max(24, h + 12))
                      for x in range(12, max(13, width - w + 1), max(24, w + 12)))
    for x, y in candidates:
        if x < 0 or y < 0 or x + w > width or y + h > height:
            continue
        if all(x + w <= ox or ox + ow <= x or y + h <= oy or oy + oh <= y
               for ox, oy, ow, oh in occupied):
            return [x, y, w, h]
    offset = 24 * len(occupied)
    return list(bounded_rect((12 + offset, 12 + offset, w, h), width, height))
