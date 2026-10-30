"""Installer discovery and transfer checks without network access."""

import hashlib
import io
import tempfile
import unittest
from pathlib import Path

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
                    release("v0.1.0-beta1.04", [asset("WaveType-0.1.0-beta1.04-Setup-x64.exe")]),
                    release("v0.1.0-beta2.01", [asset("WaveType-0.1.0-beta2.01-Setup-x64.exe"), asset("SHA256SUMS.txt")])]
        self.assertEqual(select_release(releases, "0.1.0-beta1.02")["version"], "0.1.0-beta1.03")
        self.assertIsNone(select_release(releases, "0.1.0-beta1.03"))
        self.assertEqual(version_key("v0.1.0-beta1.12"), (0, 1, 0, 12))

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


if __name__ == "__main__":
    unittest.main()
