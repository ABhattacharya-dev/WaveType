"""Small no-focus Windows dictation pill."""

import argparse
import ctypes
import os
import queue
import sys
import threading
import tkinter as tk
from ctypes import wintypes

from client import EngineClient


TRANSPARENT = "#ff00ff"
user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
if user32:
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.SetWindowPos.argtypes = [wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                   ctypes.c_int, ctypes.c_int, wintypes.UINT]
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]


class MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT),
                ("rcWork", wintypes.RECT), ("dwFlags", wintypes.DWORD)]


def pill_position(area, screen, width, height, margin):
    x, y = (area.left + area.right - width) // 2, area.bottom - height - margin
    if area.top > screen.top:
        y = area.top + margin
    elif area.left > screen.left:
        x, y = area.left + margin, (area.top + area.bottom - height) // 2
    elif area.right < screen.right:
        x, y = area.right - width - margin, (area.top + area.bottom - height) // 2
    return x, y


class Pill:
    def __init__(self, smart=False, tap_threshold_ms=250):
        if os.name != "nt":
            raise OSError("pill requires Windows")
        try:
            if not user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4)):
                user32.SetProcessDPIAware()
        except AttributeError:
            user32.SetProcessDPIAware()
        self.messages = queue.Queue()
        self.commands = queue.Queue()
        self.state = "processing"
        self.level = 0.0
        self.error = None
        self.error_serial = 0
        self.target = None
        self.ready = False
        previous_focus = user32.GetForegroundWindow()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack()
        self.canvas.bind("<Button-1>", lambda _: self._send("toggle", insert=True))
        self.canvas.bind("<Button-3>", lambda _: self._send("cancel"))
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id())
        if not self.hwnd:
            raise OSError("could not find pill window")
        self._install_window_style()
        self._draw()
        self._place()
        user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
        if previous_focus and user32.GetForegroundWindow() == self.hwnd:
            user32.SetForegroundWindow(previous_focus)
        self.root.after(33, self._tick)
        threading.Thread(target=self._connect, args=(smart, tap_threshold_ms), daemon=True).start()

    def _install_window_style(self):
        get_style = user32.GetWindowLongPtrW
        set_style = user32.SetWindowLongPtrW
        get_style.argtypes = [wintypes.HWND, ctypes.c_int]
        get_style.restype = ctypes.c_ssize_t
        set_style.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t]
        set_style.restype = ctypes.c_ssize_t
        style = get_style(self.hwnd, -20)
        set_style(self.hwnd, -20, style | 0x08000000 | 0x00000080 | 0x00080000)
        PROC = ctypes.WINFUNCTYPE(ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT,
                                 wintypes.WPARAM, wintypes.LPARAM)
        user32.CallWindowProcW.argtypes = [ctypes.c_void_p, wintypes.HWND, wintypes.UINT,
                                           wintypes.WPARAM, wintypes.LPARAM]
        user32.CallWindowProcW.restype = ctypes.c_ssize_t

        def window_proc(hwnd, message, wparam, lparam):
            if message == 0x21:  # WM_MOUSEACTIVATE
                return 3  # MA_NOACTIVATE: keep the click
            return user32.CallWindowProcW(self.previous_procs[hwnd], hwnd, message, wparam, lparam)

        self.window_proc = PROC(window_proc)
        self.previous_procs = {}
        for hwnd in (self.hwnd, self.root.winfo_id(), self.canvas.winfo_id()):
            previous = set_style(hwnd, -4, ctypes.cast(self.window_proc, ctypes.c_void_p).value)
            if not previous:
                raise ctypes.WinError(ctypes.get_last_error())
            self.previous_procs[hwnd] = previous

    def _place(self):
        hwnd = self.target or user32.GetForegroundWindow() or self.hwnd
        monitor = user32.MonitorFromWindow(hwnd, 2)
        info = MONITORINFO()
        info.cbSize = ctypes.sizeof(info)
        if not monitor or not user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
            raise ctypes.WinError(ctypes.get_last_error())
        area = info.rcWork
        screen = info.rcMonitor
        dpi = user32.GetDpiForWindow(hwnd) or 96
        scale = dpi / 96
        width, height = (62, 24) if self.state == "idle" and not self.error else (184, 48)
        width, height = round(width * scale), round(height * scale)
        margin = round(12 * scale)
        x, y = pill_position(area, screen, width, height, margin)
        if getattr(self, "size", None) != (width, height):
            self.canvas.configure(width=width, height=height)
        geometry = (x, y, width, height)
        if geometry != getattr(self, "geometry", None):
            user32.SetWindowPos(self.hwnd, -1, *geometry, 0x0010 | 0x0040)
            self.geometry = geometry
        self.size = width, height

    def _draw(self):
        if not hasattr(self, "size"):
            self.size = 62, 24
        width, height = self.size
        self.canvas.delete("all")
        radius = height / 2
        self.canvas.create_oval(0, 0, height, height, fill="black", outline="black")
        self.canvas.create_oval(width - height, 0, width, height, fill="black", outline="black")
        self.canvas.create_rectangle(radius, 0, width - radius, height, fill="black", outline="black")
        if self.error:
            label = "Insertion failed" if "Text insertion failed" in self.error else self.error[:20]
            self.canvas.create_text(width / 2, height / 2, text=label,
                                    fill="#ff7777", font=("Segoe UI", max(9, height // 4)))
        elif self.state == "idle":
            self.canvas.create_oval(width / 2 - 2, height / 2 - 2,
                                    width / 2 + 2, height / 2 + 2, fill="white", outline="")
        elif self.state == "processing":
            self.canvas.create_text(width / 2, height / 2,
                                    text="Processing…" if self.ready else "Starting…", fill="white",
                                    font=("Segoe UI", max(9, height // 4)))
        else:
            bars = 11
            gap = width / (bars + 5)
            for index in range(bars):
                variation = abs((index * 7) % 11 - 5) / 5
                amplitude = max(0.1, min(1, self.level * 4 + 0.12))
                length = max(5, (height - 15) * amplitude * (0.4 + 0.6 * variation))
                x = width / 2 + (index - (bars - 1) / 2) * gap
                self.canvas.create_line(x, (height - length) / 2, x, (height + length) / 2,
                                        fill="white", width=max(2, round(height / 16)), capstyle="round")

    def _send(self, name, **args):
        if self.ready and self.state != "processing":
            self.commands.put((name, args))

    def _connect(self, smart, threshold):
        commands = events = None
        try:
            commands = EngineClient(start=True)
            commands.command("settings", mode="hybrid", smart=smart,
                             tap_threshold_ms=threshold, hotkey=True)
            events = EngineClient()
            events.command("subscribe")
            self.messages.put({"event": "state", "value": commands.command("status")["state"]})
            self.ready = True
            self.command_worker = threading.Thread(target=self._command_loop, args=(commands,), daemon=True)
            self.command_worker.start()
            for event in events.events():
                self.messages.put(event)
            if self.ready:
                self.messages.put({"event": "error", "message": "Engine connection lost"})
        except Exception as exc:
            self.messages.put({"event": "error", "message": str(exc)})
        finally:
            self.ready = False
            if commands and not hasattr(self, "command_worker"):
                commands.close()
            if events:
                events.close()

    def _command_loop(self, client):
        try:
            while True:
                name, args = self.commands.get()
                if name is None:
                    try:
                        state = client.command("status")["state"]
                        if state in ("recording", "locked"):
                            client.command("cancel")
                        client.command("settings", hotkey=False)
                    except Exception:
                        pass
                    break
                try:
                    client.command(name, **args)
                except Exception as exc:
                    self.messages.put({"event": "error", "message": str(exc)})
        finally:
            client.close()

    def _tick(self):
        redraw = False
        while True:
            try:
                event = self.messages.get_nowait()
            except queue.Empty:
                break
            if event["event"] == "state":
                self.state = event["value"]
                if self.state in ("recording", "locked") and self.target is None:
                    self.target = user32.GetForegroundWindow()
                elif self.state == "idle":
                    self.target = None
                redraw = True
            elif event["event"] == "level":
                self.level = event["value"]
                redraw = self.state in ("recording", "locked")
            elif event["event"] == "error":
                self.error = event["message"]
                print(self.error, file=sys.stderr)
                self.error_serial += 1
                if self.ready:
                    self.root.after(3500, self._clear_error, self.error_serial)
                redraw = True
        if redraw or not hasattr(self, "positioned"):
            self._place()
            self._draw()
        else:
            self._place()
        self.positioned = True
        self.root.after(33 if self.state in ("recording", "locked") else 250, self._tick)

    def _clear_error(self, serial):
        if serial != self.error_serial:
            return
        self.error = None
        self._place()
        self._draw()

    def run(self):
        try:
            self.root.mainloop()
        finally:
            if getattr(self, "command_worker", None):
                self.commands.put((None, {}))
                self.command_worker.join(timeout=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smart", action="store_true")
    parser.add_argument("--tap-threshold-ms", type=int, default=250)
    options = parser.parse_args()
    Pill(options.smart, options.tap_threshold_ms).run()
