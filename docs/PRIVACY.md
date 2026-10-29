WaveType Privacy

Overview

WaveType has no telemetry or speech-upload path in the reviewed application source. Speech recognition runs locally using Parakeet. Optional Smart cleanup uses Qwen through an authenticated server bound to 127.0.0.1.

Local Processing and Network Connections

Speech recognition uses Parakeet locally.

Optional Smart cleanup uses Qwen through an authenticated server bound to 127.0.0.1.

The engine's authenticated inter-process communication (IPC) also listens only on 127.0.0.1.

After installation, the app downloads missing models and runtimes over HTTPS from Hugging Face and GitHub and verifies pinned SHA-256 hashes. Parakeet starts on first launch; Qwen downloads only when selected in Settings. Pausing retains a partial download; canceling removes it.

These download services receive ordinary connection information, not dictation.

Browser links open only when selected.

Dictation works offline after the required files are installed.

An application receiving inserted text may independently send or synchronize it.

Microphone and Data Storage

When an input device is available, the microphone remains open while the engine runs to maintain a short pre-roll in memory. The app can still open Settings if no microphone is available. Recorded clips and inference buffers stay in memory.

History stores only the following information:

Date and time

Final text

Foreground process name

Personal dictionary files and history are stored as local JSON and are not encrypted.

The keyboard hook handles the Ctrl+Win chord. Ordinary keystrokes are not written to a key log.

Local Data and Uninstallation

Installed-app data lives in %LOCALAPPDATA%\STTCore.

Individual history entries can be deleted in History.

Uninstallation keeps models, partial downloads, preferences, dictionaries, history, and diagnostic logs by default. Reinstalling restores this data.

Select the unchecked “Also delete all local data” option during uninstall to remove the canonical %LOCALAPPDATA%\STTCore folder for a fresh start. Directory links are not followed; any failure is reported and the uninstall entry remains available to retry. Custom data locations are not removed. Silent uninstall keeps data unless /REMOVE-DATA is explicitly supplied.

Settings offers separate deletion for Parakeet and Qwen, including each model's downloaded runtimes, cached archives, partial files and verification records. Qwen includes both CPU and GPU runtimes. Deleting Qwen turns off Smart cleanup; deleting Parakeet prevents dictation until downloaded again. Personal data and the other model are kept. Pause, cancel and deletion intent are stored locally and survive restarting the app.

Exit WaveType from the tray before install, upgrade or uninstall. Setup checks file access and asks you to retry if files remain in use. Exiting stops active recording without inserting unfinished speech, releases the microphone and stops model workers and owned cleanup processes.

Source runs keep personal dictionaries, models, and history in ignored repository folders instead.

Release Security and Validation

The release build rejects bundled models, WAV recordings, JSONL history, personal dictionaries, endpoint tokens, and signing-key files. It produces a file manifest containing SHA-256 hashes.

This verifies package contents. It is not a complete audit of upstream native binaries or proof based on network capture.

This first prerelease has not undergone clean-VM testing, Microsoft Defender validation, or runtime network-capture testing. Trusted code signing remains pending.

No antivirus exclusions or changes to Windows protections are required or recommended.
