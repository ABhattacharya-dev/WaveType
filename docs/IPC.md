# Local engine IPC (version 1)

The engine listens on `127.0.0.1` at the port in `%LOCALAPPDATA%\STTCore\endpoint.json`. The file also contains a random `token` and engine `pid`. Read it as the same Windows user. Send one UTF-8 JSON object per line; every request includes `id`, `token`, `command`, and optional `args`. Responses have the same `id`, `ok`, and either `result` or `error`. The `subscribe` command enables unsolicited event lines on that connection. There is no network or cloud service after models are installed.

```json
{"id":1,"token":"<endpoint token>","command":"settings","args":{"mode":"hold","smart":true,"tier":"auto","hotkey":true}}
{"id":1,"ok":true,"result":{"mode":"hold","smart":true,"tier":"auto","hotkey":true}}
{"event":"state","value":"recording","mode":"hold"}
{"event":"level","value":0.42}
{"event":"result","raw":"...","text":"...","timings":{"asr_ms":1200,"cleanup_ms":400,"release_to_ready_ms":1600}}
```

Commands:

| Command | Args | Behavior |
| --- | --- | --- |
| `status` | none | Returns state, mode, audio level, sample rate, and cleanup readiness. |
| `devices` | none | Lists available microphone indexes and names. |
| `capture_retry` | none | Retries opening the selected microphone while idle; leaves the model controls available if no input device works. |
| `model_status` | none | Reports each model's `missing`, `verifying`, `downloading`, `paused`, `ready`, or `failed` state, progress bytes, current file, and error; also reports microphone availability, memory, GPU suitability, and tier. |
| `model_download` | `model`: `asr`/`cleanup`; optional `repair`: boolean | Starts or resumes verification and download in the background. `repair=true` refreshes a runtime carried over from an older installation. Repeated requests for an active job share that job. |
| `model_verify` | `model`: `asr`/`cleanup` | Verifies installed files in the background without downloading. |
| `model_stop` | `model`: `asr`/`cleanup`, `action`: `pause`/`cancel` | Stops an active job; pause retains partial files and cancel removes them. |
| `model_delete` | `model`: `asr`/`cleanup` | Asynchronous; requires idle dictation. Stops conflicting work, unloads the model, then deletes its owned files. Returns `deleting`; follow `model_progress` for completion or failure. Qwen deletion emits `cleanup_disabled` so clients save and display `smart=false`. |
| `dictionary_get` | none | Returns `snippets` and `vocabulary` objects. |
| `dictionary_set` | `kind`: `snippets`/`vocabulary`, `entries`: complete object | Atomically replaces one personal dictionary after validation. |
| `history_list` | optional `limit` (1–500), `offset` | Returns newest dated entries first. Old JSONL entries remain readable. |
| `history_change` | `id`, `action`: `delete` | Deletes the selected history entry. IDs are returned by `history_list` and may change after deletion. |
| `settings` | `mode`: `hold`/`tap`/`hybrid`; `tap_threshold_ms`: integer 100–1000; `smart`: boolean; `tier`: `auto`/`cpu`; `hotkey`: boolean; `microphone`: device index or null; `language`: `auto` | Accepted while idle, except `hotkey=false` can disable the hook during any state. Hybrid starts on Ctrl+Win press, sends on release at or above the threshold (default 250 ms), or locks after a shorter tap. `smart=true` warms cleanup before recording. `hotkey=true` installs Ctrl+Win handling. This adapter auto-detects among Redux's supported languages. |
| `subscribe` | none | Enables state, level, result, error, and `model_progress` events. |
| `start` or `press` | `insert`: boolean | In hold mode starts recording. In tap mode first press locks recording and second press sends it. `insert=true` types the final text into the foreground app. |
| `release` | none | Sends a hold recording; leaves tap recording locked. |
| `toggle` | `insert`: boolean | Starts locked recording when idle; sends when recording or locked. Used by the clickable pill. |
| `cancel` | none | Discards a recording or locked dictation. |
| `replay` | `path`: absolute WAV path, optional `insert`, optional `history` | Loads mono 16-bit PCM into a recording state for evaluation, then use `release` or a second `press`. History defaults off for replay. |
| `shutdown` | none | Stops the server and its child processes. |

States are `idle`, `recording`, `locked`, and `processing`. A UI should subscribe before starting capture, display `level` values between 0 and 1, and show `error` events. The `result` event contains raw and final text for the active dictation; `history_added` follows after the dated entry is stored. History persists only date, time, final text, and foreground process name. If insertion fails, the result still appears and an error event describes the failure.

`model_progress` includes `model`, `state`, `file`, `downloaded`, `total`, and `error`. A zero `total` means the server did not provide a content length. Starting speech capture while Parakeet is unavailable returns a "Model unavailable" error; the app and model controls remain accessible.

Model states additionally include `pausing`, `canceling`, and `deleting`. Each model reports `operation` (`download`, `repair`, `verify`, `delete`, or empty), `installed` (owned installed files present, not a verification guarantee), `partial` (resumable partial files present), and `disk_bytes` (all owned files, or null if inaccessible). Failures persist across restarts until an explicit retry. Pause, cancel and intentional deletion suppress automatic Parakeet downloads on future launches; `model_download` explicitly resumes them. Repeated starts/deletes share the current job; transitional controls should not submit duplicate requests.

Controls: missing → Download; downloading → Pause/Cancel; paused or interrupted with only partials → Resume/Cancel; installed, including repair failures → Verify / repair and Delete model. Initial verification and deletion show status only. Verification during download/repair permits Pause/Cancel. Show a progress bar for downloading, paused, verification, deletion and pause/cancel transitions, and show disk usage for every state. Confirm deletion in the client before issuing `model_delete`.

`shutdown` acknowledges after workers, microphone and model resources have closed. Active recording is discarded without insertion; completed processing can finish saving its history. Clients should allow shutdown to finish before closing their engine job handle.

The pill uses `python pill.py` and subscribes to `level` events at about 30 Hz while recording or locked. Other states send a level heartbeat every five seconds; state changes wake the level stream immediately. For direct hybrid IPC control, send `release` with `held_ms`; the built-in keyboard hook supplies that duration automatically.

`python demo_engine.py path\to\clip.wav` runs hold, cancel and tap through this API without a UI or microphone. `python evaluate.py path\to\clip.wav --smart --tier cpu --warmup` reports latency; `python evaluate.py --manifest recordings.jsonl` computes WER. Manifest lines contain `{"wav":"clip.wav","reference":"exact spoken words"}`. The engine uses the same API for the terminal client in `stt.py`.
