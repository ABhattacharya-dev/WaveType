"""Light Windows desktop client for the local dictation engine."""

import base64
import ctypes
import json
import os
import sys
import tkinter as tk
import webbrowser
import winreg
from ctypes import wintypes
from pathlib import Path
from tkinter import filedialog, ttk

from ipc_protocol import APP_DIR
from pill import Pill


PREFERENCES = APP_DIR / "ui.json"
RELEASES = "https://github.com/ABhattacharya-dev/stt-core-structure/releases"
LIGHT = {"bg": "#F8F6F1", "side": "#EEEAE2", "card": "#FFFFFF", "text": "#25231F",
         "muted": "#6D685F", "line": "#DED9D0", "accent": "#25231F", "button": "#E9E5DD"}
DARK = {"bg": "#1F1F1E", "side": "#292927", "card": "#32322F", "text": "#F4F0E9",
        "muted": "#B9B3A9", "line": "#454541", "accent": "#F4F0E9", "button": "#3C3C38"}


def system_dark():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize") as key:
            return winreg.QueryValueEx(key, "AppsUseLightTheme")[0] == 0
    except OSError:
        return False


def startup_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    pythonw = Path(sys.executable).with_name("pythonw.exe")
    return f'"{pythonw if pythonw.exists() else sys.executable}" "{Path(__file__).resolve()}"'


def login_enabled():
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                            r"Software\Microsoft\Windows\CurrentVersion\Run") as key:
            return winreg.QueryValueEx(key, "STT Core")[0] == startup_command()
    except OSError:
        return False


def set_login(enabled):
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                       r"Software\Microsoft\Windows\CurrentVersion\Run", 0,
                       winreg.KEY_SET_VALUE) as key:
        if enabled:
            winreg.SetValueEx(key, "STT Core", 0, winreg.REG_SZ, startup_command())
        else:
            try:
                winreg.DeleteValue(key, "STT Core")
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
        user32.LoadIconW.restype = wintypes.HICON
        self.data.hIcon = user32.LoadIconW(None, ctypes.c_void_p(32512))
        self.data.szTip = "STT Core dictation"
        if not ctypes.windll.shell32.Shell_NotifyIconW(0, ctypes.byref(self.data)):
            raise ctypes.WinError()

    def message(self, message, _wparam, lparam):
        if message != self.MESSAGE:
            return False
        if lparam & 0xFFFF in (0x202, 0x203, 0x205):
            self.callback(lparam & 0xFFFF)
        return True

    def close(self):
        ctypes.windll.shell32.Shell_NotifyIconW(2, ctypes.byref(self.data))


