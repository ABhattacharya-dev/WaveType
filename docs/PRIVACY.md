WaveType Privacy

Overview

WaveType has no telemetry or speech-upload path in the reviewed application source. Speech recognition runs locally using Parakeet. Optional Smart cleanup uses Qwen through an authenticated server bound to 127.0.0.1.

Local Processing and Network Connections

Speech recognition uses Parakeet locally.

Optional Smart cleanup uses Qwen through an authenticated server bound to 127.0.0.1.

The engine's authenticated inter-process communication (IPC) also listens only on 127.0.0.1.

Setup downloads missing models and runtimes over HTTPS from Hugging Face and GitHub and verifies pinned SHA-256 hashes.

These download services receive ordinary connection information, not dictation.

Browser links open only when selected.

Dictation works offline after the required files are installed.

An application receiving inserted text may independently send or synchronize it.

Microphone and Data Storage

The microphone remains open while the engine runs to maintain a short pre-roll in memory. Recorded clips and inference buffers stay in memory.

History stores only the following information:

Date and time

Final text

Foreground process name

Personal dictionary files and history are stored as local JSON and are not encrypted.

The keyboard hook handles the Ctrl+Win chord. Ordinary keystrokes are not written to a key log.

Local Data and Uninstallation

Installed-app data lives in %LOCALAPPDATA%\STTCore.

Individual history entries can be deleted in History.

Uninstallation retains models, preferences, dictionaries, history, and diagnostic logs.

To remove these files as well, exit WaveType and manually delete the data folder.

Source runs keep personal dictionaries, models, and history in ignored repository folders instead.

Release Security and Validation

The release build rejects bundled models, WAV recordings, JSONL history, personal dictionaries, endpoint tokens, and signing-key files. It produces a file manifest containing SHA-256 hashes.

This verifies package contents. It is not a complete audit of upstream native binaries or proof based on network capture.

This first prerelease has not undergone clean-VM testing, Microsoft Defender validation, or runtime network-capture testing. Trusted code signing remains pending.

No antivirus exclusions or changes to Windows protections are required or recommended.
