# App updates

Installed WaveType builds can check the public [GitHub Releases](https://github.com/ABhattacharya-dev/WaveType/releases) feed from Settings. **Check and download automatically** is off by default. When enabled, WaveType checks shortly after startup and no more than once per day while it runs. A manual **Check for updates** remains available; repeated checks are limited to one per minute. Source runs do not offer in-app updates.

Automatic mode downloads a newer beta 1 Windows x64 installer, then asks before installation. Manual mode asks before downloading and again before installation. Settings shows the download progress, with Pause, Resume, and Cancel. A paused partial download remains under `%LOCALAPPDATA%\STTCore\updates`; Cancel removes it. The updater checks the installer's SHA-256 against the matching `SHA256SUMS.txt` entry in the same release. Missing or mismatched checksums block installation. Only published releases in the existing `0.1.0-beta1.NN` series are selected.

Once approved, WaveType shuts down its engine, closes, runs the verified installer silently with its update-only option, and reopens. The update retains the installed location, current Start Menu and desktop shortcut choices, startup-on-sign-in choice, and all local models and personal data. The updater reports an installer failure on the next launch. The update-only option requires an existing installation; normal setup still shows the installation wizard.

Release maintainers must publish `WaveType-VERSION-Setup-x64.exe` and `SHA256SUMS.txt` together. The checksum file must contain the installer's exact filename and SHA-256. Release checks and installer downloads use HTTPS to GitHub. Dictation audio and text are not sent to GitHub. The installer is currently unsigned, so Windows may still show its usual publisher or SmartScreen warning; checksum verification does not replace code signing.

## Validation

Run `python -m unittest discover` and `powershell -ExecutionPolicy Bypass -File .\build.ps1` before release. Check an actual installed upgrade on Windows 10 and 11, including a non-default install location, disabled shortcuts, disabled startup, pause/resume, cancellation, failed checksum, and an interrupted update. A source test or a compiled installer alone does not prove the shutdown and relaunch path.
