<p align="center">
<!-- Logo slot: replace assets/logo.svg with your final WaveType logo, or change the path below. -->
<img src="assets/logo.svg" alt="WaveType logo" width="112">
</p>
<h1 align="center">WaveType</h1>
**Speak naturally. Type anywhere. Keep your dictation on your Windows PC.**

WaveType is a local dictation app for Windows 10 and 11. A floating pill and a **Ctrl+Win** shortcut turn speech into text with Parakeet Redux; optional Qwen Smart cleanup can polish the result before insertion. After the first model downloads, inference runs offline.

[![Windows 10 and 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows11&logoColor=white)](#download-and-install) [![Latest release](https://img.shields.io/github/v/release/ABhattacharya-dev/stt-core-structure?include_prereleases&label=release)](https://github.com/ABhattacharya-dev/stt-core-structure/releases) [![GitHub issues](https://img.shields.io/github/issues/ABhattacharya-dev/stt-core-structure)](https://github.com/ABhattacharya-dev/stt-core-structure/issues)

[Download the Windows preview](https://github.com/ABhattacharya-dev/stt-core-structure/releases/tag/v0.1.0-beta.1) · [See how it works](#how-to-dictate) · [Contribute](#contributing)

> [!NOTE]
> The current Windows x64 release is **0.1.0 beta 1**. It is unsigned and has not yet been validated on a clean Windows installation or with Microsoft Defender. Keep Windows security protections enabled; see [release status](docs/RELEASE.md).

## Why WaveType?

| | |
| --- | --- |
| **Local transcription** | Parakeet Redux transcribes on your machine. Speech is not uploaded by WaveType; setup downloads verified model and runtime files. |
| **Dictate into other apps** | Hold **Ctrl+Win** to record and release to insert text into the focused text box. A quick tap locks recording for hands-free speech. |
| **Optional Smart cleanup** | Qwen3 4B can improve punctuation and grammar, resolve spoken corrections, or format requested JSON. It runs locally and is off by default. |
| **Personal vocabulary** | Add recognition aliases and deliberate snippets for names, addresses, and phrases. |
| **A small desktop companion** | Use the floating pill, tray menu, History, Dictionary, Settings, or the terminal client. |

**Performance snapshot:** On one GTX 1650 / Ryzen 7 4800H development machine, a seven-second replay reached final text in **1.69 s p50 with GPU cleanup** or **3.76 s p50 with CPU-only cleanup**, measured after recording release and excluding model startup. See the [full benchmarks and limitations](docs/BENCHMARKS.md).

## Preview

<!-- Screenshot slots: replace each placeholder cell with an <img> pointing to your real capture. Suggested paths: assets/screenshots/desktop.png and assets/screenshots/pill.png. -->
<table>
  <tr>
    <td align="center" width="65%"><strong>Desktop window</strong><br><em>Add your WaveType desktop screenshot here<br><code>assets/screenshots/desktop.png</code></em></td>
    <td align="center" width="35%"><strong>Floating pill</strong><br><em>Add your pill screenshot here<br><code>assets/screenshots/pill.png</code></em></td>
  </tr>
</table>

The existing logo above uses [`assets/logo.svg`](assets/logo.svg). Replace that file or update its path when your final WaveType logo is ready. For screenshots, save real captures at the paths shown above and replace the two placeholder cells with image tags.

## Download and install

1. Download **`WaveType-0.1.0-beta.1-Setup-x64.exe`** from the [beta 1 release](https://github.com/ABhattacharya-dev/stt-core-structure/releases/tag/v0.1.0-beta.1). The release also provides SHA-256 checksums.
2. Run the installer on **Intel/AMD x64 Windows 10 or 11**. Python is included; no separate Python or CUDA Toolkit install is needed.
3. Choose your installation folder and shortcuts. Startup on sign-in and the optional Smart cleanup download are off by default.
4. Let setup download and verify the base speech model. If interrupted, WaveType resumes the download when launched. Then open WaveType and select a text box to start dictating.

The installer and first use need internet for missing files. Transcription and optional cleanup run locally after their files are installed. ARM64 and 32-bit Windows are not supported by this release. See [privacy details](docs/PRIVACY.md) for network and data-storage behavior.

## How to dictate

| Action | What happens |
| --- | --- |
| Hold **Ctrl+Win**, then release | Record while held; insert the final text on release. |
| Tap **Ctrl+Win** quickly | Lock recording; press **Ctrl+Win** again to send. |
| Click the floating pill | Start locked recording; click again to send. Right-click to cancel. |
| Right-click the tray icon → **WaveType** | Open History, Dictionary, Settings, and About. Choose **Exit** to stop the app and engine. |

Smart cleanup can be enabled in the tray or Settings. Downloading its model during setup does not enable it. Windows may block text insertion into elevated apps; if that happens, the final text remains in History. The clipboard is untouched by hotkey insertion.

## Run from source

**Requirements:** Windows 10/11, Python 3.12, and internet access for first-run model/runtime downloads.

```powershell
git clone https://github.com/ABhattacharya-dev/stt-core-structure.git
cd stt-core-structure
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python desktop.py
```

The first desktop launch downloads and verifies Parakeet. Later launches show the pill and tray icon; the main window opens from the tray. For the terminal client, run `python stt.py` and press Enter to start and stop a recording. It asks whether to enable Smart cleanup; the default is **No**. Run `python stt.py --show-raw` to see the raw transcript alongside the final text.

For the standalone pill, run `python pill.py`; use `--smart` for optional cleanup or `--tap-threshold-ms 300` to adjust the quick-tap threshold. For a standalone engine, run `python engine.py serve --hotkey`. The terminal client leaves its resident engine running after exit; the desktop app owns and stops its engine when you choose **Exit**.

<details>
<summary>Personal terms and vocabulary in source runs</summary>

Create `personal_terms.json` beside `stt.py` for deliberate snippets:

```json
{"name":"Your Full Name","second email":"you@example.com"}
```

Say **“insert my”** followed by a key. Ordinary mentions are unchanged. Create `personal_vocabulary.json` for exact recognition aliases:

```json
{"Parakeet Redux":["parakeet redox"]}
```

Aliases correct known misrecognitions after transcription; they do not change Parakeet decoding. Keep them specific. Both files are ignored by Git. In the installed app, edit them through **Dictionary** instead.

</details>

## Privacy and local data

WaveType has no telemetry or speech-upload path in the reviewed application source. Parakeet runs locally; optional Qwen cleanup and the engine's authenticated IPC bind to `127.0.0.1`. Setup fetches missing models and runtimes over HTTPS and checks pinned SHA-256 hashes. An app receiving inserted text may independently sync it.

History stores the final text, date/time, and foreground app name as readable local JSON. Installed-app models, settings, dictionaries, history, and logs live under `%LOCALAPPDATA%\STTCore` and remain after uninstall; delete that folder manually if you also want to remove local data. Read the full [privacy notes](docs/PRIVACY.md).

## For developers

| Area | Start here |
| --- | --- |
| Desktop UI and pill | `desktop.py`, `pill.py`, [UI architecture](docs/UI_ARCHITECTURE.md) |
| Engine, audio, hotkeys, insertion | `engine.py`, `windows_support.py`, [architecture](docs/ARCHITECTURE.md) |
| Local client protocol | `client.py`, `ipc_protocol.py`, [IPC API](docs/IPC.md) |
| Models, cleanup, personal data | `model_manager.py`, `smart.py`, `vocabulary.py`, `user_data.py` |
| Packaging and release | `build.ps1`, `installer.nsi`, [release notes](docs/RELEASE.md) |

Run the regression suite before opening a pull request:

```powershell
python -m unittest discover
```

For replay and evaluation, use `python demo_engine.py path\to\clip.wav` or `python evaluate.py path\to\clip.wav --smart --tier auto --warmup`. A manifest can contain one `{"wav":"clip1.wav","reference":"the exact words you spoke"}` object per line; run it with `python evaluate.py --manifest recordings.jsonl`. Replay expects mono 16-bit PCM WAV. The report includes stage latency and word error rate against raw ASR. See the [architecture notes](docs/ARCHITECTURE.md) for the resident engine design.

## Contributing

Bug reports, Windows 10/11 installation results, accessibility feedback, documentation fixes, and reproducible performance measurements are useful. [Open an issue](https://github.com/ABhattacharya-dev/stt-core-structure/issues) with your Windows version, CPU/GPU, WaveType version, steps to reproduce, and relevant logs **with personal dictation removed**. For code or docs, fork the repo, make a focused change, run `python -m unittest discover` when applicable, and [open a pull request](https://github.com/ABhattacharya-dev/stt-core-structure/pulls) explaining what changed and how you checked it.

If WaveType helps you, [star the repository](https://github.com/ABhattacharya-dev/stt-core-structure) so other Windows dictation users can find it.

### Community files being added

These are the next project documents and GitHub templates. Paths are shown so you can check for each one as it is added; they are not published yet.

| Item | Planned path | Status |
| --- | --- | --- |
| Code of conduct | `CODE_OF_CONDUCT.md` | To add |
| Contribution guide | `CONTRIBUTING.md` | To add |
| Project-code license | `LICENSE` | To choose and add |
| Security policy | `SECURITY.md` | To add |
| Issue templates | `.github/ISSUE_TEMPLATE/` | To add |
| Pull request template | `.github/PULL_REQUEST_TEMPLATE.md` | To add |

## License and credits

The repository currently has **no declared license for its project code**. See [third-party notices](LICENSES.md) for the Parakeet, Qwen, llama.cpp, parakeet.cpp, font, and icon assets and their separate terms. A project-code license needs to be selected before describing WaveType as licensed open source.
