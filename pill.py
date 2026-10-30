"""Small no-focus Windows dictation pill."""

import argparse
import ctypes
import math
import os
import queue
import struct
import sys
import threading
import time
import tkinter as tk
import zlib
from ctypes import wintypes
from pathlib import Path

from client import EngineClient


TRANSPARENT = "#ff00ff"
PILL_SIZES = {"idle": (40, 5), "recording": (78, 29), "locked": (94, 29),
              "processing": (96, 28), "error": (128, 30)}
HOVER_GROWTH = (6, 2)
LOCK_ICON_SIZE = 20
WAVE_PEAKS = (7, 11, 15, 18, 19, 20, 19, 17, 14, 10, 6)
WAVE_PERIODS = (.75, .85, .68, .72, .82, .65, .78, .88, .70, .84, .76)
WAVE_PHASES = (.12, .28, .05, .35, .18, .42, .22, .08, .32, .15, .26)
user32 = ctypes.WinDLL("user32", use_last_error=True) if os.name == "nt" else None
if user32:
    user32.GetParent.argtypes = [wintypes.HWND]
    user32.GetParent.restype = wintypes.HWND
    user32.GetForegroundWindow.restype = wintypes.HWND
    user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]
    user32.MonitorFromWindow.restype = wintypes.HANDLE
    user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]
    user32.GetDpiForWindow.argtypes = [wintypes.HWND]
    user32.GetCursorPos.argtypes = [ctypes.POINTER(wintypes.POINT)]
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


def pill_size(state, error=False):
    return PILL_SIZES["error" if error else state]


def capsule_png(width, height, shade, background):
    """Rasterize a rounded capsule with subpixel edge coverage for Tk."""
    radius = height / 2
    pixels = bytearray()
    for y in range(height):
        row = bytearray()
        for x in range(width):
            dx = max(radius - (x + .5), 0, (x + .5) - (width - radius))
            distance = math.hypot(dx, y + .5 - radius) - radius
            coverage = max(0, min(1, .5 - distance))
            if coverage:
                # Tk's color key cannot blend partial alpha, so blend edge pixels here.
                row.extend(round(shade * coverage + channel * (1 - coverage))
                           for channel in background)
                row.append(255)
            else:
                row.extend((0, 0, 0, 0))
        pixels.append(0)
        pixels.extend(row)

    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))

    return (b"\x89PNG\r\n\x1a\n" +
            chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) +
            chunk(b"IDAT", zlib.compress(pixels)) + chunk(b"IEND", b""))


