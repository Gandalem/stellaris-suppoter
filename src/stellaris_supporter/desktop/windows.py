"""Windows window identity, client geometry and registered hotkeys. No hooks/injection."""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes as W
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Target:
    hwnd: int
    pid: int
    executable: str
    rect: tuple[int, int, int, int]
    dpi: int


def path_key(value):
    return os.path.normcase(os.path.abspath(value))


def parse_hotkey(value):
    if not isinstance(value, str):
        raise ValueError("단축키 형식이 올바르지 않습니다.")
    parts = [v.strip().upper() for v in value.split("+")]
    modifiers, key = 0, None
    for part in parts:
        if part in {"CTRL", "CONTROL", "ALT", "SHIFT"}:
            flag = {"CTRL": 2, "CONTROL": 2, "ALT": 1, "SHIFT": 4}[part]
            if modifiers & flag:
                raise ValueError("중복된 보조 키입니다.")
            modifiers |= flag
        elif key is None and (part == "SPACE" or len(part) == 1 and part.isascii() and part.isalnum()):
            key = 32 if part == "SPACE" else ord(part)
        else:
            raise ValueError("Ctrl/Alt/Shift와 영문·숫자·Space 조합을 사용해주세요.")
    if not modifiers or key is None:
        raise ValueError("보조 키와 일반 키를 함께 지정해주세요.")
    return modifiers | 0x4000, key


