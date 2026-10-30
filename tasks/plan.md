# Implementation plan: in-app updates

## Goal

Let installed WaveType users opt into automatic version checks and downloads, or check manually in Settings. Show download progress with Pause, Resume, and Cancel. Ask before installing a verified update, then close WaveType, run an express update, and reopen it. Keep ordinary setup unchanged.

## Decisions

- Use the public `ABhattacharya-dev/WaveType` GitHub Releases feed and the existing beta 1 version sequence. Ignore drafts, other platforms, and releases without the expected x64 installer plus a matching entry in `SHA256SUMS.txt`.
- Automatic checks and downloads are off by default. A manual check is a button with an in-flight guard and cooldown; it does not change the automatic setting.
- Keep update state under the existing local app data directory. Resume partial downloads with HTTP Range, verify the final SHA-256, and never run a partial or unverified installer.
- Add an NSIS update-only silent path that retains the current install directory and shortcut/startup choices. Normal setup keeps its current wizard.
- After approval, a detached helper waits for WaveType to exit, runs the installer, records failure if needed, and relaunches on success. The installer retains its existing file-in-use checks.
- Source runs can inspect releases, but express installation is available only from an installed packaged app.

## Ordered tasks and acceptance criteria

1. **Release discovery and verification**: compare beta versions, identify the correct installer and checksum, and reject malformed or older releases. Verify with focused unit tests.
2. **Download lifecycle**: implement one active download with progress, pause/resume/cancel, persisted partial state, and checksum verification. Verify interrupted transfer and bad checksum cases.
3. **Settings flow**: add automatic-update toggle, manual check with cooldown, status/progress controls, and approval prompt. Verify state and controls with focused tests and a Windows UI check where feasible.
4. **Express install handoff**: add an update-only NSIS path and detached helper to exit, install, and reopen safely. Verify installer compilation and an isolated installed-app upgrade if feasible.
5. **Documentation and regression**: describe network behavior, release asset requirements, install behavior, and limitations. Run the regression suite and build checks; close the issue with exact results.

## Checkpoints

- After tasks 1–2: release selection and download tests pass; no unverified installer can run.
- After tasks 3–4: update flow is wired end to end; normal installer flow remains available.
- After task 5: checks and release documentation match the implementation.

## Risks

- A silent installer could overwrite choices or race a running process. Preserve choices in update mode and let existing lock checks block mutation until processes exit.
- A release might lack the checksum asset. Show a clear error and do not install it.
- The current checkout contains unrelated uncommitted work. Stage only updater changes and do not rewrite those edits.
- Git commit signing was not configured initially. A dedicated SSH signing key is now registered with GitHub and local commits verify with the account email.

## Tracking

Tasks and completion evidence are tracked in [GitHub issue #22](https://github.com/ABhattacharya-dev/WaveType/issues/22); this file records the implementation order and decisions.

## Completion evidence

- The project Python environment passed 60 source tests, with one existing symlink test skipped.
- Release discovery and a complete checksum-verified installer download succeeded against the published beta 1.01 GitHub release.
- The PyInstaller and NSIS build completed, and the update-only installer rejected a path without an existing installation with exit code 2.
- The detached helper's failure reporting was exercised. A live installed upgrade on Windows 10/11 remains a release validation step.
