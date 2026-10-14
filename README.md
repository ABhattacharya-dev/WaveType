# WaveType

Local Windows 10/11 dictation with Parakeet Redux transcription, optional Qwen cleanup, a resident engine, a terminal client, and a small floating pill with a desktop window. Runtime inference is offline after first-run downloads.

## Windows installer

Download `WaveType-0.1.0-beta.1-Setup-x64.exe` from the [GitHub prerelease](https://github.com/ABhattacharya-dev/stt-core-structure/releases/tag/v0.1.0-beta.1). It is for Intel/AMD x64 Windows 10/11 and includes Python, the app and the engine. Keep Defender enabled: this first preview is unsigned, and clean-machine and Defender validation are pending. The release includes SHA-256 checksums.

The wizard lets you choose an installation folder, Start Menu and desktop shortcuts, startup on sign-in, and whether to download optional Smart cleanup now. Startup and Smart cleanup downloads are off by default. Setup downloads and verifies the base speech model; interrupted downloads can resume when you launch WaveType. Smart cleanup remains off until enabled in the tray or Settings, even if its files were downloaded during setup. The finish page offers app launch and an unchecked developer-page link.

Speech processing runs locally after setup. Models, settings, personal dictionaries and history are retained under `%LOCALAPPDATA%\STTCore` when you uninstall. The uninstaller removes only shipped app files. Read the [privacy notes](docs/PRIVACY.md) and [release status](docs/RELEASE.md).

## Run from source

```powershell
git clone -b main https://github.com/ABhattacharya-dev/stt-core-structure.git
cd stt-core-structure
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Start the terminal client with `python stt.py`. On first run the engine downloads the Parakeet GGUF and its small Windows C API library, resumes interrupted downloads, and verifies SHA-256. `runtime/parakeet-cli.exe` is included as a fallback. Answer `y` at **Smart cleanup? [y/N]:** to download and warm Qwen3 4B plus the verified llama.cpp runtime. The NVIDIA package includes CUDA runtime DLLs; it does not require an installed CUDA toolkit. A CPU package is selected when no suitable NVIDIA GPU is found. Model and runtime files are ignored by Git. Subsequent runs need no internet.

Run `python desktop.py` for the Windows app. Its first-run screen waits while the engine downloads and verifies Parakeet. Later launches show only the pill and notification-area icon; right-click the icon and choose **WaveType** to open History, Dictionary, Settings, and About, or **Exit** to stop the app and its engine. The main window appears in the taskbar while open or minimized. Closing it removes the taskbar entry and leaves dictation active in the tray. The Smart cleanup toggle stays synchronized between the tray and Settings. The default light theme uses a warm off-white palette. System and dark themes are available in Settings. The app owns the engine as a hidden child process and communicates through the local [IPC API](docs/IPC.md).

The installer is built from `build.ps1` and `installer.nsi`. The current preview was compiled after source review; no tests or clean-VM installation checks were run for this release pass, as requested. Earlier development installers were checked on this Windows 11 machine.

The engine remains running after the CLI exits. It unloads Parakeet after about 20 idle seconds and the optional cleanup model after five idle minutes. Stop it with:

```powershell
python -c "from client import EngineClient; c=EngineClient(); c.command('shutdown'); c.close()"
```

The CLI prompts for Enter to start and Enter to stop. `python stt.py --show-raw` also prints the raw transcript. Only the final text is printed normally. Cleanup can resolve spoken corrections, grammar and punctuation, and JSON beginning with “write in JSON format.” Invalid or unsafe cleanup falls back to the transcript with snippets applied.

## Floating pill

Run `python pill.py` and leave it running. Select a text box in another app, then hold Ctrl+Win to record and release to insert text. A quick tap (under 250 ms) locks recording; press Ctrl+Win again to send. Click the pill to start locked recording and click again to send. Right-click it to cancel. The pill does not take focus from the text box. Run `python pill.py --tap-threshold-ms 300` to adjust tap timing, or add `--smart` for optional cleanup. Close the process with Ctrl+C in its terminal. Windows can block insertion into elevated apps; an insertion failure appears on the pill, and the final text remains in history.

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

In the installed app, these files live in `%LOCALAPPDATA%\STTCore`; edit them in Dictionary instead of opening JSON. The current Parakeet adapter detects language automatically across Redux's supported languages. A fixed-language selection is not implemented.

## Engine, replay and evaluation

```powershell
python engine.py serve --hotkey
python demo_engine.py path\to\clip.wav
python evaluate.py path\to\clip.wav --smart --tier auto --warmup
python evaluate.py path\to\clip.wav --smart --tier cpu --warmup
python evaluate.py --manifest recordings.jsonl
python -m unittest test_smart test_engine test_user_data
```

The hotkey defaults to Ctrl+Win. The standalone engine defaults to hold mode; the pill selects hybrid hold/tap mode. Clients can still select tap mode over IPC: first press locks, second press sends. Hotkey results type into the focused app with Unicode `SendInput`; the clipboard is untouched. Windows may block insertion into an elevated target. The final text remains in history even if insertion fails. The full client protocol is in [docs/IPC.md](docs/IPC.md), and design choices are in [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md).

For WER, create `recordings.jsonl` with one object per line:

```json
{"wav":"clip1.wav","reference":"the exact words you spoke"}
```

Replay requires mono 16-bit PCM WAV. The report includes p50/p95 stage latency, raw/final text and WER against the raw ASR output. WER only becomes meaningful with your own labeled recordings.

History is stored in ignored `history/YYYY-MM-DD.jsonl` in source runs, or `%LOCALAPPDATA%\STTCore\history` in the installed app. Each record contains only `date`, `time`, final `text`, and the foreground app name. The History screen groups entries by day and lets you delete a row on hover. On startup, older entries are compacted and WAV files previously generated in `history/audio` are removed. Logs and the IPC endpoint are under `%LOCALAPPDATA%\STTCore`.

## Code layout

| Files | Responsibility |
| --- | --- |
| `desktop.py`, `pill.py` | Desktop screens, tray, nonactivating pill |
| `client.py`, `ipc_protocol.py` | Local IPC client and endpoint paths |
| `engine.py`, `windows_support.py` | Capture, ASR, hotkeys, process lifetime and insertion |
| `stt.py`, `smart.py`, `vocabulary.py` | Terminal client, cleanup and personal replacements |
| `model_manager.py`, `user_data.py` | Verified downloads, dictionary and compact history |
| `evaluate.py`, `benchmark_*.py`, `demo_engine.py` | Replay, latency, accuracy and IPC checks |
| `test_*.py` | Regression tests |
| `assets/`, `licenses/`, `docs/` | UI assets, third-party notices and architecture |

Run `python -m unittest discover` before contributing. Models, personal dictionaries, history, benchmark artifacts and build outputs stay out of Git. The `core-structure` branch preserves the original terminal prototype; `feature` contains the current app.

## Measured on this machine

GTX 1650 4 GB / Ryzen 7 4800H, one seven-second sample WAV replayed three measured times, October 12, 2026. The resident engine used one extra warmup replay. The prior script path was measured with prompt caching disabled and model startup reported separately. Times below are from replay release to text, excluding model startup and audio duration:

| Path | ASR p50/p95 | Cleanup p50/p95 | Release to ready p50/p95 |
| --- | --- | --- | --- |
| Prior GPU | 1.28/1.28 s | 4.77/4.78 s | 6.04/6.05 s |
| Engine GPU | 0.70/0.72 s | 0.96/0.98 s | 1.69/1.69 s |
| Prior CPU simulation | 1.40/1.83 s | 10.01/10.02 s timeout | 11.42/11.84 s, raw fallback |
| Engine CPU-only | 0.74/0.86 s | 3.02/3.05 s | 3.76/3.94 s |

Enabling prompt caching cut a short correction's GPU cleanup from about 4.0 s to 0.24–0.43 s after warmup; CPU cleanup took 1.21 s on the same short correction after a 13.94 s startup. The 32-case text fixture benchmark passed 29 cases with 0.404 s median cleanup. Its misses were a grammar singular/plural change, one extra comma, and a JSON quantity correction that kept the old number. Valid JSON can still be semantically wrong. Redux cannot use `parakeet-cli --stream`; its CLI reports that the model is not cache-aware. Pauses can be transcribed in the background, but the final segment still incurs ASR work at release. An official 213 MB packed Redux model produced the same sample text but took 25–27 s per clip on this CPU/build, so Q8 remains the default.

## Branding

The app icon is generated from `assets/logo.svg`; the sidebar uses `assets/logo_expanded.svg`. Windows/Tk use the checked-in `WaveType.ico` and `logo_expanded.png` derivatives, so no SVG renderer is needed at runtime. The existing `STTCore` data folder is retained for compatibility with saved settings and history. Startup uses the WaveType registry value and migrates the previous STT Core value when changed.
