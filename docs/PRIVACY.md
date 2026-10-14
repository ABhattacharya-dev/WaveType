# WaveType privacy

Speech recognition uses Parakeet locally. Optional Smart cleanup uses Qwen through an authenticated server bound to 127.0.0.1. The engine's authenticated IPC also listens only on 127.0.0.1. WaveType has no telemetry or speech-upload path in the reviewed application source.

Setup downloads missing models and runtimes over HTTPS from Hugging Face and GitHub and verifies pinned SHA-256 hashes. Those services receive ordinary download connection information, not dictation. Browser links open only when selected. Dictation works offline after required files are installed. An app receiving inserted text may itself send or sync it.

The microphone remains open while the engine runs to maintain a short pre-roll in memory. Recorded clips and inference buffers stay in memory. History stores only date, time, final text and foreground process name. Personal dictionary files and history are readable local JSON, not encrypted. The keyboard hook handles the Ctrl+Win chord; ordinary keystrokes are not written to a key log.

Installed-app data lives in %LOCALAPPDATA%\STTCore. Individual history entries can be deleted in History. Uninstall retains models, preferences, dictionaries, history and diagnostic logs. To remove those too, exit WaveType and delete that data folder manually. Source runs keep personal dictionaries, models and history in ignored repository folders instead.

The release build rejects bundled models, WAV recordings, JSONL history, personal dictionaries, endpoint tokens and signing-key files. It produces a file manifest with SHA-256 hashes. This verifies package contents; it is not a complete audit of upstream native binaries or proof from network capture.

This first prerelease has not had a clean-VM, Defender or runtime network-capture check. No antivirus exclusions or changes to Windows protections are required or recommended. Trusted code signing remains pending.
