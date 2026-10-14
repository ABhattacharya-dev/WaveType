# Windows UI implementation report

## Scope and decisions

The UI is a separate Tkinter/Win32 process. It talks to the engine only through its documented loopback IPC client. The main window is created once and hidden until opened; the pill remains a no-activate topmost tool window. The tray menu contains WaveType, a Smart cleanup toggle, and Exit. A lock on `%LOCALAPPDATA%/STTCore/ui.lock` permits one UI instance. The login option uses the current user's Run key. Light, dark, and system palettes are available.

History groups final text by date with time and app name; delete appears when a row is hovered. Dictionary manages snippets and vocabulary. Settings expose the current Ctrl+Win hybrid hotkey's tap threshold, microphone, CPU/auto tier, optional cleanup, automatic language mode, theme, and start on login. Setup waits for verified first-run model downloads. About shows model and runtime attribution.

Tk was chosen after measuring the earlier pill at 43.2 MiB and 0.00% of one CPU core over five seconds while idle. It uses the same process and renderer for the main window; Tauri would add a WebView2 process and required Rust/MSVC build tooling unavailable here. The UI remained below 40 MiB in a live main-window sample.

## Verification

The user physically confirmed Ctrl+Win hold and tap, Notepad insertion, and no Start-menu popup. This machine's isolated Chrome text area and VS Code editor also accepted Unicode insertion. The user reported testing other target apps and waived further compatibility checks. Windows Terminal was absent here; its user-scope installation timed out with `0x80072ee2`. Elevated insertion cannot be guaranteed across Windows integrity levels.

The original source UI and packaged UI were opened and inspected. The NSIS installer completed with exit code 0 on this Windows 11 machine, and the installed UI launched its own bundled engine process over IPC. The current source changes have not been packaged. A clean Windows 10/11 VM with empty model storage has **not** been run; first-run download in that environment remains a release gate.

## Historical measurements

Ryzen 7 4800H, GTX 1650 4 GB, Windows 11; five measured warm replays per row after one warmup. The 5.6-second test WAV was generated with Windows SpeechSynthesizer and says: “Hello there, let us meet tomorrow. Sorry, make it today.” All rows returned “Hello there, let us meet today.” Times are milliseconds from the replay release command to the result event; model startup and audio duration are excluded.

| Cleanup tier | UI | Wall p50 / p95 | ASR p50 / p95 | Cleanup p50 / p95 |
| --- | --- | ---: | ---: | ---: |
| GPU auto | running | 2479 / 2552 | 1277 / 1346 | 1180 / 1194 |
| GPU auto | closed | 2436 / 2464 | 1245 / 1276 | 1170 / 1187 |
| CPU only | running | 2424 / 2858 | 1318 / 1379 | 1235 / 1434 |
| CPU only | closed | 2316 / 4639 | 1192 / 2135 | 1236 / 2472 |

The engine's `release_to_ready_ms` and the client-observed wall time differed by 0.3–0.6 ms at p50 in all four rows. The larger run-to-run wall differences track ASR and cleanup variation, especially the CPU p95 outlier; five runs are not enough to make a tighter claim about UI overhead. Source UI screenshots and raw benchmark JSON are in ignored `artifacts/` so demo and personal data are not pushed.

With the installed app idle and smart cleanup unloaded, the UI used 37.3 MiB working set and the warm engine 934.0 MiB, 971.3 MiB combined. Each consumed 0.31% of one CPU core over a five-second sample. The warm ASR model dominates idle RAM.

## Source fix after the first pill review

The visible idle pill is 40×5 logical pixels, recording is 78×29, and locked is 94×29, scaled for the current monitor. The transparent outer window stays at a fixed size; the pill is rendered with antialiased capsule images and pre-rendered lock frames. Regression tests cover repeated state transitions, click handling, hover, and waveform animation. The installer has not been rebuilt.

The engine now loads the Q8 ASR model at recording start and releases it after 20 idle seconds. On this machine, the engine used 33.3 MiB at startup, 933.9 MiB while recording, and 73.5 MiB after 27 seconds idle. A separate model-only measurement found 0.35–0.43 s load time and 931 MiB loaded versus 33 MiB after release. Five warm raw WAV replays measured 630.3 ms p50 and 648.7 ms p95 from release to result, with the expected transcript. Active transcription still needs roughly 1 GiB; a smaller model backend would need to match its measured speed and accuracy before replacing it.

## Remaining release work

- Validate clean Windows 10 and 11 VMs with no Python, model cache, or CUDA Toolkit. Confirm first-run downloads and microphone permissions there.
- Sign both executables and the installer with an Authenticode certificate, then publish a signed update manifest. See `docs/RELEASE.md`.
- Automatic background update installation is planned but not yet implemented. The current Settings button opens the releases page on demand.
- A fixed-language selector and alternate hotkey chords need engine support and language-specific accuracy checks. The current adapter auto-detects Redux's supported languages.

## Source cleanup — October 14, 2026

Removed obsolete single-run cleanup and status-bar code, unused imports, and unused icon color variants. Engine background workers now receive a shutdown signal. Waveform events remain at 30 Hz during capture and become five-second heartbeats when inactive, with an immediate wake on state changes. This interval keeps the existing 180-second client socket timeout alive with substantially fewer idle notifications.

Five warm raw replays of the same synthetic WAV, with no UI and Smart cleanup off:

| Measurement | Before | After |
| --- | ---: | ---: |
| Release to ready p50 / p95 | 644.2 / 659.4 ms | 678.2 / 770.4 ms |
| ASR p50 / p95 | 625.7 / 640.3 ms | 654.1 / 754.8 ms |
| Client wall p50 / p95 | 644.6 / 659.8 ms | 678.5 / 770.8 ms |
| Observed idle level events / second | 29.6 | 0.34 |

The short idle samples covered 5.00 and 5.88 seconds respectively; steady inactive cadence is one event per five seconds. Both replay runs returned identical text. The later ASR run was slower; this cleanup does not demonstrate an inference speedup. Client overhead stayed below 0.5 ms at p50. These samples measure reduced idle IPC traffic, not a new RAM/CPU benchmark or physical hotkey latency.

## First public x64 preview

The 0.1.0-beta.1 installer now packages the WaveType brand and current source UI. It adds selectable shortcuts/startup, folder selection, optional cleanup download, model-setup progress and a developer-page checkbox. Historical packaging statements above refer to earlier source reviews. This release was compiled and statically reviewed without running tests or installation checks, as requested. Signing and Defender/clean-machine validation remain pending; see RELEASE.md.
