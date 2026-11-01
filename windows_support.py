"""Small Win32 boundary for process lifetime, hotkeys, and text insertion."""

import ctypes
import os
import threading
import time
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
    user32.GetAsyncKeyState.argtypes = [ctypes.c_int]
    user32.GetAsyncKeyState.restype = ctypes.c_short
    user32.OpenClipboard.argtypes = [wintypes.HWND]
    user32.GetClipboardData.argtypes = [wintypes.UINT]
    user32.GetClipboardData.restype = wintypes.HANDLE
    user32.SetClipboardData.argtypes = [wintypes.UINT, wintypes.HANDLE]
    user32.SetClipboardData.restype = wintypes.HANDLE
    user32.EnumClipboardFormats.argtypes = [wintypes.UINT]
    user32.EnumClipboardFormats.restype = wintypes.UINT
    user32.GetClipboardSequenceNumber.restype = wintypes.DWORD
    user32.RegisterClipboardFormatW.argtypes = [wintypes.LPCWSTR]
    user32.RegisterClipboardFormatW.restype = wintypes.UINT
    kernel32.GlobalAlloc.argtypes = [wintypes.UINT, ctypes.c_size_t]
    kernel32.GlobalAlloc.restype = wintypes.HANDLE
    kernel32.GlobalLock.argtypes = [wintypes.HANDLE]
    kernel32.GlobalLock.restype = ctypes.c_void_p
    kernel32.GlobalSize.argtypes = [wintypes.HANDLE]
    kernel32.GlobalSize.restype = ctypes.c_size_t
    kernel32.GlobalFree.argtypes = [wintypes.HANDLE]
    kernel32.GlobalFree.restype = wintypes.HANDLE
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
    def __init__(self, assign_self=True):
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
        if assign_self and not kernel32.AssignProcessToJobObject(self.handle, kernel32.GetCurrentProcess()):
            self.close()
            raise ctypes.WinError(ctypes.get_last_error())

    def assign(self, pid):
        process = kernel32.OpenProcess(0x0101, False, pid)  # SET_QUOTA | TERMINATE
        if not process:
            raise ctypes.WinError(ctypes.get_last_error())
        try:
            if not kernel32.AssignProcessToJobObject(self.handle, process):
                raise ctypes.WinError(ctypes.get_last_error())
        finally:
            kernel32.CloseHandle(process)

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


def foreground_window():
    return user32.GetForegroundWindow() if os.name == "nt" else None


def _clipboard_open(window):
    for _ in range(20):
        if user32.OpenClipboard(window):
            return
        time.sleep(0.025)
    raise OSError("Notepad needs the clipboard for reliable insertion, but it is busy")


def _clipboard_snapshot():
    _clipboard_open(None)
    try:
        sequence = user32.GetClipboardSequenceNumber()
        saved = []
        format_id = 0
        while True:
            ctypes.set_last_error(0)
            format_id = user32.EnumClipboardFormats(format_id)
            if not format_id:
                if ctypes.get_last_error():
                    raise ctypes.WinError(ctypes.get_last_error())
                break
            if format_id in (2, 3, 9, 14):  # GDI handles are not movable memory.
                raise OSError("Clipboard contains a format WaveType cannot preserve; "
                              "paste the result from History instead")
            handle = user32.GetClipboardData(format_id)
            size = kernel32.GlobalSize(handle) if handle else 0
            pointer = kernel32.GlobalLock(handle) if size else None
            if not pointer:
                raise OSError("Clipboard contains a format WaveType cannot preserve; "
                              "paste the result from History instead")
            try:
                saved.append((format_id, ctypes.string_at(pointer, size)))
            finally:
                kernel32.GlobalUnlock(handle)
        if user32.GetClipboardSequenceNumber() != sequence:
            raise OSError("Clipboard changed during insertion; retry dictation")
        return saved, sequence
    finally:
        user32.CloseClipboard()


