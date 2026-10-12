# STT engine

Local Windows 10/11 dictation with Parakeet Redux transcription, optional Qwen cleanup, a resident engine, and a terminal client. No UI is included. Runtime inference is offline after first-run downloads.

## Install

```powershell
git clone -b engine https://github.com/ABhattacharya-dev/stt-core-structure.git
cd stt-core-structure
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the terminal client with `python stt.py`. On first run the engine downloads the Parakeet GGUF and its small Windows C API library, resumes interrupted downloads, and verifies SHA-256. `runtime/parakeet-cli.exe` is included as a fallback. Answer `y` at **Smart cleanup? [y/N]:** to download and warm Qwen3 4B plus the verified llama.cpp runtime. The NVIDIA package includes CUDA runtime DLLs; it does not require an installed CUDA toolkit. A CPU package is selected when no suitable NVIDIA GPU is found. Model and runtime files are ignored by Git. Subsequent runs need no internet.

The engine remains running after the CLI exits and unloads the cleanup model after five idle minutes. Stop it with:

```powershell
python -c "from client import EngineClient; c=EngineClient(); c.command('shutdown'); c.close()"
```

The CLI prompts for Enter to start and Enter to stop. `python stt.py --show-raw` also prints the raw transcript. Only the final text is printed normally. Cleanup can resolve spoken corrections, grammar and punctuation, and JSON beginning with “write in JSON format.” Invalid or unsafe cleanup falls back to the transcript with snippets applied.

## Personal terms

Create `personal_terms.json` beside `stt.py` for deliberate snippets:

```json
{"name":"Your Full Name","second email":"you@example.com","phone number":"+1 555 0100"}
```

Say “insert my” followed by any key. Ordinary mentions stay unchanged. Create `personal_vocabulary.json` separately for exact recognition aliases:

```json
{"Parakeet Redux":["parakeet redox"],"Your Name":["your name as Parakeet often hears it"]}
```

Parakeet's current CLI has no hotword parameter. Vocabulary aliases correct known misrecognitions after ASR; they do not change decoding. Keep aliases specific to avoid replacing unrelated speech. Both personal files are ignored by Git.

## Engine, replay and evaluation

```powershell
python engine.py serve --hotkey
python demo_engine.py path\to\clip.wav
python evaluate.py path\to\clip.wav --smart --tier auto --warmup
python evaluate.py path\to\clip.wav --smart --tier cpu --warmup
python evaluate.py --manifest recordings.jsonl
python -m unittest test_smart test_engine
```

The hotkey defaults to Ctrl+Win. Hold the chord to record and release to send. A future client can set tap mode over IPC: first press locks, second press sends. Hotkey results type into the focused app with Unicode `SendInput`; the clipboard is untouched. Windows may block insertion into an elevated target. The final text remains in history even if insertion fails. The full client protocol is in [docs/IPC.md](docs/IPC.md), and design choices are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

For WER, create `recordings.jsonl` with one object per line:

```json
{"wav":"clip1.wav","reference":"the exact words you spoke"}
```

Replay requires mono 16-bit PCM WAV. The report includes p50/p95 stage latency, raw/final text and WER against the raw ASR output. WER only becomes meaningful with your own labeled recordings.

History is stored in ignored `history/YYYY-MM-DD.jsonl`. New records keep the old `time` and `text` fields and add `raw`, `cleaned`, `timings`, foreground `app`, and recording `mode`. Old history remains readable. Logs and the IPC endpoint are under `%LOCALAPPDATA%\STTCore`.

## Measured on this machine

GTX 1650 4 GB / Ryzen 7 4800H, one seven-second sample WAV replayed three measured times, October 12, 2026. The resident engine used one extra warmup replay. The prior script path was measured with prompt caching disabled and model startup reported separately. Times below are from replay release to text, excluding model startup and audio duration:

| Path | ASR p50/p95 | Cleanup p50/p95 | Release to ready p50/p95 |
| --- | --- | --- | --- |
| Prior GPU | 1.28/1.28 s | 4.77/4.78 s | 6.04/6.05 s |
| Engine GPU | 0.70/0.72 s | 0.96/0.98 s | 1.69/1.69 s |
| Prior CPU simulation | 1.40/1.83 s | 10.01/10.02 s timeout | 11.42/11.84 s, raw fallback |
| Engine CPU-only | 0.74/0.86 s | 3.02/3.05 s | 3.76/3.94 s |

Enabling prompt caching cut a short correction's GPU cleanup from about 4.0 s to 0.24–0.43 s after warmup; CPU cleanup took 1.21 s on the same short correction after a 13.94 s startup. The 32-case text fixture benchmark passed 29 cases with 0.404 s median cleanup. Its misses were a grammar singular/plural change, one extra comma, and a JSON quantity correction that kept the old number. Valid JSON can still be semantically wrong. Redux cannot use `parakeet-cli --stream`; its CLI reports that the model is not cache-aware. Pauses can be transcribed in the background, but the final segment still incurs ASR work at release. An official 213 MB packed Redux model produced the same sample text but took 25–27 s per clip on this CPU/build, so Q8 remains the default.
