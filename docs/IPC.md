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
| `settings` | `mode`: `hold`/`tap`; `smart`: boolean; `tier`: `auto`/`cpu`; `hotkey`: boolean | Accepted only while idle. `smart=true` warms cleanup before recording. `hotkey=true` installs Ctrl+Win handling. |
| `subscribe` | none | Enables state, level, result and error events. |
| `start` or `press` | `insert`: boolean | In hold mode starts recording. In tap mode first press locks recording and second press sends it. `insert=true` types the final text into the foreground app. |
| `release` | none | Sends a hold recording; leaves tap recording locked. |
| `cancel` | none | Discards a recording or locked dictation. |
| `replay` | `path`: absolute WAV path, optional `insert`, optional `history` | Loads mono 16-bit PCM into a recording state for evaluation, then use `release` or a second `press`. History defaults off for replay. |
| `shutdown` | none | Stops the server and its child processes. |

States are `idle`, `recording`, `locked`, and `processing`. A UI should subscribe before starting capture, display `level` values between 0 and 1, and show `error` events. The `result` event contains both raw and final text so a UI can offer “undo AI edit.” History records the same texts, stage timings, and foreground process/title. If insertion fails, the result still appears and an error event describes the failure.

`python demo_engine.py path\to\clip.wav` runs hold, cancel and tap through this API without a UI or microphone. `python evaluate.py path\to\clip.wav --smart --tier cpu --warmup` reports latency; `python evaluate.py --manifest recordings.jsonl` computes WER. Manifest lines contain `{"wav":"clip.wav","reference":"exact spoken words"}`. The engine uses the same API for the terminal client in `stt.py`.