def _clipboard_set(window, formats):
    handles = []
    try:
        for format_id, value in formats:
            handle = kernel32.GlobalAlloc(0x0002, len(value))  # GMEM_MOVEABLE
            if not handle:
                raise ctypes.WinError(ctypes.get_last_error())
            handles.append((format_id, handle))
            pointer = kernel32.GlobalLock(handle)
            if not pointer:
                raise ctypes.WinError(ctypes.get_last_error())
            try:
                ctypes.memmove(pointer, value, len(value))
            finally:
                kernel32.GlobalUnlock(handle)
        _clipboard_open(window)
        try:
            if not user32.EmptyClipboard():
                raise ctypes.WinError(ctypes.get_last_error())
            for format_id, handle in list(handles):
                if not user32.SetClipboardData(format_id, handle):
                    raise ctypes.WinError(ctypes.get_last_error())
                handles.remove((format_id, handle))
        finally:
            user32.CloseClipboard()
    finally:
        for _, handle in handles:
            kernel32.GlobalFree(handle)


def _paste_notepad(text, expected_window):
    saved, previous_sequence = _clipboard_snapshot()  # Fail before changing unsupported formats.
    window = foreground_window()
    if expected_window is not None and window != expected_window:
        raise OSError("focused window changed during dictation")
    if user32.GetClipboardSequenceNumber() != previous_sequence:
        raise OSError("Clipboard changed during insertion; retry dictation")
    exclusion = user32.RegisterClipboardFormatW("ExcludeClipboardContentFromMonitorProcessing")
    if not exclusion:
        raise ctypes.WinError(ctypes.get_last_error())
    changed = False
    sequence = None
    try:
        changed = True
        _clipboard_set(window, [(13, text.encode("utf-16-le") + b"\0\0"),
                                (exclusion, b"\0\0\0\0")])
        sequence = user32.GetClipboardSequenceNumber()
        if expected_window is not None and foreground_window() != expected_window:
            raise OSError("focused window changed during dictation")
        if user32.GetClipboardSequenceNumber() != sequence:
            raise OSError("Clipboard changed during insertion; retry dictation")
        keys = (INPUT * 4)()
        for event in keys:
            event.type = 1
        keys[0].ki = KEYBDINPUT(0x11, 0, 0, 0, 0)
        keys[1].ki = KEYBDINPUT(0x56, 0, 0, 0, 0)
        keys[2].ki = KEYBDINPUT(0x56, 0, 0x0002, 0, 0)
        keys[3].ki = KEYBDINPUT(0x11, 0, 0x0002, 0, 0)
        sent = user32.SendInput(4, ctypes.byref(keys), ctypes.sizeof(INPUT))
        if sent != 4:
            raise OSError(f"SendInput sent {sent}/4 paste key events; elevated windows may block input")
        time.sleep(0.2)  # Let Notepad read the clipboard before restoring it.
    finally:
        if changed and (sequence is None or user32.GetClipboardSequenceNumber() == sequence):
            _clipboard_set(window, saved)


def insert_text(text, expected_window=None):
    if os.name != "nt":
        raise OSError("text insertion requires Windows")
    if expected_window is not None and foreground_window() != expected_window:
        raise OSError("focused window changed during dictation")
    # SendInput does not release physical modifiers; the dictation hotkey may
    # still have Ctrl or Win held when the recording is released.
    deadline = time.monotonic() + 0.5
    while any(user32.GetAsyncKeyState(key) & 0x8000 for key in (0x10, 0x11, 0x12, 0x5B, 0x5C)):
        if time.monotonic() >= deadline:
            raise OSError("release modifier keys before inserting text")
        time.sleep(0.01)
    if expected_window is not None and foreground_window() != expected_window:
        raise OSError("focused window changed during dictation")
    if not text:
        return
    if ((foreground_app() or {}).get("process") or "").casefold() == "notepad.exe":
        _paste_notepad(text, expected_window)
        return
    raw = text.encode("utf-16-le")
    items = (INPUT * len(raw))()
    for offset in range(0, len(raw), 2):
        code = int.from_bytes(raw[offset:offset + 2], "little")
        i = offset
        items[i].type = items[i + 1].type = 1
        items[i].ki = KEYBDINPUT(0, code, 0x0004, 0, 0)
        items[i + 1].ki = KEYBDINPUT(0, code, 0x0006, 0, 0)
    if expected_window is not None and foreground_window() != expected_window:
        raise OSError("focused window changed during dictation")
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


