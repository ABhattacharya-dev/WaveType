# Signing and updates

The current NSIS installer is an unsigned development artifact. Do not publish it as a trusted production download until an Authenticode certificate and a clean-VM installation test are available.

For a release, run the tests and `build.ps1`, then sign `WaveType.exe`, `engine/WaveTypeEngine.exe`, and `WaveType-Setup.exe` with SHA-256 and a trusted timestamp service. Verify each signature with `signtool verify /pa /v` before upload. Keep the certificate private key in a protected release environment, never in Git. Publish version, SHA-256, size, signature identity, and download URL in a release manifest over HTTPS. The future updater should check the manifest only when the user enables updates, verify the downloaded installer hash and Authenticode signature, then run the signed per-user installer after the UI exits. The model downloader already uses pinned SHA-256 and resumable downloads independently of app updates.

Release validation matrix: clean Windows 10 and 11, default and NVIDIA systems, first-run model download and restart, microphone, hotkey, normal-app insertion, uninstall without deleting history or personal files, and upgrade over a prior installer. Keep the full license notices in `LICENSES.md` and `licenses/` with every release.
