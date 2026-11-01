# First-run Parakeet recovery

WaveType checks the Parakeet model weights, runtime CLI, and runtime DLL separately. Open **Settings → Parakeet Redux** to see which part needs attention.

- **Model missing or failed verification:** Select **Download**, **Retry download**, or **Verify / repair**, whichever Settings shows. A partial download can be resumed; WaveType verifies the complete file against its pinned SHA-256 before use.
- **Runtime DLL missing or invalid:** Select **Verify / repair**. Beta1.04 restores the pinned DLL from the installer without another download. Beta1.03.1 and older builds fetch and verify the pinned runtime ZIP from GitHub.
- **Runtime download failed:** Keep WaveType open, check your connection, then select **Verify / repair**. The error names the runtime rather than the model.
- **Certificate verification failed:** Check the Windows date and time and make sure Windows trusted roots and any organization-managed proxy certificate are current. Then select **Verify / repair**. A certificate-chain failure may have several causes; WaveType does not disable TLS checks. If it persists, report the exact error and Windows version without sharing dictated text or model files.

Once both model and runtime are verified, Settings shows **Ready and verified**. WaveType can then start Parakeet without a network connection. If the bundled DLL itself fails verification, reinstall WaveType from its published release before retrying; the installed application files may be damaged.