class Windows:
    def __init__(self):
        if os.name != "nt":
            raise OSError("게임 오버레이는 Windows에서 실행합니다.")
        self.user = ctypes.WinDLL("user32", use_last_error=True)
        self.kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        self.callback = ctypes.WINFUNCTYPE(W.BOOL, W.HWND, W.LPARAM)
        declarations = {
            "EnumWindows": ([self.callback, W.LPARAM], W.BOOL),
            "IsWindow": ([W.HWND], W.BOOL), "IsWindowVisible": ([W.HWND], W.BOOL),
            "IsIconic": ([W.HWND], W.BOOL), "GetForegroundWindow": ([], W.HWND),
            "GetWindowThreadProcessId": ([W.HWND, ctypes.POINTER(W.DWORD)], W.DWORD),
            "GetWindow": ([W.HWND, W.UINT], W.HWND),
            "GetWindowTextLengthW": ([W.HWND], ctypes.c_int),
            "GetWindowRect": ([W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
            "GetClientRect": ([W.HWND, ctypes.POINTER(W.RECT)], W.BOOL),
            "ClientToScreen": ([W.HWND, ctypes.POINTER(W.POINT)], W.BOOL),
            "GetDpiForWindow": ([W.HWND], W.UINT),
            "RegisterHotKey": ([W.HWND, ctypes.c_int, W.UINT, W.UINT], W.BOOL),
            "UnregisterHotKey": ([W.HWND, ctypes.c_int], W.BOOL),
            "SetWindowPos": ([W.HWND, W.HWND, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, W.UINT], W.BOOL),
            "SetForegroundWindow": ([W.HWND], W.BOOL), "ShowWindow": ([W.HWND, ctypes.c_int], W.BOOL),
            "GetWindowLongPtrW": ([W.HWND, ctypes.c_int], ctypes.c_ssize_t),
            "SetWindowLongPtrW": ([W.HWND, ctypes.c_int, ctypes.c_ssize_t], ctypes.c_ssize_t),
        }
        for name, (args, result) in declarations.items():
            function = getattr(self.user, name)
            function.argtypes, function.restype = args, result
        self.kernel.OpenProcess.argtypes = [W.DWORD, W.BOOL, W.DWORD]
        self.kernel.OpenProcess.restype = W.HANDLE
        self.kernel.QueryFullProcessImageNameW.argtypes = [W.HANDLE, W.DWORD, W.LPWSTR, ctypes.POINTER(W.DWORD)]
        self.kernel.QueryFullProcessImageNameW.restype = W.BOOL
        self.kernel.CloseHandle.argtypes = [W.HANDLE]
        self.kernel.CloseHandle.restype = W.BOOL
        self.bound = None
        self.registrations = {}
        self.serial = 100

    def identity(self, hwnd):
        if not self.user.IsWindow(hwnd):
            return None
        pid = W.DWORD()
        if not self.user.GetWindowThreadProcessId(hwnd, ctypes.byref(pid)):
            return None
        handle = self.kernel.OpenProcess(0x1000, False, pid.value)
        if not handle:
            return None
        try:
            size = W.DWORD(32768)
            buffer = ctypes.create_unicode_buffer(size.value)
            if not self.kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
                return None
            return pid.value, path_key(buffer.value)
        finally:
            self.kernel.CloseHandle(handle)

    def candidates(self, executable):
        wanted = path_key(executable)
        found = []
        @self.callback
        def visit(hwnd, unused):
            if (self.user.IsWindowVisible(hwnd) and not self.user.GetWindow(hwnd, 4)
                    and self.user.GetWindowTextLengthW(hwnd) > 0):
                identity = self.identity(hwnd)
                if identity and identity[1] == wanted:
                    found.append((int(hwnd), identity))
            return True
        self.user.EnumWindows(visit, 0)
        return found

    def track(self, executable):
        if not executable or not Path(executable).is_absolute():
            self.bound = None
            return None
        wanted = path_key(executable)
        if self.bound is not None:
            hwnd, identity = self.bound
            if identity[1] != wanted or self.identity(hwnd) != identity:
                self.bound = None
        if self.bound is None:
            candidates = self.candidates(executable)
            if len(candidates) != 1:
                return None
            self.bound = candidates[0]
        hwnd, (pid, image) = self.bound
        if not self.user.IsWindowVisible(hwnd) or self.user.IsIconic(hwnd):
            return None
        rect, point = W.RECT(), W.POINT()
        if not self.user.GetClientRect(hwnd, ctypes.byref(rect)) or not self.user.ClientToScreen(hwnd, ctypes.byref(point)):
            return None
        width, height = rect.right-rect.left, rect.bottom-rect.top
        if width <= 0 or height <= 0:
            return None
        return Target(hwnd, pid, image, (point.x, point.y, width, height), self.user.GetDpiForWindow(hwnd) or 96)

    def foreground(self):
        return int(self.user.GetForegroundWindow() or 0)

    def focus(self, target):
        if self.identity(target.hwnd) == (target.pid, target.executable):
            self.user.ShowWindow(target.hwnd, 9)
            return bool(self.user.SetForegroundWindow(target.hwnd))
        return False

    def passive(self, hwnd, enabled):
        flags = self.user.GetWindowLongPtrW(hwnd, -20)
        mask = 0x20 | 0x08000000
        self.user.SetWindowLongPtrW(hwnd, -20, flags | mask if enabled else flags & ~mask)
        self.user.SetWindowPos(hwnd, W.HWND(-1), 0, 0, 0, 0, 0x01 | 0x02 | 0x10 | 0x20)

    def bind_hotkeys(self, hwnd, toggle, hide):
        parsed = [parse_hotkey(toggle), parse_hotkey(hide)]
        if parsed[0] == parsed[1]:
            raise ValueError("열기와 숨기기에 서로 다른 단축키를 지정해주세요.")
        if self.registrations and [v[2] for v in self.registrations.values()] == parsed:
            return
        new = {}
        try:
            for action, (mods, vk) in zip(("toggle", "hide"), parsed):
                # Retain unchanged registrations while replacing the other shortcut.
                existing = next(((i, v) for i, v in self.registrations.items() if v[0] == hwnd and v[2] == (mods, vk)), None)
                if existing:
                    ident, value = existing
                    new[ident] = (hwnd, action, (mods, vk))
                    continue
                self.serial += 1
                if not self.user.RegisterHotKey(hwnd, self.serial, mods, vk):
                    raise ValueError("단축키를 다른 프로그램에서 사용 중입니다. 다른 조합을 지정해주세요.")
                new[self.serial] = (hwnd, action, (mods, vk))
        except ValueError:
            for ident in new.keys() - self.registrations.keys():
                self.user.UnregisterHotKey(hwnd, ident)
            raise
        for ident, value in self.registrations.items():
            if ident not in new:
                self.user.UnregisterHotKey(value[0], ident)
        self.registrations = new

    def release(self):
        for ident, value in self.registrations.items():
            self.user.UnregisterHotKey(value[0], ident)
        self.registrations.clear()
