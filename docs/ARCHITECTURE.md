# Dictation engine

The engine owns capture, transcription, cleanup, history and text insertion. A UI is a client of the local JSON-lines socket. The existing terminal script uses the same client API. No runtime request is sent to a cloud service.

## Decisions

- **One resident process.** The engine holds the microphone and optional cleanup server between dictations. It unloads cleanup after an idle period; Parakeet remains a per-segment CLI call because `parakeet-cli 0.6.1 --stream` rejects the Redux GGUF as non-cache-aware. Speech-pause segmentation moves completed ASR work before key release, but the last segment still costs a CLI launch.
- **Explicit capture states.** `idle`, `recording`, `locked`, and `processing` accept press, release, lock, cancel and completion events. Capture keeps a short pre-roll and uses low-cost energy gating for pause detection. The threshold adapts to the initial ambient level. This is a boundary detector, not a word-level VAD.
- **Local IPC.** A loopback JSON-lines socket with a random bearer token is cross-language and avoids a UI framework. The endpoint file lives in the current user's application-data directory. Clients subscribe to state, level, result and error events; commands return an ID-correlated response.
- **Process containment.** On Windows, children are assigned to a Job Object with kill-on-close. The job handle is private to the engine; closing it, including at process death, terminates its children. Failure to create or assign the job prevents launching a child.
- **Output safety.** Personal snippets are protected by the existing placeholders. A lightweight rule skips cleanup for text with no clear edit signal. The LLM gets delimited dictated data, not executable instructions. Changed numbers, negation or personal placeholders reject cleanup and return the normal transcript. Cleanup failures always fall back.
- **Windows insertion.** Unicode `SendInput` types into the foreground control without touching the clipboard. A failed injection is an error event. Windows integrity isolation may prevent insertion into elevated apps; the client can still copy the result manually.
- **Model files.** Existing local models and binaries are reused. The downloader resumes partial files and verifies SHA-256 before replacing the destination. Bundles and weights stay outside Git. Hardware chooses GPU cleanup if a working CUDA server is present, otherwise CPU; cleanup can be disabled on weak machines.
- **History.** New JSONL entries retain `text` for older readers and add raw/cleaned text, per-stage timings, mode and foreground app. Old entries remain readable without migration.

## Rejected alternatives

- Keeping a `parakeet-cli` process open on stdin: its `transcribe` command handles one WAV and exits; Redux cannot use its cache-aware streaming path.
- A persistent ASR server or PyTorch model: no working Redux server is shipped here, and PyTorch would materially enlarge installation.
- Clipboard paste: it risks overwriting clipboard contents and is less predictable across apps than Unicode injection.
- Aggressive automatic cleanup: the measured 4B model has changed corrected numbers and dates in fixtures; guarded opt-in gives the user a raw fallback.

## Risks and UI contract

Energy gating may miss quiet speech or split across pauses. The trailing segment remains on the release path. ASR currently recognizes the languages supported by the loaded model; a different ASR implementation can replace the adapter. Valid JSON can still carry the wrong meaning. `SendInput` is blocked across some integrity boundaries. A UI must connect using the endpoint token, render state/error/level events, expose both capture modes, and show raw and final text so edits can be undone.
