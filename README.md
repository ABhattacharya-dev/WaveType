<p align="center">
<img src="assets/logo.svg" alt="WaveType logo" width="112">
</p>
<h1 align="center">WaveType</h1>
<strong>Speak naturally. Type anywhere. Keep your dictation on your Windows PC.</strong>

WaveType is a local dictation app for Windows 10 and 11. A floating pill and a **Ctrl+Win** shortcut turn speech into text with Parakeet Redux; optional Qwen Smart cleanup can polish the result before insertion. After the first model downloads, inference runs offline.

[![Windows 10 and 11](https://img.shields.io/badge/Windows-10%20%7C%2011-0078D4?logo=windows11&logoColor=white)](#download-and-install) [![Latest release](https://img.shields.io/github/v/release/ABhattacharya-dev/WaveType?include_prereleases&label=release)](https://github.com/ABhattacharya-dev/WaveType/releases) [![GitHub issues](https://img.shields.io/github/issues/ABhattacharya-dev/WaveType)](https://github.com/ABhattacharya-dev/WaveType/issues) [![License: MIT](https://img.shields.io/badge/license-MIT-2E7D6B)](LICENSE)

[Download the Windows preview](https://github.com/ABhattacharya-dev/WaveType/releases/tag/v0.1.0-beta.1) · [See how it works](#how-to-dictate) · [Contribute](#contributing)

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

<table>
  <tr>
    <!-- 
    <td align="center" width="65%">
      <strong>Desktop window</strong><br>
      <em>Add your WaveType desktop screenshot here<br><code>assets/screenshots/desktop.png</code></em>
    </td> 
    -->
    <td align="center" width="100%">
      <strong>Floating pill</strong><br><br>
      <img src="assets/screenshots/pill.gif" alt="WaveType Floating Pill Demo" width="100%">
    </td>
  </tr>
</table>

## Download and install

1. Download **`WaveType-0.1.0-beta.1-Setup-x64.exe`** from the [beta 1 release](https://github.com/ABhattacharya-dev/WaveType/releases/tag/v0.1.0-beta.1). The release also provides SHA-256 checksums.
2. Run the installer on **Intel/AMD x64 Windows 10 or 11**. Python is included; no separate Python or CUDA Toolkit install is needed.
3. Choose your installation folder and shortcuts. Startup on sign-in is off by default.
4. Launch WaveType to download Parakeet; manage optional Qwen in Settings.

Installation finishes before model downloads. On first launch, WaveType downloads Parakeet; Qwen remains optional. Settings shows Download, Pause / Resume, Cancel, Verify / repair and Delete model controls when relevant, with progress and per-model disk usage.

The source tree and local development installer now target **0.1.0-beta1.01**; the beta 1 link above is the previously published release. Exit WaveType from the tray before upgrading or uninstalling. Setup checks for files still in use and offers Retry or Cancel; it never force-closes the app. Older uninstallers cannot be updated retroactively: install beta 1.01 to get the new uninstall choices.

Deleting a model removes its downloaded weights, runtimes, cached archives, partial files and verification records. Qwen deletion includes both CPU and GPU runtimes and turns off Smart cleanup. Parakeet deletion makes dictation unavailable until you download it again. Pause, Cancel and intentional deletion are remembered across restarts. The other model and your history, settings and dictionary are preserved. Progress bars appear only while downloading, paused, verifying, deleting, or completing a pause/cancel request.

History stores the final text, date/time, and foreground app name as readable local JSON. Installed-app models, settings, dictionaries, history, and logs live under `%LOCALAPPDATA%\STTCore`. Uninstall keeps them by default so reinstall restores your setup. Select **Also delete all local data** for a fresh start; this also removes partial downloads. Custom data locations are not removed. Read the full [privacy notes](docs/PRIVACY.md).


## How to dictate

| Action | What happens |
| --- | --- |
| Hold **Ctrl+Win**, then release | Record while held; insert the final text on release. |
| Tap **Ctrl+Win** quickly | Lock recording; press **Ctrl+Win** again to send. |
| Click the floating pill | Start locked recording; click again to send. Right-click to cancel. |
| Right-click the tray icon → **WaveType** | Open History, Dictionary, Settings, and About. Choose **Exit** to stop the app and engine. |

Smart cleanup can be enabled in the tray or Settings. Downloading its model in Settings does not enable it. Windows may block text insertion into elevated apps; if that happens, the final text remains in History. The clipboard is untouched by hotkey insertion.

## Run from source

**Requirements:** Windows 10/11, Python 3.12, and internet access for first-run model/runtime downloads.

```powershell
git clone https://github.com/ABhattacharya-dev/WaveType.git
cd WaveType
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

## Accessibility

WaveType is still being checked for keyboard, screen reader, contrast, and text scaling support. The [Accessibility page](ACCESSIBILITY.md) lists current input paths, known limits, and how to report a barrier.

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

Please read the [Code of Conduct](CODE_OF_CONDUCT.md) and [Contributing guide](CONTRIBUTING.md) before participating.

For suspected vulnerabilities, use the [Security Policy](SECURITY.md) instead of a public issue.

Bug reports, Windows 10/11 installation results, accessibility feedback, documentation fixes, and reproducible performance measurements are useful. [Open an issue](https://github.com/ABhattacharya-dev/WaveType/issues) with your Windows version, CPU/GPU, WaveType version, steps to reproduce, and relevant logs **with personal dictation removed**. For code or docs, fork the repo, make a focused change, run `python -m unittest discover` when applicable, and [open a pull request](https://github.com/ABhattacharya-dev/WaveType/pulls) using the [pull request template](.github/PULL_REQUEST_TEMPLATE.md) to explain what changed and how you checked it.

If WaveType helps you, [star the repository](https://github.com/ABhattacharya-dev/WaveType) so other Windows dictation users can find it.

### Community files

These documents and templates are available to contributors:

| Item | Document or path | Status |
| --- | --- | --- |
| Code of conduct | [Read the Code of Conduct](CODE_OF_CONDUCT.md) | Added |
| Contribution guide | [Read the Contributing guide](CONTRIBUTING.md) | Added |
| Project-code license | [MIT License](LICENSE) | Added |
| Security policy | [Read the Security Policy](SECURITY.md) | Added |
| Issue templates | [Bug report](.github/ISSUE_TEMPLATE/01-bug-report.yml) · [Feature request](.github/ISSUE_TEMPLATE/02-feature-request.yml) | Added |
| Pull request template | [Read the pull request template](.github/PULL_REQUEST_TEMPLATE.md) | Added |
| Accessibility | [Read the Accessibility page](ACCESSIBILITY.md) | Added |

## License and credits

WaveType project code is licensed under the [MIT License](LICENSE). Third-party models, runtimes, fonts, and artwork retain their own terms; see [third-party notices](LICENSES.md). The published beta 1 installer predates this license update; future installer builds include the project license text.
