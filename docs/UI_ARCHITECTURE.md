# Windows UI architecture

## Choice

Use Tkinter and Win32 for this Windows prototype. The existing nonactivating pill is already measured at 43.2 MiB working set and 0.00% of one CPU core across a five-second idle sample on this machine; the resident ASR engine was 967.7 MiB and 0.00% in the same sample. Tk ships with Python, shares the pill's event loop, and avoids another renderer process. The main window is created once, hidden until opened from the tray, and reused while dictation remains active. A WebView2 shell would add a browser runtime and a Rust/MSVC build chain; neither Rust nor MSVC Build Tools is installed here. Tauri remains a viable later shell because all product operations go through the documented engine IPC.

## Boundaries

- The UI owns presentation, tray, login startup preference, and a single-instance mutex. It never imports transcription, cleanup, model-management, history, or dictionary modules. Its only engine dependency is the JSON-lines client.
- The engine owns hotkeys, recording, text insertion, microphone selection, model downloads, history, and personal terms. Additive IPC commands expose those operations. Engine changes are separate commits from UI changes.
- A background IPC reader feeds a thread-safe queue. Tk consumes events on its own thread. The microphone callback and key hook never wait on Tk or a socket.
- The pill is a no-activate, topmost tool window. The main window has a native, fixed-size title bar with minimize and close controls. An owner window keeps it out of the taskbar; it only takes focus when the user opens it. Dictation targets are captured by the engine before processing.
- UI settings live in `%LOCALAPPDATA%/STTCore/ui.json`; dictionary and history remain engine-owned. The UI requests a snapshot when shown and does not poll while hidden.
- The installer contains the UI executable, a separate engine executable, the pinned Parakeet CLI fallback, and attribution. Models and optional llama.cpp runtimes are first-run downloads. Installed runtime and personal files must be writable per user, not under Program Files.

## Risks and verification

The physical Ctrl+Win hold and tap paths and Notepad insertion were confirmed by the user without opening Start. An isolated browser text area and VS Code editor accepted Unicode `SendInput` here. The user reports testing remaining targets and waived further test work. Windows Terminal was absent on this machine and its user-scope installer returned `0x80072ee2`; an elevated input result is therefore user reported, not independently reproduced. UI release-to-text overhead will be measured against the IPC-only path. A clean Windows VM, installer, and signing remain separate release gates.

Tk provides adequate low-idle resource use, but its default controls require explicit styling and DPI checks. A loaded ASR model needs roughly 1 GiB; the engine releases it after 20 idle seconds. Historical warm and unloaded measurements are in UI_REPORT.md. Redux supports 25 languages and this adapter auto-detects them; selecting a particular language would require backend support and a measured accuracy check.
