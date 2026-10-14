# Dictation engine

The engine owns capture, transcription, cleanup, history and text insertion. A UI is a client of the local JSON-lines socket. The existing terminal script uses the same client API. No runtime request is sent to a cloud service.

## Decisions

- **One resident process.** The engine holds the microphone between dictations. It loads Parakeet at recording start and unloads it after 20 idle seconds; the model load takes roughly 0.4 s on the measured machine and normally finishes while the user speaks. Optional cleanup unloads after five idle minutes. Speech-pause segmentation moves completed ASR work before key release. Redux cannot use the cache-aware `--stream` path, so the last segment still needs offline inference. The pinned Windows C API library lowered warm ASR on the sample WAV from roughly 1.28 s per CLI call to 0.70 s, with identical output. The CLI remains a fallback if the library cannot load.
- **Explicit capture states.** `idle`, `recording`, `locked`, and `processing` accept press, release, cancel and completion events. Capture keeps a short pre-roll and uses WebRTC VAD plus an ambient energy gate for pause detection; other sample rates use the energy gate. On this machine, five seconds of idle microphone input yielded at most six consecutive frames passing the combined gate at its initial floor, so a segment requires eight consecutive speech frames. This is a boundary detector, not a word-level VAD; recordings are never discarded solely by VAD.
- **Local IPC.** A loopback JSON-lines socket with a random bearer token is cross-language and avoids a UI framework. The endpoint file lives in the current user's application-data directory. Clients subscribe to state, level, result and error events; commands return an ID-correlated response.
- **Process containment.** A standalone engine owns a kill-on-close Windows Job Object for its children. The desktop client instead owns a job containing the hidden engine process and its descendants, so tray Exit or a UI crash stops the entire tree. The UI and engine remain separate for crash isolation and communicate through IPC; they appear as one tray app. Failure to assign a new engine to the UI job stops that engine immediately.
- **Output safety.** Personal snippets are protected by the existing placeholders. A lightweight rule skips cleanup for simple greetings. The LLM is told dictated text is untrusted data. Changed numbers, negation, introduced content words or personal placeholders reject cleanup and return the normal transcript. Cleanup failures always fall back.
- **Windows insertion.** Unicode `SendInput` types into the foreground control without touching the clipboard. A failed injection is an error event. Windows integrity isolation may prevent insertion into elevated apps; the client can still copy the result manually.
- **Model files.** The downloader resumes partial files and verifies SHA-256 before replacing the destination. Model weights, the Parakeet C API library, and llama.cpp bundles stay outside Git; the Parakeet CLI binary is already committed. Hardware chooses GPU cleanup on an NVIDIA card with at least 3.5 GB reported VRAM, otherwise CPU; failed GPU startup retries CPU. The 3.5 GB cutoff follows the tested 3.1 GB cleanup usage on a 4 GB GTX 1650. Explicit CPU-only mode is available for evaluation. CPU cleanup is refused when less than 3.5 GB RAM is available, leaving raw dictation working.
- **History.** Dated JSONL entries contain date, time, final text, and foreground process name. Old entries are compacted on engine startup; generated WAV files are removed. Raw text and stage timings remain available only in live result events.

## Rejected alternatives

- Keeping a `parakeet-cli` process open on stdin: its `transcribe` command handles one WAV and exits; Redux cannot use its cache-aware streaming path. The upstream C API provides a smaller resident solution than an HTTP server.
- Packed Redux as the low-end default: it is only 213 MB, but this CPU/build used a scalar kernel and took 25–27 s for the sample versus 0.7–0.8 s for Q8, with identical text.
- PyTorch: it would materially enlarge installation without evidence of a speed gain here.
- Clipboard paste: it risks overwriting clipboard contents and is less predictable across apps than Unicode injection.
- Aggressive automatic cleanup: the measured 4B model has changed corrected numbers and dates in fixtures; guarded opt-in gives the user a raw fallback.

## Risks and UI contract

Energy gating may miss quiet speech or split across pauses. The trailing segment remains on the release path. ASR currently recognizes the languages supported by the loaded model; a different ASR implementation can replace the adapter. Valid JSON can still carry the wrong meaning. `SendInput` is blocked across some integrity boundaries. A UI must connect using the endpoint token, render state/error/level events, and expose both capture modes.

## Redistribution

Parakeet Redux weights are [CC BY 4.0](https://huggingface.co/moondream/parakeet-redux); redistribution needs attribution. The [Qwen3 model](https://huggingface.co/Qwen/Qwen3-4B-Instruct-2507/blob/main/LICENSE) is Apache 2.0, and llama.cpp is MIT. The NVIDIA CUDA runtime DLLs come under NVIDIA's CUDA redistributable terms. Verify notice and redistribution obligations before packaging model weights or CUDA binaries into an installer; this branch downloads them per user instead.
