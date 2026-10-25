"""Own-window Windows API smoke; does not certify actual game input passthrough."""
import json
import os

from PySide6.QtWidgets import QApplication, QWidget

from stellaris_supporter.desktop.windows import Windows


def main():
    app = QApplication([])
    first, second = QWidget(), QWidget()
    first.setWindowTitle("Native overlay acceptance")
    first.resize(640, 360)
    second.setWindowTitle("Native hotkey conflict acceptance")
    native, other = Windows(), Windows()
    try:
        first.show()
        second.show()
        app.processEvents()
        hwnd = int(first.winId())
        identity = native.identity(hwnd)
        assert identity and identity[0] == os.getpid()
        assert native.track(identity[1]) is None
        second.hide()
        app.processEvents()
        target = native.track(identity[1])
        assert target and target.hwnd == hwnd
        native.passive(hwnd, True)
        flags = native.user.GetWindowLongPtrW(hwnd, -20)
        assert flags & 0x20 and flags & 0x08000000
        native.passive(hwnd, False)
        flags = native.user.GetWindowLongPtrW(hwnd, -20)
        assert not flags & 0x20 and not flags & 0x08000000
        native.bind_hotkeys(hwnd, "Ctrl+Shift+Z", "Ctrl+Shift+H")
        try:
            other.bind_hotkeys(int(second.winId()), "Ctrl+Shift+Z", "Ctrl+Shift+H")
            raise AssertionError("Conflict not detected")
        except ValueError:
            pass
        native.release()
        other.bind_hotkeys(int(second.winId()), "Ctrl+Shift+Z", "Ctrl+Shift+H")
        other.release()
        first.showMinimized()
        app.processEvents()
        assert native.track(identity[1]) is None
        print(json.dumps({"native_own_window_identity": True, "ambiguity_rejected": True,
                          "passive_native_flags": True, "hotkey_conflict_release": True,
                          "minimized_hidden": True, "dpi": target.dpi, "actual_game_test": False}))
    finally:
        native.release()
        other.release()
        first.close()
        second.close()
        app.processEvents()


if __name__ == "__main__":
    main()
