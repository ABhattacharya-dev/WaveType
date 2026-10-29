# Accessibility

WaveType is an early Windows 10/11 preview. We want people to be able to use it with different input methods and assistive technology. Accessibility testing is incomplete, and we do not currently claim conformance with an accessibility standard.

## Ways to use WaveType

- Hold **Ctrl+Win** to dictate, then release to insert text in the focused field. A quick tap locks recording; press the shortcut again to send. This avoids holding the keys throughout a longer dictation.
- The floating pill can start and stop locked recording with a pointer. The tray menu opens History, Dictionary, Settings, and About.
- The [terminal client](README.md#run-from-source) offers a text-based path for source users: run `python stt.py` and press Enter to start and stop recording.

These paths may behave differently with assistive technology or in elevated applications. See the [dictation instructions](README.md#how-to-dictate) for current behavior.

## Current limits and testing gaps

- The floating pill is a nonactivating canvas operated by pointer clicks. It is not a keyboard-focusable control, so use **Ctrl+Win** to dictate without clicking it.
- The main window has a fixed size. Keyboard navigation, screen reader output (including Narrator and NVDA), Windows contrast themes, and larger text or display scaling have not been fully verified.
- We have not published an accessibility audit or a list of supported assistive technology combinations. Please do not assume a particular combination works without testing it.

## Report a barrier

Use the [bug report form](https://github.com/ABhattacharya-dev/WaveType/issues/new/choose) for an accessibility problem. Include the WaveType version, Windows version, which view or control you used, your input method or assistive technology if relevant, steps to reproduce, and what you expected. Mention any workaround you found.

Remove dictated text, recordings, contact details, private file paths, and other personal data from screenshots or logs before posting. For a suspected security vulnerability, follow the [Security Policy](SECURITY.md) instead.

## Help improve accessibility

Accessibility fixes and testing reports are welcome. See the [Contributing guide](CONTRIBUTING.md) for setup, checks, and pull request guidance. For UI changes, describe keyboard and focus behavior and state which assistive technology, contrast, and scaling combinations you actually checked.
