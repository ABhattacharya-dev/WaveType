# Working on WaveType

- Make a separate local commit for each completed feature or fix, with its focused validation. Keep closely coupled changes together when splitting them would leave a broken intermediate state.
- Do not push commits to origin unless the user explicitly requests it.
- The current development version is `0.1.0-beta1.01`. Subsequent requested builds use `0.1.0-beta1.02`, `0.1.0-beta1.03`, and so on. Keep beta 1 until the user explicitly requests a new beta series; do not automatically change to beta 2 or beta 3.
- Keep version metadata, installer names and release documentation consistent. Previously published release links retain their original versions.
- Keep personal data, model downloads, signing credentials and generated build artifacts out of commits.