class DesktopApp:
    def __init__(self):
        APP_DIR.mkdir(parents=True, exist_ok=True)
        try:
            self.preferences = json.loads(PREFERENCES.read_text(encoding="utf-8"))
        except (FileNotFoundError, ValueError):
            self.preferences = {}
        self.first_run = not PREFERENCES.exists()
        self.theme = self.preferences.get("theme", "Light")
        self.colors = DARK if self.theme == "Dark" or self.theme == "System" and system_dark() else LIGHT
        self.page = "Setup" if self.first_run else "History"
        self.history = []
        self.dictionary = {"snippets": {}, "vocabulary": {}}
        self.devices = []
        self.model = {}
        self.status = "Starting the local engine and checking model files…"
        self.pill = Pill(smart=bool(self.preferences.get("smart", False)),
                         tap_threshold_ms=int(self.preferences.get("tap_threshold_ms", 250)),
                         settings={"tier": self.preferences.get("tier", "auto"),
                                   "language": "auto", "microphone": self.preferences.get("microphone")},
                         on_event=self.on_engine_event, on_window_message=self.on_window_message)
        self.root = self.pill.root
        self.main = tk.Toplevel(self.root)
        self.main.title("STT Core")
        self.main.geometry("960x640")
        self.main.minsize(760, 520)
        self.main.configure(bg=self.colors["bg"])
        self.main.protocol("WM_DELETE_WINDOW", self.hide)
        self.main.bind("<Escape>", lambda _event: self.hide())
        self.main.withdraw()
        self.tray = TrayIcon(self.pill.hwnd, self.on_tray)
        self.menu = tk.Menu(self.root, tearoff=False)
        self.menu.add_command(label="Open STT Core", command=self.show)
        self.menu.add_command(label="Start or send dictation", command=lambda: self.pill._send("toggle", insert=True))
        self.menu.add_command(label="Cancel dictation", command=lambda: self.pill._send("cancel"))
        self.menu.add_separator()
        self.menu.add_command(label="Quit", command=self.quit)
        self.render()
        self.show()
        self.root.after(500, self.watch_ready)

    def on_window_message(self, message, wparam, lparam):
        return getattr(self, "tray", None) is not None and self.tray.message(message, wparam, lparam)

    def on_tray(self, button):
        if button in (0x202, 0x203):
            self.root.after_idle(self.show)
        elif button == 0x205:
            self.root.after_idle(self.popup_menu)

    def popup_menu(self):
        x, y = self.root.winfo_pointerxy()
        try:
            self.menu.tk_popup(x, y)
        finally:
            self.menu.grab_release()

    def show(self):
        self.main.deiconify()
        self.main.lift()
        self.main.focus_force()
        self.refresh_page()

    def hide(self):
        self.main.withdraw()

    def quit(self):
        self.tray.close()
        self.main.destroy()
        self.root.quit()

    def save_preferences(self):
        PREFERENCES.write_text(json.dumps(self.preferences, indent=2) + "\n", encoding="utf-8")

    def watch_ready(self):
        if self.pill.ready and not getattr(self, "initialized", False):
            self.initialized = True
            self.status = "Ready. Focus a text box and hold Ctrl+Win, or tap to lock."
            self.pill.request("model_status", self.receive_model)
            self.refresh_page()
        elif not self.pill.ready and not getattr(self, "initialized", False):
            self.root.after(500, self.watch_ready)

    def receive_model(self, data, error):
        if error:
            self.status = error
        else:
            self.model = data
            tier = "NVIDIA GPU" if data["gpu_available"] else "CPU"
            self.status = f"Ready · {tier} available · Automatic language detection"
        if self.page in ("Setup", "Settings"):
            self.render()

    def on_engine_event(self, event):
        kind = event["event"]
        if kind == "error":
            self.status = event["message"]
        elif kind == "result":
            self.status = "Dictation sent · " + event["text"][:72]
        elif kind == "history_added" and self.page == "History":
            self.refresh_page()
        elif kind == "state" and event["value"] == "idle" and self.pill.ready:
            if self.status.startswith("Recording"):
                self.status = "Ready. Focus a text box and hold Ctrl+Win, or tap to lock."
        elif kind == "state" and event["value"] in ("recording", "locked"):
            self.status = "Recording" if event["value"] == "recording" else "Recording locked"
        if kind != "level" and self.main.winfo_viewable():
            self.status_label.configure(text=self.status)

    def colors_for(self, surface):
        return {"bg": self.colors[surface], "fg": self.colors["text"]}

    def label(self, parent, text, size=11, color="text", weight="normal", **kwargs):
        return tk.Label(parent, text=text, bg=parent.cget("bg"), fg=self.colors[color],
                        font=("Segoe UI", size, weight), anchor="w", **kwargs)

    def button(self, parent, text, command, primary=False, **kwargs):
        bg = self.colors["accent"] if primary else self.colors["button"]
        fg = self.colors["bg"] if primary else self.colors["text"]
        return tk.Button(parent, text=text, command=command, bg=bg, fg=fg,
                         activebackground=self.colors["line"], activeforeground=self.colors["text"],
                         relief="flat", bd=0, padx=14, pady=7, cursor="hand2",
                         font=("Segoe UI", 10), **kwargs)

    def render(self):
        self.main.unbind_all("<MouseWheel>")
        for child in self.main.winfo_children():
            child.destroy()
        c = self.colors
        shell = tk.Frame(self.main, bg=c["bg"])
        shell.pack(fill="both", expand=True)
        side = tk.Frame(shell, bg=c["side"], width=196)
        side.pack(side="left", fill="y")
        side.pack_propagate(False)
        tk.Label(side, text="STT Core", bg=c["side"], fg=c["text"],
                 font=("Segoe UI", 17, "bold"), anchor="w").pack(fill="x", padx=24, pady=(27, 28))
        for page in ("History", "Dictionary", "Settings"):
            selected = self.page == page
            tk.Button(side, text=page, command=lambda target=page: self.navigate(target),
                      bg=c["card"] if selected else c["side"], fg=c["text"],
                      relief="flat", anchor="w", bd=0, padx=18, pady=10,
                      activebackground=c["card"], font=("Segoe UI", 11)).pack(fill="x", padx=12, pady=3)
        tk.Frame(side, bg=c["side"]).pack(fill="both", expand=True)
        tk.Button(side, text="About & licenses", command=lambda: self.navigate("About"),
                  bg=c["side"], fg=c["muted"], relief="flat", anchor="w", bd=0,
                  padx=18, pady=9, font=("Segoe UI", 10)).pack(fill="x", padx=12, pady=(0, 18))
        content = tk.Frame(shell, bg=c["bg"])
        content.pack(side="left", fill="both", expand=True)
        header = tk.Frame(content, bg=c["bg"])
        header.pack(fill="x", padx=32, pady=(26, 4))
        self.label(header, self.page, 22, weight="bold").pack(side="left")
        self.status_label = self.label(content, self.status, 10, color="muted", wraplength=680)
        self.status_label.pack(fill="x", padx=32, pady=(0, 20))
        self.body = tk.Frame(content, bg=c["bg"])
        self.body.pack(fill="both", expand=True, padx=32, pady=(0, 24))
        getattr(self, f"show_{self.page.lower()}")()

    def navigate(self, page):
        self.page = page
        self.render()
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

    def show_setup(self):
        box = tk.Frame(self.body, bg=self.colors["card"], padx=28, pady=25)
        box.pack(fill="x", pady=12)
        self.label(box, "Local dictation, ready for your text box", 16, weight="bold").pack(fill="x", pady=(0, 12))
        self.label(box, "The engine downloads and verifies Parakeet Redux on first run. "
                   "This may take several minutes. Future dictation works offline.", 11,
                   wraplength=560, justify="left").pack(fill="x", pady=(0, 16))
        tier = "NVIDIA GPU detected" if self.model.get("gpu_available") else "CPU mode available"
        self.label(box, tier + " · Smart cleanup is optional", 11, color="muted").pack(fill="x", pady=(0, 22))
        self.button(box, "Continue to history", self.finish_setup, primary=True).pack(anchor="w")

    def finish_setup(self):
        if not self.pill.ready:
            self.status = "Please wait for the engine to finish setup."
            self.status_label.configure(text=self.status)
            return
        self.first_run = False
        self.save_preferences()
        self.navigate("History")

    def receive_history(self, data, error):
        if error:
            self.report(error)
            return
        self.history = data
        if self.page == "History":
            self.render()

    def scroll_area(self, parent):
        canvas = tk.Canvas(parent, bg=self.colors["bg"], highlightthickness=0, bd=0)
        bar = ttk.Scrollbar(parent, orient="vertical", command=canvas.yview)
        inside = tk.Frame(canvas, bg=self.colors["bg"])
        inside.bind("<Configure>", lambda _event: canvas.configure(scrollregion=canvas.bbox("all")))
        canvas.create_window((0, 0), window=inside, anchor="nw", tags="body")
        canvas.bind("<Configure>", lambda event: canvas.itemconfigure("body", width=event.width))
        canvas.configure(yscrollcommand=bar.set)
        canvas.pack(side="left", fill="both", expand=True)
        bar.pack(side="right", fill="y")
        canvas.bind_all("<MouseWheel>", lambda event: canvas.yview_scroll(-int(event.delta / 120), "units"))
        return inside

    def show_history(self):
        if not self.history:
            self.label(self.body, "Your dictations will appear here.", 12, color="muted").pack(anchor="w")
            return
        inside = self.scroll_area(self.body)
        for entry in self.history:
            card = tk.Frame(inside, bg=self.colors["card"], padx=17, pady=13)
            card.pack(fill="x", pady=(0, 10))
            date = f"{entry.get('date', '')}  {entry.get('time', '')}"
            app_value = entry.get("app") or {}
            app = app_value.get("process") or "" if isinstance(app_value, dict) else str(app_value)
            self.label(card, (date + "  ·  " + app).strip(" ·"), 9, color="muted").pack(fill="x")
            self.label(card, entry.get("text", ""), 12, wraplength=600, justify="left").pack(fill="x", pady=(8, 6))
            if entry.get("raw") and entry.get("raw") != entry.get("text"):
                self.label(card, "Raw: " + entry["raw"], 9, color="muted", wraplength=600,
                           justify="left").pack(fill="x", pady=(0, 7))
            actions = tk.Frame(card, bg=self.colors["card"])
            actions.pack(fill="x")
            for title, action in (("Undo AI edit", "undo"), ("Retry", "retry"), ("Delete", "delete")):
                self.button(actions, title, lambda e=entry, a=action: self.history_action(e, a)).pack(side="left", padx=(0, 5))
            self.button(actions, "Download audio", lambda e=entry: self.download_audio(e),
                        state="normal" if entry.get("has_audio") else "disabled").pack(side="left")

    def history_action(self, entry, action):
        self.status = "Updating history…"
        self.status_label.configure(text=self.status)
        self.pill.request("history_change", lambda _data, error: self.after_history_change(error),
                          id=entry["id"], action=action, smart=bool(self.preferences.get("smart")))

    def after_history_change(self, error):
        if error:
            self.report(error)
        else:
            self.status = "History updated."
            self.status_label.configure(text=self.status)
            self.refresh_page()

    def download_audio(self, entry):
        destination = filedialog.asksaveasfilename(parent=self.main, defaultextension=".wav",
                                                    initialfile=f"dictation-{entry['id']}.wav",
                                                    filetypes=[("WAV audio", "*.wav")])
        if destination:
            self.pill.request("history_audio", lambda data, error: self.save_audio(destination, data, error),
                              id=entry["id"])

    def save_audio(self, path, data, error):
        if error:
            self.report(error)
            return
        try:
            Path(path).write_bytes(base64.b64decode(data["base64"], validate=True))
            self.report("Audio saved.")
        except (OSError, ValueError) as exc:
            self.report(str(exc))

    def receive_dictionary(self, data, error):
        if error:
            self.report(error)
            return
        self.dictionary = data
        if self.page == "Dictionary":
            self.render()

    def show_dictionary(self):
        inside = self.scroll_area(self.body)
        for kind, heading, helper in (
                ("snippets", "Snippets", "Say ‘insert my’ followed by the key."),
                ("vocabulary", "Vocabulary", "Map common mishearings to the spelling you want.")):
            self.label(inside, heading, 15, weight="bold").pack(fill="x", pady=(0, 3))
            self.label(inside, helper, 10, color="muted").pack(fill="x", pady=(0, 12))
            values = self.dictionary.get(kind, {})
            for key, value in values.items():
                row = tk.Frame(inside, bg=self.colors["card"], padx=10, pady=8)
                row.pack(fill="x", pady=3)
                rendered = ", ".join(value) if isinstance(value, list) else value
                self.label(row, key + "   →   " + rendered, 10, wraplength=490).pack(side="left", fill="x", expand=True)
                self.button(row, "Remove", lambda k=kind, n=key: self.change_dictionary(k, n, None)).pack(side="right")
            self.label(inside, "Key and value" if kind == "snippets" else
                       "Correct spelling and comma-separated aliases", 9, color="muted").pack(fill="x", pady=(9, 4))
            form = tk.Frame(inside, bg=self.colors["bg"])
            form.pack(fill="x", pady=(0, 27))
            key_entry = tk.Entry(form, width=18, font=("Segoe UI", 10))
            key_entry.pack(side="left", padx=(0, 7), ipady=6)
            value_entry = tk.Entry(form, font=("Segoe UI", 10))
            value_entry.pack(side="left", fill="x", expand=True, padx=(0, 7), ipady=6)
            self.button(form, "Save", lambda k=kind, a=key_entry, b=value_entry:
                        self.change_dictionary(k, a.get(), b.get())).pack(side="left")

    def change_dictionary(self, kind, key, value):
        key = key.strip()
        if not key:
            self.report("Enter a key first.")
            return
        entries = dict(self.dictionary.get(kind, {}))
        if value is None:
            entries.pop(key, None)
        elif kind == "vocabulary":
            entries[key] = [item.strip() for item in value.split(",") if item.strip()]
        else:
            entries[key] = value
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
            if self.page == "Settings":
                self.render()

    def show_settings(self):
        inside = self.scroll_area(self.body)
        card = tk.Frame(inside, bg=self.colors["card"], padx=20, pady=18)
        card.pack(fill="x")
        self.smart_var = tk.BooleanVar(value=bool(self.preferences.get("smart", False)))
        self.login_var = tk.BooleanVar(value=login_enabled())
        self.tier_var = tk.StringVar(value=self.preferences.get("tier", "auto"))
        self.theme_var = tk.StringVar(value=self.theme)
        self.threshold_var = tk.StringVar(value=str(self.preferences.get("tap_threshold_ms", 250)))
        selected_mic = self.preferences.get("microphone")
        mic_label = next((f"{d['index']}: {d['name']}" for d in self.devices
                          if d["index"] == selected_mic), "Default")
        self.mic_var = tk.StringVar(value=mic_label)
        for title, variable, values in (
                ("Hotkey", tk.StringVar(value="Ctrl+Win · hold or tap to lock"), None),
                ("Tap threshold (ms)", self.threshold_var, None),
                ("Microphone", self.mic_var, ["Default"] + [f"{d['index']}: {d['name']}" for d in self.devices]),
                ("Model / hardware tier", self.tier_var, ["auto", "cpu"]),
                ("Language", tk.StringVar(value="Automatic · 25 languages"), None),
                ("Theme", self.theme_var, ["System", "Light", "Dark"])):
            row = tk.Frame(card, bg=self.colors["card"])
            row.pack(fill="x", pady=7)
            self.label(row, title, 10).pack(side="left", fill="x", expand=True)
            if values:
                ttk.Combobox(row, textvariable=variable, values=values, state="readonly", width=36).pack(side="right")
            elif title in ("Hotkey", "Language"):
                self.label(row, variable.get(), 10, color="muted").pack(side="right")
            else:
                tk.Entry(row, textvariable=variable,
                         width=39, relief="flat", bg=self.colors["bg"], fg=self.colors["text"]).pack(side="right", ipady=6)
        for text, var in (("Smart cleanup (downloads Qwen on first use)", self.smart_var),
                          ("Start when I sign in", self.login_var)):
            tk.Checkbutton(card, text=text, variable=var, bg=self.colors["card"], fg=self.colors["text"],
                           activebackground=self.colors["card"], selectcolor=self.colors["card"],
                           font=("Segoe UI", 10)).pack(anchor="w", pady=5)
        self.button(card, "Apply settings", self.apply_settings, primary=True).pack(anchor="w", pady=(15, 0))
        self.label(inside, "Auto-update path: signed releases can be checked from GitHub. "
                   "Runtime inference stays local.", 10, color="muted", wraplength=650).pack(fill="x", pady=(18, 9))
        self.button(inside, "Open releases", lambda: webbrowser.open(RELEASES)).pack(anchor="w")

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
        self.report("Applying settings…")
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
        self.theme = preference["theme"]
        self.colors = DARK if self.theme == "Dark" or self.theme == "System" and system_dark() else LIGHT
        self.main.configure(bg=self.colors["bg"])
        self.status = "Settings saved."
        self.render()

    def show_about(self):
        info = [
            ("Parakeet Redux", "CC BY 4.0 · moondream/parakeet-redux",
             "https://huggingface.co/moondream/parakeet-redux"),
            ("Qwen3-4B-Instruct-2507", "Apache 2.0 · optional cleanup model",
             "https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507"),
            ("llama.cpp", "MIT · optional local inference runtime",
             "https://github.com/ggml-org/llama.cpp"),
            ("parakeet.cpp", "Runtime and binary notices are provided by the upstream project",
             "https://github.com/mudler/parakeet.cpp"),
            ("NVIDIA CUDA runtime", "Optional GPU components; NVIDIA redistributable terms apply",
             "https://docs.nvidia.com/cuda/eula/index.html")]
        self.label(self.body, "All speech processing runs on this computer after model setup.", 11,
                   wraplength=620).pack(fill="x", pady=(0, 20))
        for title, detail, url in info:
            row = tk.Frame(self.body, bg=self.colors["card"], padx=15, pady=11)
            row.pack(fill="x", pady=5)
            self.label(row, title, 11, weight="bold").pack(fill="x")
            self.label(row, detail, 10, color="muted").pack(side="left", fill="x", expand=True)
            self.button(row, "Source", lambda link=url: webbrowser.open(link)).pack(side="right")

    def report(self, message):
        self.status = message
        if self.main.winfo_exists():
            self.status_label.configure(text=message)

    def run(self):
        try:
            self.pill.run()
        finally:
            if getattr(self, "tray", None):
                self.tray.close()


def main():
    if os.name != "nt":
        raise OSError("The desktop client requires Windows")
    APP_DIR.mkdir(parents=True, exist_ok=True)
    import msvcrt
    instance = (APP_DIR / "ui.lock").open("a+b")
    instance.write(b"1")
    instance.flush()
    instance.seek(0)
    try:
        msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
    except OSError:
        return
    DesktopApp().run()


if __name__ == "__main__":
    main()
