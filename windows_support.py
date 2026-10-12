"""Small Win32 boundary for process lifetime, hotkeys, and text insertion."""

import ctypes
import os
import threading
from ctypes import wintypes


if os.name == "nt":
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    kernel32.CreateJobObjectW.restype = wintypes.HANDLE
    kernel32.GetCurrentProcess.restype = wintypes.HANDLE
    kernel32.SetInformationJobObject.argtypes = [wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
    kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    user32.SendInput.argtypes = [wintypes.UINT, ctypes.c_void_p, ctypes.c_int]
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.GetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
    user32.GetWindowThreadProcessId.argtypes = [wintypes.HWND, ctypes.POINTER(wintypes.DWORD)]
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                                   ctypes.POINTER(wintypes.DWORD)]
    user32.CallNextHookEx.argtypes = [wintypes.HANDLE, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM]
    user32.CallNextHookEx.restype = ctypes.c_ssize_t


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64), ("PerJobUserTimeLimit", ctypes.c_int64),
                ("LimitFlags", wintypes.DWORD), ("MinimumWorkingSetSize", ctypes.c_size_t),
                ("MaximumWorkingSetSize", ctypes.c_size_t), ("ActiveProcessLimit", wintypes.DWORD),
                ("Affinity", ctypes.c_size_t), ("PriorityClass", wintypes.DWORD),
                ("SchedulingClass", wintypes.DWORD)]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [(name, ctypes.c_uint64) for name in (
        "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
        "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
                ("IoInfo", IO_COUNTERS), ("ProcessMemoryLimit", ctypes.c_size_t),
                ("JobMemoryLimit", ctypes.c_size_t), ("PeakProcessMemoryUsed", ctypes.c_size_t),
                ("PeakJobMemoryUsed", ctypes.c_size_t)]


class ChildJob:
    def __init__(self):
        if os.name != "nt":
            self.handle = None
            return
        self.handle = kernel32.CreateJobObjectW(None, None)
        if not self.handle:
            raise ctypes.WinError(ctypes.get_last_error())
        info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
        info.BasicLimitInformation.LimitFlags = 0x2000  # KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(self.handle, 9, ctypes.byref(info), ctypes.sizeof(info)):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())
        if not kernel32.AssignProcessToJobObject(self.handle, kernel32.GetCurrentProcess()):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def close(self):
        if self.handle:
            kernel32.CloseHandle(self.handle)
            self.handle = None


class KEYBDINPUT(ctypes.Structure):
    _fields_ = [("wVk", wintypes.WORD), ("wScan", wintypes.WORD),
                ("dwFlags", wintypes.DWORD), ("time", wintypes.DWORD),
                ("dwExtraInfo", ctypes.c_size_t)]


class MOUSEINPUT(ctypes.Structure):
    _fields_ = [("dx", wintypes.LONG), ("dy", wintypes.LONG),
                ("mouseData", wintypes.DWORD), ("dwFlags", wintypes.DWORD),
                ("time", wintypes.DWORD), ("dwExtraInfo", ctypes.c_size_t)]


class INPUT(ctypes.Structure):
    class _UNION(ctypes.Union):
        _fields_ = [("ki", KEYBDINPUT), ("mi", MOUSEINPUT)]
    _anonymous_ = ("data",)
    _fields_ = [("type", wintypes.DWORD), ("data", _UNION)]


def insert_text(text):
    if os.name != "nt":
        raise OSError("text insertion requires Windows")
    raw = text.encode("utf-16-le")
    items = (INPUT * len(raw))()
    for offset in range(0, len(raw), 2):
        code = int.from_bytes(raw[offset:offset + 2], "little")
        i = offset
        items[i].type = items[i + 1].type = 1
        items[i].ki = KEYBDINPUT(0, code, 0x0004, 0, 0)
        items[i + 1].ki = KEYBDINPUT(0, code, 0x0006, 0, 0)
    if items:
        sent = user32.SendInput(len(items), ctypes.byref(items), ctypes.sizeof(INPUT))
        if sent != len(items):
            raise OSError(f"SendInput sent {sent}/{len(items)} key events; elevated windows may block input")


def foreground_app():
    if os.name != "nt":
        return None
    hwnd = user32.GetForegroundWindow()
    title = ctypes.create_unicode_buffer(256)
    user32.GetWindowTextW(hwnd, title, len(title))
    pid = wintypes.DWORD()
    user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
    process = kernel32.OpenProcess(0x1000, False, pid.value)
    executable = None
    if process:
        try:
            path = ctypes.create_unicode_buffer(1024)
            size = wintypes.DWORD(len(path))
            if kernel32.QueryFullProcessImageNameW(process, 0, path, ctypes.byref(size)):
                executable = os.path.basename(path.value)
        finally:
            kernel32.CloseHandle(process)
    return {"process": executable, "title": title.value, "pid": pid.value}


class Hotkey:
    """Low-level hook; supports modifier-only chords which RegisterHotKey cannot."""

    def __init__(self, callback, keys=(0x11, 0x5B)):
        self.callback = callback
        self.keys = set(keys)
        self.down = set()
        self.active = False
        self.ready = threading.Event()
        self.error = None
        self.thread = threading.Thread(target=self._run, daemon=True)

    def start(self):
        if os.name != "nt":
            raise OSError("hotkeys require Windows")
        self.thread.start()
        if not self.ready.wait(3):
            raise OSError("hotkey hook did not start")
        if self.error:
            raise self.error

    def _run(self):
        HOOK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        def hook(code, message, pointer):
            if code >= 0:
                event = ctypes.cast(pointer, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if not event.flags & 0x10:  # injected input
                    key = {0xA2: 0x11, 0xA3: 0x11, 0x5C: 0x5B}.get(event.vkCode, event.vkCode)
                    if message in (0x100, 0x104):
                        self.down.add(key)
                        if not self.active and self.keys <= self.down:
                            self.active = True
                            self.callback("press")
                    elif message in (0x101, 0x105):
                        self.down.discard(key)
                        if self.active and not self.keys <= self.down:
                            self.active = False
                            self.callback("release")
            return user32.CallNextHookEx(None, code, message, pointer)

        self._callback = HOOK(hook)
        user32.SetWindowsHookExW.restype = wintypes.HANDLE
        user32.SetWindowsHookExW.argtypes = [ctypes.c_int, HOOK, wintypes.HANDLE, wintypes.DWORD]
        handle = user32.SetWindowsHookExW(13, self._callback, None, 0)
        if not handle:
            self.error = ctypes.WinError(ctypes.get_last_error())
            self.ready.set()
            return
        self.ready.set()
        try:
            message = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(message), None, 0, 0) > 0:
                user32.TranslateMessage(ctypes.byref(message))
                user32.DispatchMessageW(ctypes.byref(message))
        finally:
            user32.UnhookWindowsHookEx(handle)