def consume_win_keyup(vk, scan):
    events = (INPUT * 3)()
    for event in events:
        event.type = 1
    # A function key can trigger a laptop's touchpad hotkey. VK_NONAME is
    # reserved and has no corresponding function-key action.
    events[0].ki = KEYBDINPUT(0xFC, 0, 0, 0, 0)
    events[1].ki = KEYBDINPUT(0xFC, 0, 0x0002, 0, 0)
    events[2].ki = KEYBDINPUT(vk, scan, 0x0003, 0, 0)  # Win up, extended
    return user32.SendInput(3, ctypes.byref(events), ctypes.sizeof(INPUT)) == 3


class Hotkey:
    """Low-level hook; supports modifier-only chords which RegisterHotKey cannot."""

    def __init__(self, callback, keys=(0x11, 0x5B)):
        self.callback = callback
        self.keys = set(keys)
        self.down = set()
        self.active = False
        self.assistant_enabled = False
        self.active_assistant = False
        self.interrupted = False
        self.consume_win_up = False
        self.pressed_at = 0.0
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

    def _on_key(self, vk, scan, flags, message):
        if flags & 0x10:  # Ignore our injected replacement key-up.
            return False
        key = {0xA0: 0x10, 0xA1: 0x10, 0xA2: 0x11, 0xA3: 0x11,
               0x5C: 0x5B}.get(vk, vk)
        if message in (0x100, 0x104):
            if self.consume_win_up and key not in self.keys and key != 0x10:
                self.consume_win_up = False
            self.down.add(key)
            if self.active and key == 0x10 and self.assistant_enabled and not self.active_assistant:
                self.active_assistant = True
                self.pressed_at = time.monotonic()
                self.callback("assistant_switch", 0)
            elif self.active and key not in self.keys and key != 0x10:
                self.active = False
                self.interrupted = True
                self.callback("assistant_abort" if self.active_assistant else "abort", 0)
            elif key in self.keys and not self.active and not self.interrupted and self.keys <= self.down:
                self.active = True
                self.active_assistant = self.assistant_enabled and 0x10 in self.down
                self.pressed_at = time.monotonic()
                self.callback("assistant_press" if self.active_assistant else "press", 0)
        elif message in (0x101, 0x105):
            if self.active and key in self.down and (key in self.keys or
                                                     key == 0x10 and self.active_assistant):
                self.consume_win_up = 0x5B in self.down
                self.down.discard(key)
                self.active = False
                self.interrupted = key == 0x10 and self.keys <= self.down
                self.callback("assistant_release" if self.active_assistant else "release",
                              (time.monotonic() - self.pressed_at) * 1000)
            else:
                self.down.discard(key)
                if key in self.keys and not self.keys <= self.down:
                    self.interrupted = False
            if key == 0x5B and self.consume_win_up:
                self.consume_win_up = False
                # The physical Win-up is held back until the neutral key has been sent.
                return consume_win_keyup(vk, scan)
        return False

    def _run(self):
        HOOK = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, ctypes.c_int, wintypes.WPARAM, wintypes.LPARAM)
        class KBDLLHOOKSTRUCT(ctypes.Structure):
            _fields_ = [("vkCode", wintypes.DWORD), ("scanCode", wintypes.DWORD),
                        ("flags", wintypes.DWORD), ("time", wintypes.DWORD),
                        ("dwExtraInfo", ctypes.c_size_t)]

        def hook(code, message, pointer):
            if code >= 0:
                event = ctypes.cast(pointer, ctypes.POINTER(KBDLLHOOKSTRUCT)).contents
                if self._on_key(event.vkCode, event.scanCode, event.flags, message):
                    return 1
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