class Pill:
    def __init__(self, smart=False, tap_threshold_ms=250, on_event=None, on_window_message=None,
                 settings=None, engine_job=None):
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
        self.visual_size = None
        self.visual_target = None
        self.animation_start = 0.0
        self.animation_duration = .38
        self.hover = False
        self.in_tick = False
        self.hover_amount = 0.0
        self.hover_start = 0.0
        self.hover_from = 0.0
        self.lock_started = 0.0
        self.display_level = 0.0
        self.last_frame = time.monotonic()
        self.target = None
        self.ready = False
        self.closing = False
        self.toggle_pending = False
        self.on_event = on_event
        self.on_window_message = on_window_message
        self.engine_job = engine_job
        previous_focus = user32.GetForegroundWindow()
        self.root = tk.Tk()
        self.root.withdraw()
        self.root.overrideredirect(True)
        self.root.configure(bg=TRANSPARENT)
        self.root.wm_attributes("-transparentcolor", TRANSPARENT)
        self.canvas = tk.Canvas(self.root, bg=TRANSPARENT, highlightthickness=0, bd=0)
        self.canvas.pack(fill="both", expand=True)
        self.canvas.bind("<ButtonRelease-1>", lambda _: self._click())
        self.canvas.bind("<Button-3>", lambda _: self._send("cancel"))
        self.canvas.bind("<Enter>", lambda _: self._update_hover())
        self.canvas.bind("<Motion>", lambda _: self._update_hover())
        self.canvas.bind("<Leave>", lambda _: self.root.after(20, self._update_hover))
        assets = Path(__file__).with_name("assets")
        font_path = assets / "InterVariable.ttf"
        gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
        gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, wintypes.DWORD, ctypes.c_void_p]
        gdi32.GetPixel.argtypes = [wintypes.HDC, ctypes.c_int, ctypes.c_int]
        gdi32.GetPixel.restype = wintypes.COLORREF
        user32.GetDC.argtypes = [wintypes.HWND]
        user32.GetDC.restype = wintypes.HDC
        user32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
        self.gdi32 = gdi32
        self.status_font = (("Inter Variable Text", 8, "bold")
                            if font_path.is_file() and gdi32.AddFontResourceExW(str(font_path), 0x10, None)
                            else ("Segoe UI", 8, "bold"))
        self.lock_frames = [tk.PhotoImage(file=str(path))
                            for path in sorted((assets / "lock_frames").glob("*.png"))]
        self.capsule_images = {}
        self.root.update_idletasks()
        self.hwnd = user32.GetParent(self.root.winfo_id())
        if not self.hwnd:
            raise OSError("could not find pill window")
        self._install_window_style()
        self._place()
        self._draw()
        user32.ShowWindow(self.hwnd, 4)  # SW_SHOWNOACTIVATE
        if previous_focus and user32.GetForegroundWindow() == self.hwnd:
            user32.SetForegroundWindow(previous_focus)
        self.tick_after = self.root.after(33, self._tick)
        threading.Thread(target=self._connect, args=(smart, tap_threshold_ms, settings or {}), daemon=True).start()

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
            if self.on_window_message and self.on_window_message(message, wparam, lparam):
                return 0
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
        target = pill_size(self.state, bool(self.error))
        now = time.monotonic()
        if self.visual_size is None:
            self.visual_size = target
        if target != self.visual_target:
            self.animation_from = self.visual_size
            self.visual_target = target
            self.animation_start = now
        progress = min(1.0, (now - self.animation_start) / self.animation_duration)
        spring = 1 + 2.2 * (progress - 1) ** 3 + 1.2 * (progress - 1) ** 2
        self.visual_size = tuple(min(limit, start + (end - start) * spring)
                                 for start, end, limit in zip(
                                     self.animation_from, target,
                                     (max(size[0] for size in PILL_SIZES.values()),
                                      max(size[1] for size in PILL_SIZES.values()))))
        body_width, body_height = self.visual_size
        if self.state == "idle" and not self.error:
            body_width += HOVER_GROWTH[0] * self.hover_amount
            body_height += HOVER_GROWTH[1] * self.hover_amount
        width = round(max(size[0] for size in PILL_SIZES.values()) * scale)
        height = round(max(size[1] for size in PILL_SIZES.values()) * scale)
        body_width, body_height = round(body_width * scale), round(body_height * scale)
        body = ((width - body_width) // 2, height - body_height,
                body_width, body_height)
        margin = round(14 * scale)
        x, y = pill_position(area, screen, width, height, margin)
        geometry = (x, y, width, height)
        changed = body != getattr(self, "body", None) or geometry != getattr(self, "geometry", None)
        if geometry != getattr(self, "geometry", None):
            # Keep the canvas at one size across state changes. A shrinking
            # layered Tk window can retain a clipped frame of the old waveform.
            self.root.geometry(f"{width}x{height}")
            self.root.update_idletasks()
            if not user32.SetWindowPos(self.hwnd, -1, *geometry, 0x0010 | 0x0040):
                raise ctypes.WinError(ctypes.get_last_error())
            self.geometry = geometry
        self.size = width, height
        self.body = body
        return changed

    def _draw(self):
        left, top, width, height = self.body
        if not hasattr(self, "shapes"):
            self.shapes = {
                "capsule": self.canvas.create_image(0, 0, anchor="nw"),
                "text": self.canvas.create_text(0, 0, state="hidden", font=self.status_font),
                "lock_arc": self.canvas.create_arc(0, 0, 0, 0, start=0, extent=180,
                                                    outline="white", width=2, style="arc", state="hidden"),
                "lock_body": self.canvas.create_rectangle(0, 0, 0, 0, fill="white",
                                                           outline="white", state="hidden"),
                "lock_image": self.canvas.create_image(0, 0, state="hidden"),
            }
            self.bars = [self.canvas.create_line(0, 0, 0, 0, fill="white", capstyle="round",
                                                 state="hidden") for _ in WAVE_PEAKS]
        logical_width = self.visual_size[0]
        shade = (round(85 - 22 * max(0, min(1, (logical_width - 40) / 4)))
                 if logical_width <= 44 else
                 round(63 * max(0, min(1, (78 - logical_width) / 34))))
        if self.state == "idle" and not self.error:
            shade = max(0, shade - round(22 * self.hover_amount))
        dc = user32.GetDC(None)
        try:
            pixel = self.gdi32.GetPixel(dc, self.geometry[0] + left + width // 2,
                                        self.geometry[1] + top - 2)
        finally:
            user32.ReleaseDC(None, dc)
        background = ((pixel & 255, (pixel >> 8) & 255, (pixel >> 16) & 255)
                      if pixel != 0xFFFFFFFF else (32, 32, 32))
        key = width, height, shade, background
        if key not in self.capsule_images:
            if len(self.capsule_images) >= 128:
                self.capsule_images.clear()
            self.capsule_images[key] = tk.PhotoImage(data=capsule_png(*key), format="png")
        self.canvas.coords(self.shapes["capsule"], left, top)
        self.canvas.itemconfigure(self.shapes["capsule"], image=self.capsule_images[key])
        label = None
        label_color = "white"
        if self.error:
            label = ("Insert failed" if "Text insertion failed" in self.error else
                     "Mic error" if "microphone" in self.error.lower() else "Error")
            label_color = "#ff7777"
        elif self.state == "processing":
            label = "Working…" if self.ready else "Starting…"
        self.canvas.itemconfigure(self.shapes["text"], text=label or "", fill=label_color,
                                  state="normal" if label and width >= 75 else "hidden")
        self.canvas.coords(self.shapes["text"], left + width / 2, top + height / 2)
        locked = self.state == "locked" and not self.error
        for shape in ("lock_arc", "lock_body"):
            self.canvas.itemconfigure(self.shapes[shape],
                                      state="normal" if locked and not self.lock_frames else "hidden")
        self.canvas.itemconfigure(self.shapes["lock_image"],
                                  state="normal" if locked and self.lock_frames else "hidden")
        if locked and self.lock_frames:
            frame = min(len(self.lock_frames) - 1,
                        int((time.monotonic() - self.lock_started) * 30))
            self.canvas.itemconfigure(self.shapes["lock_image"], image=self.lock_frames[max(0, frame)])
            self.canvas.coords(self.shapes["lock_image"],
                               left + LOCK_ICON_SIZE * height / self.visual_size[1],
                               top + height / 2)
        elif locked:
            lock_left = left + height * 0.42
            self.canvas.coords(self.shapes["lock_arc"], lock_left, top + height * 0.25,
                               lock_left + height * 0.25, top + height * 0.65)
            self.canvas.coords(self.shapes["lock_body"], lock_left, top + height * 0.47,
                               lock_left + height * 0.25, top + height * 0.72)
        active = self.state in ("recording", "locked") and not self.error
        for bar in self.bars:
            self.canvas.itemconfigure(bar, state="normal" if active else "hidden")
        if active:
            activity = max(0.12, min(1, self.display_level * 4))
            now = time.monotonic()
            scale = height / self.visual_size[1]
            gap = min(4.5 * scale, max(1.5 * scale, (width - 14 * scale) / 10))
            for index, (bar, peak) in enumerate(zip(self.bars, WAVE_PEAKS)):
                bounce = (1 - math.cos(2 * math.pi * (now + WAVE_PHASES[index]) /
                                       WAVE_PERIODS[index])) / 2
                length = min((4 + (peak - 4) * activity * (0.35 + 0.65 * bounce)) * scale,
                             max(1, height - 4 * scale))
                x = left + width / 2 + (index - 5) * gap + (12 * scale if locked else 0)
                self.canvas.coords(bar, x, top + (height - length) / 2,
                                   x, top + (height + length) / 2)
                self.canvas.itemconfigure(bar, width=max(2, round(2 * scale)))

    def _send(self, name, **args):
        if self.ready and self.state != "processing":
            self.commands.put((name, args, None))

    def _set_hover(self, hovered):
        if hovered != self.hover:
            self.hover = hovered
            self.hover_from = self.hover_amount
            self.hover_start = time.monotonic()
            if not self.in_tick:
                self.root.after_cancel(self.tick_after)
                self.tick_after = self.root.after(16, self._tick)

    def _cursor_position(self):
        point = wintypes.POINT()
        rect = wintypes.RECT()
        user32.GetCursorPos(ctypes.byref(point))
        user32.GetWindowRect(self.hwnd, ctypes.byref(rect))
        return point.x - rect.left, point.y - rect.top

    def _update_hover(self):
        if self.state != "idle" or self.error:
            self._set_hover(False)
            return
        x, y = self._cursor_position()
        scale = self.size[0] / max(size[0] for size in PILL_SIZES.values())
        width, height = round(40 * scale), round(5 * scale)
        left, top = (self.size[0] - width) // 2, self.size[1] - height
        margin = round((14 if self.hover else 7) * scale)
        self._set_hover(left - margin <= x <= left + width + margin and
                        top - margin <= y <= top + height + margin)

    def _click(self):
        if self.toggle_pending or not self.ready or self.state == "processing":
            return
        self.toggle_pending = True
        self._send("toggle", insert=True)

    def request(self, name, callback=None, **args):
        if self.ready:
            self.commands.put((name, args, callback))
        elif callback:
            self.messages.put({"event": "response", "callback": callback,
                               "error": "Engine is still starting"})

    def _connect(self, smart, threshold, settings):
        commands = events = None
        try:
            commands = EngineClient(start=True, job=self.engine_job)
            settings = settings.copy()
            for _attempt in range(3):
                try:
                    commands.command("settings", mode="hybrid", smart=smart,
                                     tap_threshold_ms=threshold, hotkey=True, **settings)
                    break
                except RuntimeError as exc:
                    if smart and "Qwen model unavailable" in str(exc):
                        smart = False
                    elif settings.get("microphone") is not None and "unknown microphone" in str(exc):
                        settings["microphone"] = None
                        self.messages.put({"event": "error", "message":
                                           "Saved microphone unavailable; using the default input."})
                        continue
                    else:
                        raise
                    self.messages.put({"event": "error", "message": str(exc)})
            events = EngineClient()
            events.command("subscribe")
            events.sock.settimeout(None)
            self.messages.put({"event": "state", "value": commands.command("status")["state"]})
            self.ready = True
            self.command_worker = threading.Thread(target=self._command_loop, args=(commands,), daemon=True)
            self.command_worker.start()
            for event in events.events():
                self.messages.put(event)
            if self.ready and not self.closing:
                self.messages.put({"event": "error", "message": "Engine connection lost"})
        except Exception as exc:
            if not self.closing:
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
                name, args, callback = self.commands.get()
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
                    result = client.command(name, **args)
                    if callback:
                        self.messages.put({"event": "response", "callback": callback,
                                           "result": result})
                except Exception as exc:
                    if callback:
                        self.messages.put({"event": "response", "callback": callback,
                                           "error": str(exc)})
                    else:
                        self.messages.put({"event": "error", "message": str(exc)})
        finally:
            client.close()

    def _tick(self):
        self.in_tick = True
        if self.state == "idle" or self.hover:
            self._update_hover()
        redraw = False
        while True:
            try:
                event = self.messages.get_nowait()
            except queue.Empty:
                break
            if event["event"] == "state":
                self.toggle_pending = False
                if event["value"] == "locked" and self.state != "locked":
                    self.lock_started = time.monotonic()
                self.state = event["value"]
                if self.state in ("recording", "locked") and self.target is None:
                    self.target = user32.GetForegroundWindow()
                elif self.state == "idle":
                    self.target = None
                    self.level = 0.0
                redraw = True
            elif event["event"] == "level":
                self.level = event["value"]
                redraw = self.state in ("recording", "locked")
            elif event["event"] == "error":
                self.toggle_pending = False
                self.error = event["message"]
                if not self.closing:
                    print(self.error, file=sys.stderr)
                self.error_serial += 1
                if self.ready:
                    self.root.after(3500, self._clear_error, self.error_serial)
                redraw = True
            elif event["event"] == "response":
                redraw = not self._dispatch_ui_callback(
                    event["callback"], event.get("result"), event.get("error")) or redraw
            if self.on_event and event["event"] != "response":
                redraw = not self._dispatch_ui_callback(self.on_event, event) or redraw
        now = time.monotonic()
        hover_progress = min(1.0, (now - self.hover_start) / .2)
        hover_target = 1.0 if self.hover else 0.0
        hover_amount = self.hover_from + (hover_target - self.hover_from) * (
            1 - (1 - hover_progress) ** 3)
        redraw = redraw or abs(hover_amount - self.hover_amount) > .001
        self.hover_amount = hover_amount
        changed = self._place()
        elapsed = min(.25, now - self.last_frame)
        self.last_frame = now
        level = self.level if self.state in ("recording", "locked") else 0.0
        response = .06 if level > self.display_level else .14
        self.display_level += (level - self.display_level) * (1 - math.exp(-elapsed / response))
        redraw = redraw or self.state in ("recording", "locked")
        if redraw or changed or not hasattr(self, "positioned"):
            self._draw()
        self.positioned = True
        animating = now - self.animation_start < self.animation_duration
        hover_animating = hover_progress < 1 and self.hover_from != hover_target
        self.in_tick = False
        self.tick_after = self.root.after(
            16 if self.state in ("recording", "locked") or animating or hover_animating else
            33 if self.state == "processing" or self.hover else 80, self._tick)

    def _dispatch_ui_callback(self, callback, *args):
        try:
            callback(*args)
            return True
        except Exception:
            self.root.report_callback_exception(*sys.exc_info())
            self.error = "UI update failed; see ui.log"
            self.error_serial += 1
            self.root.after(3500, self._clear_error, self.error_serial)
            return False

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
                self.commands.put((None, {}, None))
                self.command_worker.join(timeout=4)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--smart", action="store_true")
    parser.add_argument("--tap-threshold-ms", type=int, default=250)
    options = parser.parse_args()
    Pill(options.smart, options.tap_threshold_ms).run()
