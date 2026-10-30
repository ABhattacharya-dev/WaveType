"""Light Windows desktop client for the local dictation engine."""

import ctypes
import faulthandler
import json
import os
import queue
import subprocess
import sys
import time
import tkinter as tk
from tkinter import ttk, messagebox
import webbrowser
import winreg
from ctypes import wintypes
from datetime import date, time as clock_time, timedelta
from pathlib import Path

from ipc_protocol import APP_DIR
from app_update import MANUAL_COOLDOWN, UpdateManager, installed_version
from pill import Pill
from windows_support import ChildJob


PREFERENCES = APP_DIR / "ui.json"


def model_controls(value):
    state = value.get("state", "missing")
    if state in ("deleting", "pausing", "canceling"):
        return ()
    if state == "verifying":
        return ("pause", "cancel") if value.get("operation") in ("download", "repair") else ()
    if state == "downloading":
        return ("pause", "cancel")
    if state == "paused":
        return ("resume", "cancel")
    if state == "ready" or value.get("installed") or value.get("operation") == "delete":
        return ("verify", "delete")
    if value.get("partial"):
        return ("resume", "cancel")
    return ("download",)


ASSETS = Path(__file__).resolve().parent / "assets"
RELEASES = "https://github.com/ABhattacharya-dev/stt-core-structure/releases"
LIGHT = {"bg": "#FFFFFF", "side": "#F4F4F2", "card": "#FFFFFF", "text": "#18181B",
         "muted": "#71717A", "soft": "#A1A1AA", "line": "#E7E7E4", "accent": "#18181B",
         "button": "#ECEAE3", "link": "#7C3AED", "subtle": "#FAF8F5", "value": "#F4F4F2",
         "banner": "#FCFBF3", "banner_line": "#EFEBD9", "danger": "#EF4444",
         "focus": "#F3E8FF"}
DARK = {"bg": "#1F1F1E", "side": "#292927", "card": "#32322F", "text": "#F4F0E9",
        "muted": "#B9B3A9", "soft": "#8D887F", "line": "#454541", "accent": "#F4F0E9",
        "button": "#3C3C38", "link": "#AD86FF", "subtle": "#292927", "value": "#3C3C38",
        "banner": "#302D24", "banner_line": "#484236", "danger": "#FF7777",
        "focus": "#46345B"}

FONT_FILES = {"sans": ("Figtree", "Figtree.ttf"),
              "serif": ("EB Garamond", "EBGaramond.ttf"),
              "mono": ("JetBrains Mono", "JetBrainsMono.ttf")}


def system_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def history_heading(value, today=None):
    today = today or date.today()
    try:
        day = date.fromisoformat(value)
    except (TypeError, ValueError):
        return value or "Unknown date"
    if day == today:
        return "Today"
    if day == today - timedelta(days=1):
        return "Yesterday"
    return f"{day.day}/{day.month}/{day.year % 100:02d}"


def history_time(value):
    try:
        clock = clock_time.fromisoformat(value)
        return f"{clock.hour % 12 or 12}:{clock.minute:02d}"
    except (TypeError, ValueError):
        return value or ""


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else sys.executable}" "{Path(__file__).resolve()}"'


def login_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            for name in ("WaveType", "STT Core"):
                try:
                    if winreg.QueryValueEx(key, name)[0] == startup_command():
                        return True
                except FileNotFoundError:
                    pass
            return False
    except OSError:
        return False


def set_login(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                       winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, "WaveType", 0, winreg.REG_SZ, startup_command())
        for name in (("STT Core",) if enabled else ("WaveType", "STT Core")):
            try:
                winreg.DeleteValue(key, name)
            except FileNotFoundError:
                pass


class NOTIFYICONDATAW(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("hWnd", wintypes.HWND),
                ("uID", wintypes.UINT), ("uFlags", wintypes.UINT),
                ("uCallbackMessage", wintypes.UINT), ("hIcon", wintypes.HICON),
                ("szTip", wintypes.WCHAR * 128)]


class TrayIcon:
    MESSAGE = 0x8000 + 17

    def __init__(self, hwnd, callback):
        self.callback = callback
        self.data = NOTIFYICONDATAW()
        self.data.cbSize = ctypes.sizeof(self.data)
        self.data.hWnd = hwnd
        self.data.uID = 1
        self.data.uFlags = 1 | 2 | 4  # message, icon, tooltip
        self.data.uCallbackMessage = self.MESSAGE
        user32 = ctypes.windll.user32
        user32.LoadImageW.argtypes = [wintypes.HINSTANCE, wintypes.LPCWSTR, wintypes.UINT,
                                     ctypes.c_int, ctypes.c_int, wintypes.UINT]
        user32.LoadImageW.restype = wintypes.HANDLE
        self.data.hIcon = user32.LoadImageW(None, str(ASSETS / "WaveType.ico"), 1, 0, 0, 0x10 | 0x40)
        if not self.data.hIcon:
            raise ctypes.WinError()
        self.data.szTip = "WaveType dictation"
        if not ctypes.windll.shell32.Shell_NotifyIconW(0, ctypes.byref(self.data)):
            self.close()
            raise ctypes.WinError()

    def message(self, message, _wparam, lparam):
        if message != self.MESSAGE:
            return False
        if lparam & 0xFFFF in (0x202, 0x203, 0x205):
            self.callback(lparam & 0xFFFF)
        return True

    def close(self):
        ctypes.windll.shell32.Shell_NotifyIconW(2, ctypes.byref(self.data))
        if self.data.hIcon:
            ctypes.windll.user32.DestroyIcon.argtypes = [wintypes.HICON]
            ctypes.windll.user32.DestroyIcon(self.data.hIcon)
            self.data.hIcon = None


class DesktopApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.preferences = json.loads(PREFERENCES.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.preferences = {}
        self.first_run = not PREFERENCES.exists()
        self.updates = UpdateManager(APP_DIR, installed_version(sys.executable))
        self.update_state = {"state": "idle"}
        self.update_manual = False
        self.prompted_version = None
        self.update_error_on_start = self.read_update_result()
        self.theme = self.preferences.get("theme", "Light")
        self.colors = DARK if self.theme == "Dark" or self.theme == "System" and system_dark() else LIGHT
        self.page = "Setup" if self.first_run else "History"
        self.history = []
        self.dictionary = {"snippets": {}, "vocabulary": {}}
        self.devices = []
        self.model = {}
        self.setup_error = ""
        self.engine_job = ChildJob(assign_self=False)
        self.pill = Pill(smart=bool(self.preferences.get("smart", False)),
                         tap_threshold_ms=int(self.preferences.get("tap_threshold_ms", 250)),
                         settings={"tier": self.preferences.get("tier", "auto"),
                                   "language": "auto", "microphone": self.preferences.get("microphone")},
                         on_event=self.on_engine_event, on_window_message=self.on_window_message,
                         engine_job=self.engine_job)
        self.root = self.pill.root
        self.ui_fonts = {"sans": "Segoe UI", "serif": "Georgia", "mono": "Consolas"}
        for style, (family, filename) in FONT_FILES.items():
            path = Path(__file__).resolve().parent / "assets" / filename
            if path.is_file() and ctypes.windll.gdi32.AddFontResourceExW(str(path), 0x10, None):
                self.ui_fonts[style] = family
        self.main = tk.Toplevel(self.root)
        self.main.title("WaveType")
        self.main.iconbitmap(str(ASSETS / "WaveType.ico"))
        work = wintypes.RECT()
        if ctypes.windll.user32.SystemParametersInfoW(0x30, 0, ctypes.byref(work), 0):
            width = min(1100, work.right - work.left - 40)
            height = min(720, work.bottom - work.top - 40)
            self.main.geometry(f"{width}x{height}+{work.left + (work.right - work.left - width) // 2}"
                               f"+{work.top + (work.bottom - work.top - height) // 2}")
        else:
            self.main.geometry("1100x720")
        self.main.resizable(False, False)
        self.main.configure(bg=self.colors["bg"])
        self.main.protocol("WM_DELETE_WINDOW", self.hide)
        self.main.bind("<Escape>", lambda _event: self.hide())
        self.main.withdraw()
        self.main.update_idletasks()
        self.style_titlebar()
        self.tray_events = queue.SimpleQueue()
        self.tray = TrayIcon(self.pill.hwnd, self.tray_events.put)
        self.menu = tk.Menu(self.root, tearoff=False)
        self.tray_smart_var = tk.BooleanVar(value=bool(self.preferences.get("smart", False)))
        self.smart_pending = False
        self.menu.add_command(label="WaveType", command=self.show)
        self.menu.add_checkbutton(label="Smart cleanup", variable=self.tray_smart_var,
                                  command=self.toggle_tray_smart)
        self.menu.add_separator()
        self.menu.add_command(label="Exit", command=self.quit)
        self.menu.bind("<ButtonRelease-3>", lambda _event: "break")
        self.render()
        if self.first_run:
            self.show()
        self.root.after(100, self.drain_tray)
        self.root.after(500, self.watch_ready)
        self.root.after(250, self.poll_updates)
        self.root.after(5000, self.auto_check_update)

    def on_window_message(self, message, wparam, lparam):
        return getattr(self, "tray", None) is not None and self.tray.message(message, wparam, lparam)

    def on_tray(self, button):
        if button in (0x202, 0x203):
            self.show()
        elif button == 0x205:
            self.root.after(120, self.popup_menu)

    def drain_tray(self):
        while not self.tray_events.empty():
            self.on_tray(self.tray_events.get_nowait())
        if not getattr(self, "quitting", False):
            self.root.after(100, self.drain_tray)

    def popup_menu(self):
        x, y = self.root.winfo_pointerxy()
        self.menu.entryconfigure("Smart cleanup", state="normal" if self.pill.ready and
                                 self.pill.state == "idle" and not self.smart_pending else "disabled")
        try:
            self.menu.tk_popup(x, y)
        finally:
            self.menu.grab_release()

    def toggle_tray_smart(self):
        enabled = self.tray_smart_var.get()
        if self.smart_pending or not self.pill.ready or self.pill.state != "idle":
            self.tray_smart_var.set(bool(self.preferences.get("smart", False)))
            return
        self.smart_pending = True
        self.pill.request("settings", lambda result, error: self.after_tray_smart(result, error),
                          smart=enabled)

    def after_tray_smart(self, result, error):
        self.smart_pending = False
        if error:
            self.tray_smart_var.set(bool(self.preferences.get("smart", False)))
            self.pill.messages.put({"event": "error", "message": error})
            return
        enabled = bool(result["smart"])
        self.tray_smart_var.set(enabled)
        self.preferences["smart"] = enabled
        self.save_preferences()
        if self.page == "Settings":
            self.smart_var.set(enabled)
            self.settings_initial["smart"] = enabled
            self.update_apply_visibility()

    def show(self):
        self.style_titlebar()
        self.main.deiconify()
        self.main.update_idletasks()
        self.main.lift()
        self.main.focus_force()
        self.refresh_page()

    def style_titlebar(self):
        user32 = ctypes.windll.user32
        user32.GetAncestor.argtypes = (wintypes.HWND, wintypes.UINT)
        user32.GetAncestor.restype = wintypes.HWND
        hwnd = user32.GetAncestor(self.main.winfo_id(), 2)
        user32.GetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int)
        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.SetWindowLongPtrW.argtypes = (wintypes.HWND, ctypes.c_int, ctypes.c_ssize_t)
        user32.SetWindowLongPtrW.restype = ctypes.c_ssize_t
        # Only the main window gets a taskbar entry; withdrawing it leaves the tray active.
        user32.SetWindowLongPtrW(hwnd, -8, 0)
        extended = (user32.GetWindowLongPtrW(hwnd, -20) | 0x40000) & ~0x80
        user32.SetWindowLongPtrW(hwnd, -20, extended)
        style = user32.GetWindowLongPtrW(hwnd, -16)
        user32.SetWindowLongPtrW(hwnd, -16, (style | 0x20000 | 0x80000) & ~(0x10000 | 0x40000))
        user32.SetWindowPos.argtypes = (wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_int, wintypes.UINT)
        user32.SetWindowPos(hwnd, None, 0, 0, 0, 0, 0x37)
        ctypes.windll.dwmapi.DwmSetWindowAttribute.argtypes = (
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD)
        ctypes.windll.dwmapi.DwmSetWindowAttribute.restype = wintypes.LONG
        dark = ctypes.c_int(self.colors is DARK)
        for attribute in (20, 19):
            if ctypes.windll.dwmapi.DwmSetWindowAttribute(
                    hwnd, attribute, ctypes.byref(dark), ctypes.sizeof(dark)) == 0:
                break

    def hide(self):
        self.main.withdraw()

    def quit(self):
        if getattr(self, "quitting", False):
            return
        self.quitting = True
        self.pill.closing = True
        if self.pill.ready:
            self.pill.request("shutdown", lambda _result, _error: self.finish_quit())
            self.root.after(45000, self.finish_quit)
        else:
            self.finish_quit()

    def finish_quit(self):
        if getattr(self, "exited", False):
            return
        self.exited = True
        self.tray.close()
        self.main.destroy()
        self.root.quit()

    def save_preferences(self):
        PREFERENCES.write_text(json.dumps(self.preferences, indent=2) + "\n", encoding="utf-8")

    def read_update_result(self):
        result = APP_DIR / "update-result.json"
        try:
            value = json.loads(result.read_text(encoding="utf-8-sig"))
            return value.get("message", "") if value.get("status") == "failed" else ""
        except (OSError, ValueError, AttributeError):
            return ""
        finally:
            result.unlink(missing_ok=True)

    def auto_check_update(self, reschedule=True):
        if self.preferences.get("auto_update") and self.updates.current_version:
            if self.updates.check(automatic=True):
                self.root.after(MANUAL_COOLDOWN * 1000, self.update_update_card)
        if reschedule and not getattr(self, "quitting", False):
            self.root.after(60 * 60 * 1000, self.auto_check_update)

    def poll_updates(self):
        while not self.updates.events.empty():
            event = self.updates.events.get_nowait()
            self.update_state = event
            state = event["state"]
            if state == "available" and self.update_manual:
                self.update_manual = False
                self.show()
                if messagebox.askyesno("WaveType update available",
                                       f"Download WaveType {event['version']} now?",
                                       parent=self.main):
                    self.updates.download()
            elif state == "ready" and self.prompted_version != event["version"]:
                self.prompted_version = event["version"]
                self.show()
                if messagebox.askyesno("Install WaveType update?",
                                       f"WaveType {event['version']} is downloaded and verified. "
                                       "WaveType will close, update, then reopen. Install now?",
                                       parent=self.main):
                    self.install_update(approved=True)
            elif state in ("current", "error"):
                self.update_manual = False
            self.update_update_card()
        if self.update_error_on_start:
            self.show()
            messagebox.showerror("WaveType update failed", self.update_error_on_start, parent=self.main)
            self.update_error_on_start = ""
        if not getattr(self, "quitting", False):
            self.root.after(250, self.poll_updates)

    def manual_check_update(self):
        if not self.updates.current_version:
            self.update_state = {"state": "error", "message": "Update checks require an installed WaveType build."}
            self.update_update_card()
            return
        self.update_manual = True
        if not self.updates.check():
            self.update_manual = False
        else:
            self.root.after(MANUAL_COOLDOWN * 1000, self.update_update_card)
        self.update_update_card()

    def set_auto_update(self):
        self.preferences["auto_update"] = self.auto_update_var.get()
        self.save_preferences()
        if self.auto_update_var.get():
            self.auto_check_update(reschedule=False)

    def install_update(self, approved=False):
        installer = self.updates.ready_installer()
        package = Path(sys.executable).parent
        helper_source = Path(__file__).resolve().parent / "packaging" / "update_helper.ps1"
        if not installer or not helper_source.is_file() or not (package / "Uninstall.exe").is_file():
            self.report("Express update requires an installed WaveType build and a verified download.")
            return
        if not approved and not messagebox.askyesno("Install WaveType update?",
                "WaveType will close, install the update, then reopen. Continue?", parent=self.main):
            return
        helper = APP_DIR / "update-helper.ps1"
        command = [str(Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" /
                       "WindowsPowerShell" / "v1.0" / "powershell.exe"),
                   "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-File", str(helper),
                   "-Installer", str(installer), "-InstallDir", str(package), "-AppPid", str(os.getpid()),
                   "-ExpectedSha256", self.updates.expected_hash,
                   "-ResultFile", str(APP_DIR / "update-result.json")]
        try:
            helper.write_bytes(helper_source.read_bytes())
            subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL, close_fds=True,
                             creationflags=subprocess.CREATE_NO_WINDOW | subprocess.DETACHED_PROCESS)
        except OSError as exc:
            self.report(f"Could not start the update: {exc}")
            return
        self.quit()

    def watch_ready(self):
        if self.pill.ready and not getattr(self, "initialized", False):
            self.initialized = True
            self.pill.request("model_status", self.receive_model)
            self.refresh_page()
        elif not self.pill.ready and not getattr(self, "initialized", False):
            self.root.after(500, self.watch_ready)

    def receive_model(self, data, error):
        if error:
            self.setup_error = error
            self.update_setup_issue()
            return
        else:
            self.model = data
            self.setup_error = ""
            self.update_model_cards()
            self.update_setup_issue()
            if hasattr(self, "microphone_status_label") and self.microphone_status_label.winfo_exists():
                self.microphone_status_label.configure(text=data.get("capture_error") or "Microphone ready")
        if self.page == "Setup" and hasattr(self, "setup_tier_label"):
            tier = "NVIDIA GPU detected" if self.model.get("gpu_available") else "CPU mode available"
            self.setup_tier_label.configure(text=tier + " · Smart cleanup is optional")
        if hasattr(self, "sidebar_engine_label"):
            self.sidebar_engine_label.configure(text=self.engine_description() if self.model else "Checking model…")

    def on_engine_event(self, event):
        if getattr(self, "exited", False):
            return
        kind = event["event"]
        if kind == "error":
            message = event["message"]
            if "Qwen model unavailable" in message:
                self.preferences["smart"] = False
                self.tray_smart_var.set(False)
                self.save_preferences()
            if "Saved microphone unavailable" in message:
                self.preferences["microphone"] = None
                self.save_preferences()
            if "Model unavailable" in message or "model unavailable" in message or "Microphone unavailable" in message:
                self.setup_error = message
                self.update_setup_issue()
            else:
                self.report(message)
        elif kind == "model_progress":
            self.model.setdefault("models", {})[event["model"]] = {
                key: value for key, value in event.items() if key not in ("event", "model")}
            self.update_model_cards()
            if event["model"] == "asr" and event["state"] == "ready":
                self.setup_error = ""
            self.update_setup_issue()
        elif kind == "cleanup_disabled":
            self.preferences["smart"] = False
            self.tray_smart_var.set(False)
            if hasattr(self, "smart_var"):
                self.smart_var.set(False)
            self.save_preferences()
        elif kind == "history_added" and self.page == "History":
            self.refresh_page()

    def font(self, size=10, weight="normal", style="sans"):
        return (getattr(self, "ui_fonts", {}).get(style, "Segoe UI"), size, weight)

    def label(self, parent, text, size=10, color="text", weight="normal", style="sans", **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=self.colors[color],
                        font=self.font(size, weight, style), anchor="w", **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        bg = self.colors["accent"] if primary else self.colors["button"]
        fg = self.colors["bg"] if primary else self.colors["text"]
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=self.colors["line"], activeforeground=self.colors["text"],
                         relief="flat", bd=0, padx=14, pady=7, cursor="hand2",
                         font=self.font(9, "bold" if primary else "normal"), **kwargs)

    def placeholder(self, entry, text):
        entry.insert(0, text)
        entry.configure(fg=self.colors["soft"])
        entry.placeholder = text

        def focus_in(_event):
            if entry.get() == text and entry.cget("fg") == self.colors["soft"]:
                entry.delete(0, tk.END)
                entry.configure(fg=self.colors["text"])

        def focus_out(_event):
            if not entry.get():
                entry.insert(0, text)
                entry.configure(fg=self.colors["soft"])

        entry.bind("<FocusIn>", focus_in)
        entry.bind("<FocusOut>", focus_out)

    def focus_entry(self, entry, background):
        entry.bind("<FocusIn>", lambda _event: entry.configure(bg=self.colors["focus"]), add="+")
        entry.bind("<FocusOut>", lambda _event: entry.configure(bg=background), add="+")

    def entry_text(self, entry):
        return "" if entry.get() == getattr(entry, "placeholder", None) and \
            entry.cget("fg") == self.colors["soft"] else entry.get()

    def icon_image(self, name, color):
        palette = "dark" if self.colors["bg"] == DARK["bg"] else "light"
        tone = ("main" if color == self.colors["text"] else
                "soft" if color == self.colors["soft"] else "muted")
        key = name.lower(), palette, tone
        if not hasattr(self, "icon_images"):
            self.icon_images = {}
        if key not in self.icon_images:
            path = Path(__file__).resolve().parent / "assets" / "icons" / f"{key[0]}-{palette}-{tone}.png"
            self.icon_images[key] = tk.PhotoImage(master=self.root, file=str(path))
        return self.icon_images[key]

    def icon(self, parent, name, color=None):
        return tk.Label(parent, image=self.icon_image(name, color or self.colors["muted"]),
                        bg=parent.cget("bg"), bd=0, padx=0, pady=0)

    def render(self):
        self.main.unbind_all("<MouseWheel>")
        for child in self.main.winfo_children():
            child.destroy()
        c = self.colors
        self.shell = tk.Frame(self.main, bg=c["bg"])
        self.shell.pack(fill="both", expand=True)
        side = tk.Frame(self.shell, bg=c["side"], width=228)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        brand = tk.Frame(side, bg=c["side"])
        brand.pack(fill="x", padx=20, pady=(22, 26))
        if not hasattr(self, "brand_image"):
            self.brand_image = tk.PhotoImage(master=self.root, file=str(ASSETS / "logo_expanded.png"))
        tk.Label(brand, image=self.brand_image, bg=c["side"], bd=0).pack(side="left")
        tk.Label(brand, text="Beta", bg="#EADBFC" if self.theme != "Dark" else c["button"],
                 fg=c["link"], font=self.font(8, "bold"), padx=5, pady=2).pack(side="left", padx=(6, 0))
        self.nav_buttons = {}
        for page in ("History", "Dictionary", "Settings"):
            row = tk.Frame(side, bg=c["button"] if self.page == page else c["side"],
                           cursor="hand2", height=36)
            row.pack(fill="x", padx=12, pady=2)
            row.pack_propagate(False)
            icon = self.icon(row, page, c["text"] if self.page == page else c["muted"])
            icon.pack(side="left", padx=(12, 10))
            label = self.label(row, page, 10, weight="bold" if self.page == page else "normal")
            label.pack(side="left")
            for widget in (row, icon, label):
                widget.bind("<Button-1>", lambda _event, target=page: self.navigate(target))
                widget.bind("<Enter>", lambda _event, target=page: self.nav_hover(target))
                widget.bind("<Leave>", lambda _event, target=page: self.nav_hover(target))
            self.nav_buttons[page] = row, icon, label
        footer = tk.Frame(side, bg=c["side"])
        footer.pack(side="bottom", fill="x")
        engine_card = tk.Frame(footer, bg=c["card"], padx=12, pady=11,
                               highlightbackground=c["line"], highlightcolor=c["line"], highlightthickness=1)
        engine_card.pack(fill="x", padx=12, pady=(0, 12))
        self.label(engine_card, "Local Engine", 9, weight="bold").pack(fill="x")
        self.sidebar_engine_label = self.label(engine_card, "Checking model…", 8, color="muted")
        self.sidebar_engine_label.pack(fill="x", pady=(5, 0))
        if self.model:
            self.sidebar_engine_label.configure(text=self.engine_description())
        self.issue_label = self.label(engine_card, "", 8, color="danger", wraplength=160,
                                      justify="left")
        self.issue_label.pack(fill="x", pady=(6, 0))
        self.issue_button = self.button(engine_card, "Open Settings", lambda: self.navigate("Settings"))
        self.update_setup_issue()
        about = tk.Frame(footer, bg=c["side"], cursor="hand2", height=34)
        about.pack(fill="x", padx=12)
        about.pack_propagate(False)
        about_icon = self.icon(about, "About", c["muted"])
        about_icon.pack(side="left", padx=(12, 10))
        about_label = self.label(about, "About & Licence", 10, color="muted")
        about_label.pack(side="left")
        for widget in (about, about_icon, about_label):
            widget.bind("<Button-1>", lambda _event: self.navigate("About"))
        source = self.label(footer, " GitHub ↗", 10, color="link", cursor="hand2",
                            image=self.icon_image("github", c["text"]), compound="left")
        source.pack(fill="x", padx=24, pady=(8, 18))
        source.bind("<Button-1>", lambda _event: webbrowser.open(RELEASES.rsplit("/", 1)[0]))
        tk.Frame(side, bg=c["side"]).pack(fill="both", expand=True)
        self.content = tk.Frame(self.shell, bg=c["bg"])
        self.content.pack(side="left", fill="both", expand=True)
        self.header = tk.Frame(self.content, bg=c["bg"])
        self.header.pack(fill="x", padx=36, pady=(28, 20))
        self.heading_label = self.label(self.header, self.page, 19, weight="bold")
        self.heading_label.pack(side="left")
        self.body = tk.Frame(self.content, bg=c["bg"])
        self.body.pack(fill="both", expand=True, padx=36, pady=(0, 12))
        getattr(self, f"show_{self.page.lower()}")()

    def engine_description(self):
        status = self.model.get("models", {}).get("asr", {}).get("state", "missing")
        if status != "ready":
            return "Parakeet Redux · " + status.capitalize()
        return "Parakeet Redux · " + ("GPU available" if self.model.get("gpu_available") else "CPU mode")

    def update_setup_issue(self):
        if not hasattr(self, "issue_label") or not self.issue_label.winfo_exists():
            return
        asr = self.model.get("models", {}).get("asr", {})
        error = self.model.get("capture_error") or getattr(self, "setup_error", "")
        if asr.get("state") in ("missing", "failed", "paused"):
            error = "Model unavailable. Download Parakeet in Settings."
            if asr.get("error"):
                error += " " + asr["error"]
        self.issue_label.configure(text=error)
        if error:
            if not self.issue_button.winfo_manager():
                self.issue_button.pack(anchor="w", pady=(6, 0))
        elif self.issue_button.winfo_manager():
            self.issue_button.pack_forget()

    def style_nav(self, hover=None):
        for page, (row, icon, label) in self.nav_buttons.items():
            selected = page == self.page
            color = self.colors["button"] if selected or page == hover else self.colors["side"]
            for widget in (row, icon, label):
                widget.configure(bg=color)
            icon.configure(image=self.icon_image(page, self.colors["text"] if selected else self.colors["muted"]))
            label.configure(font=self.font(10, "bold" if selected else "normal"))

    def nav_hover(self, page):
        row = self.nav_buttons[page][0]
        x, y = row.winfo_pointerxy()
        inside = (row.winfo_rootx() <= x < row.winfo_rootx() + row.winfo_width()
                  and row.winfo_rooty() <= y < row.winfo_rooty() + row.winfo_height())
        self.style_nav(hover=page if inside else None)

    def render_page(self):
        self.main.unbind_all("<MouseWheel>")
        if hasattr(self, "settings_apply") and self.settings_apply.winfo_exists():
            self.settings_apply.destroy()
        previous = self.body
        self.body = tk.Frame(self.content, bg=self.colors["bg"])
        getattr(self, f"show_{self.page.lower()}")()
        previous.destroy()
        self.body.pack(fill="both", expand=True, padx=36, pady=(0, 12))

    def navigate(self, page):
        if page == self.page:
            self.refresh_page()
            return
        self.page = page
        self.heading_label.configure(text=page)
        self.style_nav()
        self.render_page()
        self.refresh_page()

    def refresh_page(self):
        if not self.pill.ready:
            return
        if self.page == "History":
            self.pill.request("history_list", self.receive_history, limit=100)
        elif self.page == "Dictionary":
            self.pill.request("dictionary_get", self.receive_dictionary)
        elif self.page == "Settings":
            self.pill.request("devices", self.receive_devices)
            self.pill.request("model_status", self.receive_model)

    def show_setup(self):
        box = tk.Frame(self.body, bg=self.colors["card"], padx=28, pady=25)
        box.pack(fill="x", pady=12)
        self.label(box, "Local dictation, ready for your text box", 16, weight="bold").pack(fill="x", pady=(0, 12))
        self.label(box, "Parakeet Redux downloads and verifies on first launch. "
                   "Open Settings to see progress, pause, or retry. Qwen Smart cleanup is optional. "
                   "Future dictation works offline after the download.", 11,
                   wraplength=560, justify="left").pack(fill="x", pady=(0, 16))
        tier = "NVIDIA GPU detected" if self.model.get("gpu_available") else "CPU mode available"
        self.setup_tier_label = self.label(box, tier + " · Smart cleanup is optional", 11, color="muted")
        self.setup_tier_label.pack(fill="x", pady=(0, 22))
        self.button(box, "Open model settings", lambda: self.navigate("Settings")).pack(anchor="w", pady=(0, 10))
        self.button(box, "Continue to history", self.finish_setup, primary=True).pack(anchor="w")

    def finish_setup(self):
        if not self.pill.ready:
            self.report("Please wait for the engine to finish setup.")
            return
        self.first_run = False
        self.save_preferences()
        self.navigate("History")

    def receive_history(self, data, error):
        if error:
            self.report(error)
            return
        if data != self.history:
            self.history = data
            if self.page == "History":
                self.render_page()

    def scroll_area(self, parent):
        canvas = tk.Canvas(parent, bg=self.colors["bg"], highlightthickness=0, bd=0)
        style = ttk.Style(self.root)
        if style.theme_use() != "clam":
            style.theme_use("clam")
        style.layout("STT.Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {
            "sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"sticky": "nswe", "expand": True})]})])
        style.configure("STT.Vertical.TScrollbar", background=self.colors["soft"],
                        troughcolor=self.colors["bg"], bordercolor=self.colors["bg"],
                        lightcolor=self.colors["soft"], darkcolor=self.colors["soft"],
                        arrowsize=8, borderwidth=0)
        style.map("STT.Vertical.TScrollbar", background=[("active", self.colors["muted"])])
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview,
                            style="STT.Vertical.TScrollbar", takefocus=False)
        inside = tk.Frame(canvas, bg=self.colors["bg"])
        def update_scroll(_event=None):
            if not canvas.winfo_exists():
                return
            canvas.configure(scrollregion=canvas.bbox("all"))
            overflowing = inside.winfo_reqheight() > canvas.winfo_height()
            if overflowing and not bar.winfo_manager():
                bar.pack(side="right", fill="y", padx=(8, 0))
            elif not overflowing and bar.winfo_manager():
                bar.pack_forget()
                canvas.yview_moveto(0)

        inside.bind("<Configure>", update_scroll)
        canvas.create_window((0, 0), window=inside, anchor="nw", tags="body")
        canvas.bind("<Configure>", lambda event: (canvas.itemconfigure("body", width=event.width),
                                                  update_scroll()))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        return inside

    def show_history(self):
        if not self.history:
            self.label(self.body, "Your dictations will appear here.", 10, color="muted").pack(anchor="w")
            return
        inside = self.scroll_area(self.body)
        current_date = None
        group = None
        for entry in self.history:
            if entry.get("date") != current_date:
                first_group = current_date is None
                current_date = entry.get("date")
                self.label(inside, history_heading(current_date).upper(), 8, color="muted",
                           weight="bold").pack(anchor="w", pady=(0 if first_group else 22, 11))
                group = tk.Frame(inside, bg=self.colors["card"],
                                 highlightbackground=self.colors["line"], highlightcolor=self.colors["line"],
                                 highlightthickness=1)
                group.pack(fill="x")
            elif group.winfo_children():
                tk.Frame(group, bg=self.colors["line"], height=1).pack(fill="x", padx=18)
            row = tk.Frame(group, bg=self.colors["card"], padx=18, pady=14)
            row.pack(fill="x")
            stamp = self.label(row, history_time(entry.get("time")), 9, color="muted", width=8)
            stamp.pack(side="left", padx=(0, 16))
            actions = tk.Frame(row, bg=self.colors["card"], width=28, height=28)
            actions.pack(side="right")
            actions.pack_propagate(False)
            source = tk.Frame(row, bg=self.colors["side"], padx=8, pady=3,
                              highlightbackground=self.colors["line"], highlightcolor=self.colors["line"],
                                 highlightthickness=1)
            source.pack(side="right", padx=(12, 16))
            app = self.label(source, entry.get("app") or "", 8, color="muted", style="mono")
            app.pack()
            content = self.label(row, entry.get("text", ""), 10, wraplength=220, justify="left")
            content.pack(side="left", fill="x", expand=True)
            content.bind("<Configure>", lambda event, label=content:
                         label.configure(wraplength=max(120, event.width - 4)))
            delete = self.icon(actions, "Delete", self.colors["soft"])
            delete.configure(cursor="hand2")
            delete.bind("<Button-1>", lambda _event, e=entry: self.delete_history(e))

            def show_delete(_event, button=delete):
                button.place(relx=.5, rely=.5, anchor="center")

            def hide_delete(button=delete, container=row):
                if not container.winfo_exists():
                    return
                x, y = container.winfo_pointerxy()
                if not (container.winfo_rootx() <= x < container.winfo_rootx() + container.winfo_width()
                        and container.winfo_rooty() <= y < container.winfo_rooty() + container.winfo_height()):
                    button.place_forget()

            for widget in (row, stamp, actions, source, app, content, delete):
                widget.bind("<Enter>", show_delete)
                widget.bind("<Leave>", lambda _event, container=row, handler=hide_delete:
                            container.after(25, handler))

    def delete_history(self, entry):
        self.pill.request("history_change", lambda _data, error: self.after_history_change(error),
                          id=entry["id"], action="delete")

    def after_history_change(self, error):
        if error:
            self.report(error)
        else:
            self.refresh_page()

    def receive_dictionary(self, data, error):
        if error:
            self.report(error)
            return
        if data != self.dictionary:
            self.dictionary = data
            if self.page == "Dictionary":
                self.render_page()

    def show_dictionary(self):
        inside = self.scroll_area(self.body)
        self.dictionary_forms = {}
        self.dictionary_tab = getattr(self, "dictionary_tab", "snippets")
        tabs = tk.Frame(inside, bg=self.colors["bg"])
        tabs.pack(fill="x", pady=(0, 18))
        self.dictionary_tabs = {}
        self.dictionary_panels = {}
        for kind, title in (("snippets", "Snippet"), ("vocabulary", "Vocabulary")):
            tab = tk.Frame(tabs, bg=self.colors["bg"], cursor="hand2")
            tab.pack(side="left", padx=(0, 20))
            label = self.label(tab, title, 10, color="muted", cursor="hand2")
            label.pack(pady=(5, 8))
            underline = tk.Frame(tab, bg=self.colors["bg"], height=2)
            underline.pack(fill="x")
            for widget in (tab, label):
                widget.bind("<Button-1>", lambda _event, selected=kind: self.select_dictionary_tab(selected))
            self.dictionary_tabs[kind] = label, underline
        tk.Frame(inside, bg=self.colors["line"], height=1).pack(fill="x", pady=(0, 20))

        banner = tk.Frame(inside, bg=self.colors["banner"], padx=22, pady=18,
                          highlightbackground=self.colors["banner_line"],
                          highlightcolor=self.colors["banner_line"], highlightthickness=1)
        banner.pack(fill="x", pady=(0, 22))
        self.label(banner, "The stuff you shouldn't have to re-type.", 18,
                   style="serif").pack(fill="x", pady=(0, 5))
        self.label(banner, "Save the details you say often. Speak ‘insert my’ followed by a snippet key "
                   "to expand it instantly.", 10, color="muted", wraplength=650,
                   justify="left").pack(fill="x")

        for kind, heading, helper in (
                ("snippets", "Snippet", "Say ‘insert my’ followed by the key."),
                ("vocabulary", "Vocabulary", "Map mishearings to the spelling you want.")):
            panel = tk.Frame(inside, bg=self.colors["bg"])
            self.dictionary_panels[kind] = panel
            self.label(panel, helper, 9, color="muted").pack(fill="x", pady=(0, 12))
            form = tk.Frame(panel, bg=self.colors["card"], padx=12, pady=12,
                            highlightthickness=0)
            form.pack(fill="x", pady=(0, 18))
            save = self.button(form, "Save", lambda k=kind: self.save_dictionary_form(k), primary=True)
            save.pack(side="right", padx=(12, 0))
            key_entry = tk.Entry(form, width=20, font=self.font(10), fg=self.colors["text"],
                                 bg=self.colors["side"], relief="flat", bd=0,
                                 insertbackground=self.colors["text"])
            key_entry.pack(side="left", padx=(0, 12), ipady=7, ipadx=8)
            self.placeholder(key_entry, "Key (e.g. email)" if kind == "snippets" else "Correct spelling")
            self.focus_entry(key_entry, self.colors["side"])
            value_entry = tk.Entry(form, font=self.font(10), fg=self.colors["text"],
                                   bg=self.colors["side"], relief="flat", bd=0,
                                   insertbackground=self.colors["text"])
            value_entry.pack(side="left", fill="x", expand=True, ipady=7, ipadx=8)
            self.placeholder(value_entry, "Value (e.g. mail@example.com)" if kind == "snippets"
                             else "Mishearings, separated by commas")
            self.focus_entry(value_entry, self.colors["side"])
            self.dictionary_forms[kind] = key_entry, value_entry
            list_card = tk.Frame(panel, bg=self.colors["card"],
                                 highlightbackground=self.colors["line"], highlightcolor=self.colors["line"],
                                 highlightthickness=1)
            list_card.pack(fill="x")
            values = self.dictionary.get(kind, {})
            for index, (key, value) in enumerate(values.items()):
                if index:
                    tk.Frame(list_card, bg=self.colors["line"], height=1).pack(fill="x", padx=16)
                row = tk.Frame(list_card, bg=self.colors["card"], padx=16, pady=10)
                row.pack(fill="x")
                rendered = ", ".join(value) if isinstance(value, list) else value
                save = self.button(row, "Save", lambda: None, primary=True)
                delete = self.icon(row, "Delete", self.colors["soft"])
                delete.configure(cursor="hand2")
                delete.pack(side="right", padx=(8, 4))
                delete.bind("<Button-1>", lambda _event, k=kind, n=key:
                            self.change_dictionary(k, n, None))
                name_var = tk.StringVar(value=key)
                text_var = tk.StringVar(value=rendered)
                key_entry = tk.Entry(row, width=20, textvariable=name_var,
                                     font=self.font(10, "bold"), fg=self.colors["link"],
                                     bg=self.colors["card"], insertbackground=self.colors["link"],
                                     relief="flat", bd=0, highlightthickness=0)
                key_entry.pack(side="left", padx=(0, 10), ipady=5)
                self.focus_entry(key_entry, self.colors["card"])
                self.label(row, "→", 10, color="soft").pack(side="left", padx=(0, 10))
                value_entry = tk.Entry(row, textvariable=text_var,
                                       font=self.font(9, style="mono"), fg=self.colors["text"],
                                       bg=self.colors["value"], insertbackground=self.colors["text"],
                                       relief="flat", bd=0, highlightthickness=0)
                value_entry.pack(side="left", fill="x", expand=True, ipady=5, ipadx=7)
                self.focus_entry(value_entry, self.colors["value"])
                save.configure(command=lambda k=kind, old=key, name=name_var, text=text_var:
                               self.change_dictionary(k, name.get(), text.get(), original=old))

                def update_save(*_args, name=name_var, text=text_var, old=key,
                                original=rendered, button=save, delete_button=delete):
                    dirty = name.get() != old or text.get() != original
                    if dirty and not button.winfo_manager():
                        button.pack(side="right", before=delete_button, padx=(8, 0), ipady=0)
                    elif not dirty and button.winfo_manager():
                        button.pack_forget()

                name_var.trace_add("write", update_save)
                text_var.trace_add("write", update_save)
        self.select_dictionary_tab(self.dictionary_tab)

    def select_dictionary_tab(self, kind):
        self.dictionary_tab = kind
        for name, panel in self.dictionary_panels.items():
            panel.pack_forget()
            label, underline = self.dictionary_tabs[name]
            active = name == kind
            label.configure(fg=self.colors["text"] if active else self.colors["muted"],
                            font=self.font(10, "bold" if active else "normal"))
            underline.configure(bg=self.colors["text"] if active else self.colors["bg"])
        self.dictionary_panels[kind].pack(fill="x")

    def save_dictionary_form(self, kind):
        key_entry, value_entry = self.dictionary_forms[kind]
        self.change_dictionary(kind, self.entry_text(key_entry), self.entry_text(value_entry))

    def change_dictionary(self, kind, key, value, original=None):
        key = key.strip()
        if not key:
            self.report("Enter a key first.")
            return
        entries = dict(self.dictionary.get(kind, {}))
        if value is None:
            entries.pop(key, None)
        else:
            if original and key != original:
                if key in entries:
                    self.report("That key already exists.")
                    return
                entries.pop(original, None)
            entries[key] = ([item.strip() for item in value.split(",") if item.strip()]
                            if kind == "vocabulary" else value)
        self.pill.request("dictionary_set", lambda _result, error: self.after_dictionary_change(error),
                          kind=kind, entries=entries)

    def after_dictionary_change(self, error):
        if error:
            self.report(error)
        else:
            self.report("Dictionary saved.")
            self.refresh_page()

    def receive_devices(self, data, error):
        if not error:
            self.devices = data
            if self.page == "Settings" and hasattr(self, "mic_combo"):
                menu = self.mic_combo.nametowidget(str(self.mic_combo.cget("menu")))
                menu.delete(0, "end")
                for value in ["Default"] + [f"{device['index']}: {device['name']}" for device in data]:
                    menu.add_command(label=value, command=lambda item=value: self.mic_var.set(item))
                selected = self.preferences.get("microphone")
                if selected is not None and self.mic_var.get() == "Default":
                    self.mic_var.set(next((f"{device['index']}: {device['name']}" for device in data
                                           if device["index"] == selected), "Default"))
                    self.settings_initial["microphone"] = self.mic_var.get()
                    self.update_apply_visibility()

    def dropdown(self, parent, variable, values, width):
        control = tk.Menubutton(parent, textvariable=variable, width=width * 8,
                                bg=self.colors["card"], fg=self.colors["text"],
                                activebackground=self.colors["button"],
                                activeforeground=self.colors["text"],
                                relief="flat", bd=0, highlightthickness=0, indicatoron=False,
                                image=self.icon_image("chevron-down", self.colors["muted"]),
                                compound="right",
                                padx=10, pady=6, anchor="w", cursor="hand2", font=self.font(9))
        menu = tk.Menu(control, tearoff=False, bd=0, relief="flat",
                       bg=self.colors["card"], fg=self.colors["text"],
                       activebackground=self.colors["button"], activeforeground=self.colors["text"])
        control.configure(menu=menu)
        for value in values:
            menu.add_command(label=value, command=lambda item=value: variable.set(item))
        return control

    def settings_values(self):
        return {"smart": self.smart_var.get(), "login": self.login_var.get(),
                "tier": self.tier_var.get(), "theme": self.theme_var.get(),
                "threshold": self.threshold_var.get(), "microphone": self.mic_var.get()}

    def update_apply_visibility(self, *_args):
        if not hasattr(self, "settings_apply") or not self.settings_apply.winfo_exists():
            return
        dirty = self.settings_values() != self.settings_initial
        if dirty and not self.settings_apply.winfo_manager():
            self.settings_apply.pack(side="right")
        elif not dirty and self.settings_apply.winfo_manager():
            self.settings_apply.pack_forget()

    def show_settings(self):
        if not hasattr(self, "updates"):
            self.updates = UpdateManager(APP_DIR, installed_version(sys.executable))
            self.update_state = {"state": "idle"}
        inside = self.scroll_area(self.body)
        self.smart_var = tk.BooleanVar(value=bool(self.preferences.get("smart", False)))
        self.login_var = tk.BooleanVar(value=login_enabled())
        self.tier_var = tk.StringVar(value=self.preferences.get("tier", "auto"))
        self.theme_var = tk.StringVar(value=self.theme)
        self.threshold_var = tk.StringVar(value=str(self.preferences.get("tap_threshold_ms", 250)))
        selected_mic = self.preferences.get("microphone")
        mic_label = next((f"{d['index']}: {d['name']}" for d in self.devices
                          if d["index"] == selected_mic), "Default")
        self.mic_var = tk.StringVar(value=mic_label)
        self.settings_apply = self.button(self.header, "Apply settings", self.apply_settings,
                                          primary=True)
        self.settings_initial = self.settings_values()
        for variable in (self.smart_var, self.login_var, self.tier_var, self.theme_var,
                         self.threshold_var, self.mic_var):
            variable.trace_add("write", self.update_apply_visibility)
        card = tk.Frame(inside, bg=self.colors["subtle"], padx=18, pady=6,
                        highlightbackground=self.colors["line"], highlightcolor=self.colors["line"],
                                 highlightthickness=1)
        card.pack(fill="x")
        settings = (
            ("Hotkey", "Press and hold or tap to lock recording mode", "hotkey"),
            ("Tap threshold (ms)", "Time window between tapping and holding", "threshold"),
            ("Microphone", "Active input device for local dictation", "microphone"),
            ("Model / hardware tier", "Choose automatic GPU detection or CPU mode", "tier"),
            ("Language", "Automatic language detection", "language"),
            ("Theme", "Application color scheme", "theme"),
            ("Smart cleanup", "Optional local Qwen model; downloads on first use", "smart"),
            ("Start when I sign in", "Launch WaveType when Windows starts", "login"),
        )
        for index, (title, description, control) in enumerate(settings):
            if index:
                tk.Frame(card, bg=self.colors["line"], height=1).pack(fill="x")
            row = tk.Frame(card, bg=self.colors["subtle"], pady=13)
            row.pack(fill="x")
            info = tk.Frame(row, bg=self.colors["subtle"])
            info.pack(side="left", fill="x", expand=True)
            self.label(info, title, 10, weight="bold").pack(fill="x")
            self.label(info, description, 9, color="muted").pack(fill="x", pady=(3, 0))
            if control == "hotkey":
                badge = tk.Frame(row, bg=self.colors["card"], padx=12, pady=7,
                                 highlightbackground=self.colors["line"], highlightcolor=self.colors["line"],
                                 highlightthickness=1)
                badge.pack(side="right")
                self.label(badge, "Ctrl + Win · hold or tap to lock", 9, style="mono").pack()
            elif control == "threshold":
                self.label(row, "ms", 9, color="muted").pack(side="right", padx=(8, 0))
                threshold_entry = tk.Entry(row, textvariable=self.threshold_var, width=7,
                                           justify="right", font=self.font(10),
                                           bg=self.colors["card"], fg=self.colors["text"],
                                           relief="flat", bd=0, highlightthickness=0)
                threshold_entry.pack(side="right", ipady=6, ipadx=7)
                self.focus_entry(threshold_entry, self.colors["card"])
            elif control in ("microphone", "tier"):
                variable = self.mic_var if control == "microphone" else self.tier_var
                values = (["Default"] + [f"{d['index']}: {d['name']}" for d in self.devices]
                          if control == "microphone" else ["auto", "cpu"])
                combo = self.dropdown(row, variable, values, 28 if control == "microphone" else 12)
                combo.pack(side="right")
                if control == "microphone":
                    self.mic_combo = combo
            elif control == "language":
                self.label(row, "Automatic · 25 languages", 9, color="muted").pack(side="right")
            elif control == "theme":
                theme_box = tk.Frame(row, bg=self.colors["button"], padx=3, pady=3)
                theme_box.pack(side="right")
                self.theme_buttons = {}
                for value in ("Light", "Dark", "System"):
                    button = tk.Button(theme_box, text=" " + value, compound="left", relief="flat", bd=0,
                                       cursor="hand2", font=self.font(9), padx=10, pady=4,
                                       command=lambda selected=value: self.choose_theme(selected))
                    button.pack(side="left", padx=2)
                    self.theme_buttons[value] = button
                self.choose_theme(self.theme_var.get())
            else:
                variable = self.smart_var if control == "smart" else self.login_var
                toggle = tk.Canvas(row, width=44, height=24, bg=self.colors["subtle"],
                                   highlightthickness=0, cursor="hand2")
                toggle.pack(side="right")
                toggle.bind("<Button-1>", lambda _event, var=variable: var.set(not var.get()))
                trace = variable.trace_add("write", lambda *_args, var=variable, canvas=toggle:
                                           self.draw_toggle(canvas, var.get()))
                toggle.bind("<Destroy>", lambda _event, var=variable, token=trace:
                            var.trace_remove("write", token))
                self.draw_toggle(toggle, variable.get())
        self.microphone_status_label = self.label(
            inside, self.model.get("capture_error") or "Microphone ready", 9, color="muted",
            wraplength=540, justify="left")
        self.microphone_status_label.pack(fill="x", pady=(16, 5))
        self.button(inside, "Retry microphone", self.retry_microphone).pack(anchor="w")
        self.model_widgets = {}
        self.label(inside, "Local models", 13, weight="bold").pack(fill="x", pady=(22, 5))
        self.label(inside, "Downloads are verified before use. Pause keeps the partial file; "
                   "Cancel removes it.", 9, color="muted").pack(fill="x", pady=(0, 8))
        for name, title, detail in (
                ("asr", "Parakeet Redux", "Required for speech to text"),
                ("cleanup", "Qwen Smart cleanup", "Optional; downloading does not enable it")):
            card = tk.Frame(inside, bg=self.colors["card"], padx=16, pady=12,
                            highlightbackground=self.colors["line"], highlightthickness=1)
            card.pack(fill="x", pady=5)
            self.label(card, title, 11, weight="bold").pack(fill="x")
            self.label(card, detail, 9, color="muted").pack(fill="x", pady=(2, 7))
            status = self.label(card, "Checking files…", 9, color="muted", wraplength=530,
                                justify="left")
            status.pack(fill="x")
            bar = ttk.Progressbar(card, orient="horizontal", mode="determinate", maximum=100)
            actions = tk.Frame(card, bg=self.colors["card"])
            actions.pack(fill="x", pady=(8, 0))
            start = self.button(actions, "Download", lambda model=name: self.model_action("model_download", model))
            verify = self.button(actions, "Verify / repair", lambda model=name: self.model_action("model_download", model, repair=True))
            pause = self.button(actions, "Pause", lambda model=name: self.model_action("model_stop", model, "pause"))
            cancel = self.button(actions, "Cancel", lambda model=name: self.model_action("model_stop", model, "cancel"))
            delete = self.button(actions, "Delete model", lambda model=name: self.delete_model(model))
            for widget, icon in ((start, "download"), (verify, "repair"), (pause, "pause"),
                                 (cancel, "cancel"), (delete, "delete")):
                widget.configure(image=self.model_icon(icon), compound="left", takefocus=True,
                                 highlightthickness=1, highlightcolor=self.colors["link"])
            self.model_widgets[name] = (status, bar, start, verify, pause, cancel, delete, actions)
        self.update_model_cards()
        self.label(inside, "App updates", 13, weight="bold").pack(fill="x", pady=(22, 5))
        update_card = tk.Frame(inside, bg=self.colors["card"], padx=16, pady=12,
                               highlightbackground=self.colors["line"], highlightthickness=1)
        update_card.pack(fill="x", pady=5)
        row = tk.Frame(update_card, bg=self.colors["card"])
        row.pack(fill="x")
        info = tk.Frame(row, bg=self.colors["card"])
        info.pack(side="left", fill="x", expand=True)
        self.label(info, "Check and download automatically", 10, weight="bold").pack(fill="x")
        self.label(info, "Checks GitHub Releases; asks before installing.", 9, color="muted").pack(fill="x")
        self.auto_update_var = tk.BooleanVar(value=bool(self.preferences.get("auto_update", False)))
        toggle = tk.Canvas(row, width=44, height=24, bg=self.colors["card"],
                           highlightthickness=0, cursor="hand2", takefocus=1)
        toggle.pack(side="right")
        toggle.bind("<Button-1>", lambda _event: self.auto_update_var.set(not self.auto_update_var.get()))
        toggle.bind("<space>", lambda _event: self.auto_update_var.set(not self.auto_update_var.get()))
        toggle.bind("<Return>", lambda _event: self.auto_update_var.set(not self.auto_update_var.get()))
        trace = self.auto_update_var.trace_add("write", lambda *_args: (
            self.draw_toggle(toggle, self.auto_update_var.get()), self.set_auto_update()))
        toggle.bind("<Destroy>", lambda _event: self.auto_update_var.trace_remove("write", trace))
        self.draw_toggle(toggle, self.auto_update_var.get())
        self.update_status = self.label(update_card, "", 9, color="muted", wraplength=530)
        self.update_status.pack(fill="x", pady=(12, 4))
        self.update_bar = ttk.Progressbar(update_card, orient="horizontal", mode="determinate", maximum=100)
        actions = tk.Frame(update_card, bg=self.colors["card"])
        actions.pack(fill="x", pady=(8, 0))
        self.update_buttons = {
            "check": self.button(actions, "Check for updates", self.manual_check_update),
            "download": self.button(actions, "Download", self.updates.download),
            "pause": self.button(actions, "Pause", self.updates.pause),
            "resume": self.button(actions, "Resume", self.updates.download),
            "cancel": self.button(actions, "Cancel", self.updates.cancel),
            "install": self.button(actions, "Install update", self.install_update),
        }
        self.update_update_card()
        self.button(inside, "Open releases", lambda: webbrowser.open(RELEASES)).pack(anchor="w", pady=(9, 0))

    def update_update_card(self):
        if not hasattr(self, "update_status") or not self.update_status.winfo_exists():
            return
        state = self.update_state.get("state", "idle")
        version = self.update_state.get("version") or (self.updates.release or {}).get("version", "")
        labels = {"idle": "Updates have not been checked yet.", "checking": "Checking for a newer release…",
                  "current": "You have the newest available WaveType release.",
                  "available": f"WaveType {version} is available.",
                  "downloading": f"Downloading WaveType {version}…",
                  "paused": "Download paused. Resume when ready.",
                  "canceled": "Download canceled.",
                  "ready": f"WaveType {version} is ready to install.",
                  "error": self.update_state.get("message", "Update failed.")}
        if not self.updates.current_version:
            labels["idle"] = "App updates are available in installed builds."
        self.update_status.configure(text=labels.get(state, state))
        buttons = self.update_buttons
        for button in buttons.values():
            button.pack_forget()
        cooldown = time.monotonic() - self.updates.last_check < MANUAL_COOLDOWN
        buttons["check"].configure(state="disabled" if self.updates.busy or cooldown or
                                   not self.updates.current_version else "normal")
        buttons["check"].pack(side="left", padx=(0, 6))
        if state in ("available", "error", "canceled") and self.updates.release and not self.updates.busy:
            buttons["download"].pack(side="left", padx=(0, 6))
        elif state == "downloading":
            buttons["pause"].pack(side="left", padx=(0, 6))
            buttons["cancel"].pack(side="left", padx=(0, 6))
        elif state == "paused":
            buttons["resume"].pack(side="left", padx=(0, 6))
            buttons["cancel"].pack(side="left", padx=(0, 6))
        elif state == "ready":
            buttons["install"].pack(side="left", padx=(0, 6))
            buttons["cancel"].pack(side="left", padx=(0, 6))
        if state in ("downloading", "paused"):
            self.update_bar.pack(fill="x", pady=(5, 0), before=buttons["check"].master)
            received = self.update_state.get("received", 0)
            total = self.update_state.get("total", 0)
            self.update_bar.configure(value=100 * received / total if total else 0)
            if total:
                self.update_status.configure(text=f"{labels[state]} {received // (1024 * 1024)} / "
                                             f"{total // (1024 * 1024)} MiB")
        else:
            self.update_bar.pack_forget()

    def model_action(self, command, model, action=None, repair=False):
        if not self.pill.ready:
            self.report("Engine is still starting. Try again shortly.")
            return
        if model in getattr(self, "model_pending", set()):
            return
        self.model_pending = getattr(self, "model_pending", set()) | {model}
        self.update_model_cards()
        arguments = {"model": model}
        if action:
            arguments["action"] = action
        if repair:
            arguments["repair"] = True
        def finished(result, error):
            self.model_pending.discard(model)
            if error:
                self.report(error)
            elif result:
                self.model.setdefault("models", {})[model] = result
            self.update_model_cards()
        self.pill.request(command, finished, **arguments)

    def delete_model(self, model):
        title = "Parakeet Redux" if model == "asr" else "Qwen Smart cleanup"
        effect = ("Dictation will be unavailable until you download Parakeet again." if model == "asr"
                  else "Smart cleanup will be turned off. Dictation with Parakeet will still work.")
        if messagebox.askokcancel(f"Delete {title}?",
                f"Remove {title}'s model weights, downloaded runtimes, verification records, "
                "cached archives and partial downloads? "
                + ("Both CPU and GPU runtimes are included. " if model == "cleanup" else "")
                + f"\n\n{effect}\n\nYour other model, settings, dictionary and history are kept.",
                icon="warning", parent=self.main):
            self.model_action("model_delete", model)

    def model_icon(self, name):
        # Small monochrome line icons inherit the current theme and retain text labels.
        cache = getattr(self, "model_icons", {})
        self.model_icons = cache
        key = (name, self.colors["text"])
        if key not in cache:
            paths = {
                "download": [(8, 2, 8, 11), (4, 7, 8, 11), (8, 11, 12, 7), (2, 12, 2, 14), (2, 14, 14, 14), (14, 14, 14, 12)],
                "resume": [(4, 2, 4, 14), (4, 2, 13, 8), (13, 8, 4, 14)],
                "pause": [(5, 3, 5, 13), (11, 3, 11, 13)],
                "cancel": [(3, 3, 13, 13), (3, 13, 13, 3)],
                "repair": [(3, 5, 6, 2), (6, 2, 12, 3), (12, 3, 14, 7), (10, 7, 14, 7), (14, 7, 14, 3), (13, 11, 10, 14), (10, 14, 4, 13), (4, 13, 2, 9)],
                "delete": [(3, 4, 13, 4), (6, 2, 10, 2), (4, 6, 5, 14), (5, 14, 11, 14), (11, 14, 12, 6), (7, 7, 7, 11), (9, 7, 9, 11)]}
            icon = tk.PhotoImage(master=self.root, width=22, height=16)
            for x1, y1, x2, y2 in paths[name]:
                steps = max(abs(x2 - x1), abs(y2 - y1))
                for step in range(steps + 1):
                    icon.put(key[1], (round(x1 + (x2 - x1) * step / steps),
                                      round(y1 + (y2 - y1) * step / steps)))
            cache[key] = icon
        return cache[key]

    def retry_microphone(self):
        if not self.pill.ready:
            self.report("Engine is still starting. Try again shortly.")
            return
        def finished(_result, error):
            if error:
                self.model["capture_error"] = error
                self.setup_error = error
                self.update_setup_issue()
                if self.microphone_status_label.winfo_exists():
                    self.microphone_status_label.configure(text=error)
            else:
                self.model["capture_error"] = ""
                self.setup_error = ""
                self.update_setup_issue()
                self.pill.request("devices", self.receive_devices)
                if self.microphone_status_label.winfo_exists():
                    self.microphone_status_label.configure(text="Microphone ready")
        self.pill.request("capture_retry", finished)

    def update_model_cards(self):
        if hasattr(self, "sidebar_engine_label") and self.sidebar_engine_label.winfo_exists():
            self.sidebar_engine_label.configure(text=self.engine_description() if self.model else "Checking model…")
        for name, widgets in getattr(self, "model_widgets", {}).items():
            status, bar, start, verify, pause, cancel, delete, actions = widgets
            if not status.winfo_exists():
                continue
            value = self.model.get("models", {}).get(name, {})
            state = value.get("state", "missing")
            received, total = value.get("downloaded", 0), value.get("total", 0)
            filename = value.get("file", "")
            if state == "downloading":
                amount = (f"{received // (1024 * 1024)} / {total // (1024 * 1024)} MiB"
                          if total else f"{received // (1024 * 1024)} MiB")
                label = f"Downloading {filename or 'files'} · {amount}"
            elif state == "failed":
                label = value.get("error") or "Model operation failed. Retry to repair it."
            else:
                label = {"ready": ("Ready (previous runtime; use Verify / repair for a full check)"
                                    if value.get("legacy") else "Ready and verified"),
                         "verifying": "Verifying files…",
                         "paused": "Paused · Resume when ready", "missing": "Model unavailable",
                         "pausing": "Pausing…", "canceling": "Canceling…", "deleting": "Deleting model files…"}.get(state, state)
            disk = value.get("disk_bytes", 0)
            size = "Disk usage unavailable" if disk is None else f"{disk / (1024 ** 3):.2f} GiB on disk" if disk >= 1024 ** 3 else f"{disk / (1024 ** 2):.1f} MiB on disk"
            status.configure(text=f"{label}\n{size}")
            bar.stop()
            if state in ("downloading", "paused", "verifying", "deleting", "pausing", "canceling"):
                bar.pack(fill="x", pady=(8, 2), before=actions)
            else:
                bar.pack_forget()
            if state in ("verifying", "deleting", "pausing", "canceling") or state == "downloading" and not total:
                bar.configure(mode="indeterminate")
                bar.start(20)
            else:
                bar.configure(mode="determinate", value=100 * received / total if total else
                              (100 if state == "ready" else 0))
            visible = model_controls(value)
            buttons = {"download": start, "resume": start, "verify": verify, "pause": pause,
                       "cancel": cancel, "delete": delete}
            focused = self.root.focus_get()
            for widget in (start, verify, pause, cancel, delete):
                widget.pack_forget()
            start.configure(text="Resume" if "resume" in visible else "Download",
                            image=self.model_icon("resume" if "resume" in visible else "download"))
            if name in getattr(self, "model_pending", set()):
                visible = ()
            for action in visible:
                buttons[action].pack(side="left", padx=(0, 6))
            if focused in buttons.values() and focused not in [buttons[a] for a in visible]:
                (buttons[visible[0]] if visible else status).focus_set()

    def choose_theme(self, selected):
        self.theme_var.set(selected)
        for name, button in self.theme_buttons.items():
            active = name == selected
            color = self.colors["text"] if active else self.colors["muted"]
            button.configure(bg=self.colors["card"] if active else self.colors["button"],
                             fg=color, image=self.icon_image(
                                 {"Light": "sun", "Dark": "moon", "System": "monitor"}[name], color))

    def draw_toggle(self, canvas, enabled):
        canvas.delete("all")
        track = LIGHT["text"] if enabled else LIGHT["soft"]
        canvas.create_oval(0, 0, 24, 24, fill=track, outline=track)
        canvas.create_oval(20, 0, 44, 24, fill=track, outline=track)
        canvas.create_rectangle(12, 0, 32, 24, fill=track, outline=track)
        x = 23 if enabled else 3
        canvas.create_oval(x, 3, x + 18, 21, fill="#FFFFFF", outline="#FFFFFF")

    def apply_settings(self):
        try:
            threshold = int(self.threshold_var.get())
            if not 100 <= threshold <= 1000:
                raise ValueError()
        except ValueError:
            self.report("Tap threshold must be 100–1000 ms.")
            return
        mic = self.mic_var.get()
        microphone = None if mic == "Default" else int(mic.split(":", 1)[0])
        preference = {"smart": self.smart_var.get(), "tier": self.tier_var.get(),
                      "theme": self.theme_var.get(), "tap_threshold_ms": threshold,
                      "microphone": microphone}
        self.pill.request("settings", lambda _result, error: self.after_settings(preference, error),
                          smart=preference["smart"], tier=preference["tier"],
                          tap_threshold_ms=threshold, microphone=microphone, language="auto")

    def after_settings(self, preference, error):
        if error:
            self.report(error)
            return
        try:
            set_login(self.login_var.get())
        except OSError as exc:
            self.report(f"Could not change login setting: {exc}")
            return
        self.preferences.update(preference)
        self.save_preferences()
        self.tray_smart_var.set(bool(preference["smart"]))
        old_theme = self.theme
        self.theme = preference["theme"]
        self.colors = DARK if self.theme == "Dark" or self.theme == "System" and system_dark() else LIGHT
        self.main.configure(bg=self.colors["bg"])
        self.style_titlebar()
        if self.theme != old_theme:
            self.render()
        else:
            self.settings_initial = self.settings_values()
            self.update_apply_visibility()

    def show_about(self):
        inside = self.scroll_area(self.body)
        package = Path(sys.executable).parent if getattr(sys, "frozen", False) else Path(__file__).resolve().parent
        try:
            version = json.loads((package / "build-info.json").read_text(encoding="utf-8"))["version"]
        except (OSError, ValueError, KeyError):
            version = "source build"
        self.label(inside, f"WaveType {version}", 15, weight="bold").pack(fill="x", pady=(0, 8))
        self.label(inside, "Parakeet downloads on first launch. Settings shows download progress "
                   "and disk usage, with Download, Pause / Resume, Cancel, Verify / repair, "
                   "and Delete model controls when relevant. Deleted models stay deleted until you choose Download. "
                   "After verification, speech processing runs on this computer.", 10,
                   wraplength=620, justify="left").pack(fill="x", pady=(0, 10))
        self.label(inside, "Models, preferences, history, and logs stay in %LOCALAPPDATA%\\STTCore "
                   "unless you select ‘Also delete all local data’ during uninstall. Exit WaveType "
                   "from the tray before installing or uninstalling; active recording will stop. "
                   "Check the release page for the signing and validation "
                   "status of your installer.", 9, color="muted",
                   wraplength=620, justify="left").pack(fill="x", pady=(0, 12))
        self.button(inside, "Release status", lambda: webbrowser.open(RELEASES)).pack(anchor="w", pady=2)
        for title, filename in (("Privacy and installation notices", "INSTALL-NOTICES.txt"),
                                ("Third-party licences", "LICENSES.md")):
            path = package / filename
            if path.is_file():
                self.button(inside, title, lambda item=path: webbrowser.open(item.as_uri())).pack(anchor="w", pady=2)
        info = [
            ("Parakeet Redux", "CC BY 4.0 · Moondream + NVIDIA · converted GGUF",
             "https://huggingface.co/moondream/parakeet-redux"),
            ("Qwen3-4B-Instruct-2507", "Apache 2.0 · optional cleanup model",
             "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"),
            ("llama.cpp", "MIT · optional local inference runtime",
             "https://github.com/ggml-org/llama.cpp"),
            ("parakeet.cpp", "MIT · local ASR runtime and binary",
             "https://github.com/mudler/parakeet.cpp"),
            ("Lordicon lock", "PRO icon · animated lock indicator",
             "https://lordicon.com/icons/system/solid/94-lock"),
            ("Desktop typefaces", "Figtree, EB Garamond, JetBrains Mono · SIL OFL 1.1",
             "https://github.com/google/fonts"),
            ("NVIDIA CUDA runtime", "Optional GPU components; NVIDIA redistributable terms apply",
             "https://docs.nvidia.com/cuda/eula/index.html")]
        self.label(inside, "Model and component credits", 11, weight="bold").pack(fill="x", pady=(16, 10))
        for title, detail, url in info:
            row = tk.Frame(inside, bg=self.colors["card"], padx=15, pady=11)
            row.pack(fill="x", pady=5)
            self.label(row, title, 11, weight="bold").pack(fill="x")
            self.label(row, detail, 10, color="muted").pack(side="left", fill="x", expand=True)
            self.button(row, "Source", lambda link=url: webbrowser.open(link)).pack(side="right")

    def report(self, message):
        if not self.main.winfo_exists() or not self.main.winfo_viewable():
            return
        if not hasattr(self, "notice") or not self.notice.winfo_exists():
            self.notice = self.label(self.content, "", 9, color="text", wraplength=400)
        self.notice.configure(text=message, bg=self.colors["button"])
        self.notice.place(relx=1, rely=1, x=-24, y=-20, anchor="se")
        if hasattr(self, "notice_timer"):
            self.root.after_cancel(self.notice_timer)
        self.notice_timer = self.root.after(3500, self.notice.place_forget)

    def run(self):
        try:
            self.pill.run()
        finally:
            if getattr(self, "tray", None):
                self.tray.close()
            self.engine_job.close()


