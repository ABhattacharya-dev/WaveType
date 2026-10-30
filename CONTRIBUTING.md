# Contributing to WaveType

Thanks for helping improve local dictation on Windows. Contributions can be code, documentation, bug reports, accessibility feedback, installation results, or reproducible measurements. Please read the [Code of Conduct](CODE_OF_CONDUCT.md) before participating.

> **License:** WaveType project code is licensed under [MIT](LICENSE). Third-party components and artwork retain the separate terms listed in [LICENSES.md](LICENSES.md). Make sure you have the right to contribute any code or assets you submit.

## Find a useful task

- Search [existing issues](https://github.com/ABhattacharya-dev/WaveType/issues) before opening a new one.
- Small documentation fixes, clear reproduction steps, Windows 10/11 installation reports, accessibility findings, and labeled speech benchmarks are especially useful.
- For a larger change or a behavior change, open an issue first so the approach can be discussed before you invest time.

## Report a bug

For a suspected vulnerability, follow the [Security Policy](SECURITY.md) and report privately. For accessibility barriers, see the [Accessibility page](ACCESSIBILITY.md) and use the same [bug report form](https://github.com/ABhattacharya-dev/WaveType/issues/new/choose) as other bugs. Include:

1. WaveType version or commit, Windows version, CPU, and GPU (if relevant).
2. Whether you used the installer, desktop app from source, terminal client, or standalone pill.
3. Steps to reproduce, expected behavior, and actual behavior.
4. Whether Smart cleanup was enabled and whether this was the first run.
5. A short, redacted log excerpt or screenshot if it helps.

WaveType history and logs can contain dictated text or app names. **Remove personal speech, contact details, tokens, and file paths before posting.** Do not attach private recordings unless you have permission to share them.

## Set up a source checkout

Use Windows 10/11 and Python 3.12. From PowerShell:

```powershell
git clone https://github.com/ABhattacharya-dev/WaveType.git
cd WaveType
py -3.12 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Run `python desktop.py` for the app, `python stt.py` for the terminal client, or `python pill.py` for the standalone pill. First use downloads verified model and runtime files; subsequent inference runs locally. See the [README](README.md#run-from-source) for usage details and [architecture notes](docs/ARCHITECTURE.md) for the resident engine.

## Make a focused change

1. Fork the repository and create a descriptive branch from current `main`.
2. Keep one pull request focused on one problem. Include documentation when behavior or setup changes.
3. Keep model weights, recordings, personal dictionaries, history, logs, local credentials, build outputs, and generated benchmark artifacts out of the commit. Check `git status` and the staged diff before committing.
4. Preserve local-processing and privacy behavior. Explain any new network, data-storage, permission, or third-party dependency behavior in the pull request.
5. For UI changes, check keyboard use, readable text, the floating pill, tray behavior, and Windows 10/11 behavior where you can. State which combinations you actually tested.

## Check your work

Run the regression suite from the repository root:

```powershell
python -m unittest discover
```

For transcription or Smart cleanup changes, use a small replay and compare the raw/final output:

```powershell
python demo_engine.py path\to\clip.wav
python evaluate.py path\to\clip.wav --smart --tier auto --warmup
```

Replay expects mono 16-bit PCM WAV. Include hardware, sample length, run count, and warmup details with performance claims. For installer changes, follow the checks and limitations in [release documentation](docs/RELEASE.md); source tests alone do not validate an installer.

## Open a pull request

Open a [pull request against `main`](https://github.com/ABhattacharya-dev/WaveType/pulls) using the [pull request template](.github/PULL_REQUEST_TEMPLATE.md). Include:

- What problem the change solves and a link to its issue, if there is one.
- The approach and any user-visible behavior changes.
- Exact checks run and their results; name checks you could not run.
- Screenshots or a short recording for visible UI changes, with private data removed.
- Relevant Windows, CPU/GPU, and model/runtime details for platform-specific or performance changes.

Respond to review comments in the PR. If you update the branch, summarize what changed so reviewers can follow along.

## Local release workflow

- Make a separate local commit for each completed feature or fix, with its focused validation. Keep closely coupled changes together when splitting them would leave a broken intermediate state.
- Future commits must be cryptographically signed using an identity registered for signing on GitHub. After an authorized push, verify that GitHub reports the commits as Verified. Do not silently fall back to unsigned commits; if signing is not configured, keep changes uncommitted and explain what setup is needed. Do not rewrite existing published commits or release tags just to add signatures.
- Do not push commits to origin unless the user explicitly requests it.
- After each task, list the commits made during that task using their short hashes and titles, without descriptions. If no commits were made, say so.
- The current development version is `0.1.0-beta1.02`. Subsequent requested builds use `0.1.0-beta1.03`, `0.1.0-beta1.04`, and so on. Keep beta 1 until the user explicitly requests a new beta series; do not automatically change to beta 2 or beta 3.
- Keep version metadata, installer names and release documentation consistent. Previously published release links retain their original versions.
- Keep personal data, model downloads, signing credentials and generated build artifacts out of commits.
