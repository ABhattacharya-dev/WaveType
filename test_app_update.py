"""Installer discovery and transfer checks without network access."""

import hashlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

from app_update import UpdateManager, checksum_for, select_release, version_key


class Response(io.BytesIO):
    def __init__(self, data, status=200, headers=None):
        super().__init__(data)
        self.status = status
        self.headers = headers or {}


class UpdateTests(unittest.TestCase):
    def test_selects_newest_valid_beta_with_both_assets(self):
        def release(version, assets):
            return {"tag_name": version, "draft": False, "assets": assets}

        def asset(name):
            return {"name": name, "size": 10, "browser_download_url": "https://github.com/ABhattacharya-dev/WaveType/releases/download/test/" + name}

        releases = [release("v0.1.0-beta1.03", [asset("WaveType-0.1.0-beta1.03-Setup-x64.exe"), asset("SHA256SUMS.txt")]),
                    release("v0.1.0-beta1.03.1", [asset("WaveType-0.1.0-beta1.03.1-Setup-x64.exe"), asset("SHA256SUMS.txt")]),
                    release("v0.1.0-beta1.04", [asset("WaveType-0.1.0-beta1.04-Setup-x64.exe"), asset("SHA256SUMS.txt")]),
                    release("v0.1.0-beta1.05", [asset("WaveType-0.1.0-beta1.05-Setup-x64.exe")]),
                    release("v0.1.0-beta2.01", [asset("WaveType-0.1.0-beta2.01-Setup-x64.exe"), asset("SHA256SUMS.txt")])]
        self.assertEqual(select_release(releases, "0.1.0-beta1.02")["version"], "0.1.0-beta1.04")
        self.assertEqual(select_release(releases, "0.1.0-beta1.03")["version"], "0.1.0-beta1.04")
        self.assertEqual(select_release(releases, "0.1.0-beta1.03.1")["version"], "0.1.0-beta1.04")
        self.assertIsNone(select_release(releases, "0.1.0-beta1.04"))
        self.assertEqual(version_key("v0.1.0-beta1.12"), (0, 1, 0, 12, 0))
        self.assertEqual(version_key("v0.1.0-beta1.03.1"), (0, 1, 0, 3, 1))
        self.assertLess(version_key("0.1.0-beta1.03.1"), version_key("0.1.0-beta1.04"))

    def test_checksum_must_name_the_exact_installer(self):
        digest = "a" * 64
        self.assertEqual(checksum_for(f"{digest}  WaveType.exe", "WaveType.exe"), digest)
        with self.assertRaises(ValueError):
            checksum_for(f"{digest}  another.exe", "WaveType.exe")

    def test_resumes_partial_download_and_verifies_before_ready(self):
        data = b"example installer bytes"
        name = "WaveType-0.1.0-beta1.03-Setup-x64.exe"
        with tempfile.TemporaryDirectory() as temporary:
            requests = []

            def opener(request, timeout):
                requests.append(request)
                self.assertEqual(request.get_header("Range"), "bytes=7-")
                return Response(data[7:], 206, {"Content-Range": f"bytes 7-{len(data)-1}/{len(data)}"})

            manager = UpdateManager(temporary, "0.1.0-beta1.02", opener)
            manager.release = {"version": "0.1.0-beta1.03", "installer": {
                "name": name, "size": len(data),
                "browser_download_url": "https://github.com/ABhattacharya-dev/WaveType/releases/download/test/" + name}}
            manager.expected_hash = hashlib.sha256(data).hexdigest()
            manager.directory.mkdir()
            (manager.directory / (name + ".part")).write_bytes(data[:7])
            manager._download()
            self.assertEqual(manager.state, "ready")
            self.assertEqual(manager.ready_installer().read_bytes(), data)
            self.assertEqual(len(requests), 1)

    def test_bad_checksum_never_exposes_installer(self):
        data = b"corrupt"
        name = "WaveType-0.1.0-beta1.03-Setup-x64.exe"
        with tempfile.TemporaryDirectory() as temporary:
            manager = UpdateManager(temporary, "0.1.0-beta1.02", lambda request, timeout: Response(data))
            manager.release = {"version": "0.1.0-beta1.03", "installer": {
                "name": name, "size": len(data),
                "browser_download_url": "https://github.com/ABhattacharya-dev/WaveType/releases/download/test/" + name}}
            manager.expected_hash = "0" * 64
            manager._download()
            self.assertEqual(manager.state, "error")
            self.assertIsNone(manager.ready_installer())
            self.assertFalse((Path(temporary) / "updates" / name).exists())

    @unittest.skipUnless(os.name == "nt", "Windows desktop handoff")
    def test_install_handoff_runs_helper_outside_install_directory(self):
        import desktop

        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            package = root / "installed"
            package.mkdir()
            (package / "Uninstall.exe").write_bytes(b"installer")
            installer = root / "update.exe"
            installer.write_bytes(b"download")
            data = root / "data"
            data.mkdir()
            app = desktop.DesktopApp.__new__(desktop.DesktopApp)
            app.updates = SimpleNamespace(ready_installer=lambda: installer, expected_hash="0" * 64)
            app.report = Mock()
            app.quit = Mock()
            with patch.object(desktop, "APP_DIR", data), \
                    patch.object(desktop.sys, "executable", str(package / "WaveType.exe")), \
                    patch.object(desktop.subprocess, "Popen") as launch:
                app.install_update(approved=True)
            self.assertEqual((data / "update-helper.ps1").read_bytes(),
                             (Path(desktop.__file__).parent / "packaging" / "update_helper.ps1").read_bytes())
            self.assertIn(str(data / "update-helper.ps1"), launch.call_args.args[0])
            self.assertEqual(launch.call_args.kwargs["creationflags"], subprocess.CREATE_NO_WINDOW)
            app.quit.assert_called_once()

    @unittest.skipUnless(os.name == "nt", "Windows update helper")
    def test_windowless_helper_records_hash_failure(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer = root / "update.exe"
            installer.write_bytes(b"changed after download")
            result = root / "result.json"
            helper = Path(__file__).parent / "packaging" / "update_helper.ps1"
            powershell = Path(os.environ.get("SystemRoot", r"C:\Windows")) / "System32" / \
                "WindowsPowerShell" / "v1.0" / "powershell.exe"
            process = subprocess.Popen(
                [str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
                 "-File", str(helper), "-Installer", str(installer), "-InstallDir", str(root),
                 "-AppPid", "999999", "-ExpectedSha256", "0" * 64, "-ResultFile", str(result)],
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )
            self.assertEqual(process.wait(timeout=15), 0)
            self.assertEqual(json.loads(result.read_text(encoding="utf-8-sig")), {
                "status": "failed",
                "message": "The downloaded installer changed after verification. The update was not installed.",
            })


if __name__ == "__main__":
    unittest.main()