def main():
    import maintenance
    if maintenance.active():
        ctypes.windll.user32.MessageBoxW(None, "WaveType setup is open. Finish or close setup before starting WaveType.", "WaveType", 0x40)
        return
    if os.name != "nt":
        raise OSError("The desktop client requires Windows")
    if not getattr(sys, "frozen", False) and Path(sys.executable).name.lower() == "python.exe":
        pythonw = Path(sys.executable).with_name("pythonw.exe")
        if pythonw.is_file():
            subprocess.Popen([str(pythonw), str(Path(__file__).resolve()), *sys.argv[1:]],
                             stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                             stderr=subprocess.DEVNULL,
                             creationflags=subprocess.CREATE_NO_WINDOW, close_fds=True)
            return
    APP_DIR.mkdir(parents=True, exist_ok=True)
    sys.stderr = (APP_DIR / "ui.log").open("a", encoding="utf-8", buffering=1)
    faulthandler.enable(sys.stderr)
    import msvcrt
    instance = (APP_DIR / "ui.lock").open("a+b")
    instance.write(b"1")
    instance.flush()
    instance.seek(0)
    try:
        msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    print(f"UI started: pid={os.getpid()}", file=sys.stderr)
    try:
        DesktopApp().run()
    finally:
        print(f"UI stopped: pid={os.getpid()}", file=sys.stderr)


if __name__ == "__main__":
    main()
