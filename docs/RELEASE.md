# Windows x64 releases

The first WaveType release is 0.1.0-beta.1, an unsigned public prerelease for Intel/AMD x64 Windows 10/11. It contains the desktop UI and a separate engine, including Python and the fallback Parakeet CLI. Models and optional llama.cpp runtimes download during setup or first use. No Python or CUDA Toolkit installation is required from the user.

The NSIS wizard includes welcome and privacy/notices pages, shortcut/startup/cleanup choices, an installation-directory picker, installation progress, and a finish page with launch and developer-page checkboxes. Startup, optional model download and the developer link are not preselected. Smart cleanup remains disabled until the user enables it in the app. The uninstaller uses a generated list of shipped files, retains local data, and leaves unrelated files in the chosen folder intact.

## Build

Create an x64 Python 3.12 virtual environment and install requirements-build.txt. Install NSIS 3. Run PowerShell with `powershell -ExecutionPolicy Bypass -File .\build.ps1 -Version 0.1.0-beta.1`.

The build uses PyInstaller folders with UPX disabled, version resources and the provided WaveType icon. Raw audio capture does not use NumPy; the engine build excludes NumPy and PyTorch. The metadata script checks the app and engine PE architecture, rejects personal/model data in the bundle, copies dependency notices, creates build-info.json and install-manifest.json, and emits the file-specific uninstaller list. NSIS compiler warnings are errors. Outputs are dist/WaveType-0.1.0-beta.1-Setup-x64.exe and dist/SHA256SUMS.txt. Neither binaries nor model files are committed to Git.

## Current validation status

This release pass includes source review, Python syntax compilation, Ruff checks, successful PyInstaller compilation, x64 PE verification, bundle privacy checks and NSIS compilation. Tests, app launch, model downloads through setup, installation/uninstallation and clean-VM checks were not run for this release pass, per the user's instruction. Earlier development builds had separate local checks; those do not validate this exact package.

No trusted signing certificate was available locally. Defender validation has not been performed, and no antivirus-pass claim is made. The GitHub release must be marked prerelease and explain those limitations. Installer size and its SHA-256 are published with the artifact.

## Signing and stable release

Use a publicly trusted code-signing identity, kept outside Git. Sign WaveType.exe, engine/WaveTypeEngine.exe and other owned executables with SHA-256 and a trusted timestamp before assembling the installer. Preserve any upstream signatures and notices. Regenerate the install manifest after signing, rebuild the installer, sign the final installer, then regenerate SHA256SUMS.txt. Verify signatures using signtool verify /pa /v. Self-signing is not a substitute for a trusted public publisher identity.

Before a stable release, validate clean Windows 10/11 systems with no Python or CUDA Toolkit, model-download failure/resume, GPU/CPU paths, microphone permissions, hotkeys, normal-app insertion, selected shortcuts/startup, upgrade and uninstall. Scan the exact final artifacts with current Defender protection and capture runtime network traffic to verify the documented privacy behavior. Never require users to disable antivirus or add exclusions. Investigate any detection; submit a confirmed false positive to Microsoft as a software developer.

Publish immutable artifacts, their checksums, source tag, version and honest validation status. The current app opens the GitHub releases page on demand; automatic update installation is not implemented. A future updater must verify the installer hash and trusted Authenticode signature before launching it.

WaveType project code is licensed under MIT (see LICENSE). Third-party notices remain in LICENSES.md and licenses/. Lordicon PRO redistribution still requires the asset owner's applicable rights. The published 0.1.0-beta.1 installer predates the project-license update; future installer builds include LICENSE with the bundled notices.
