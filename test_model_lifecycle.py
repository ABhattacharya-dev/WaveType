import os
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

import model_manager as mm
from model_files import remove_owned


class LifecycleTests(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name) / "runtime"
        self.root.mkdir()
        for owner, attr, value in ((mm.stt, "RUNTIME", self.root),
                                   (mm.smart, "RUNTIME", self.root),
                                   (mm.smart, "MODEL", self.root / "qwen.gguf")):
            patcher = patch.object(owner, attr, value)
            patcher.start()
            self.addCleanup(patcher.stop)
        self.events = []
        self.manager = mm.ModelDownloads(self.events.append)
        self.addCleanup(self.manager.close)

    def file(self, relative, data=b"test"):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return path

    def wait(self, name):
        self.manager.jobs[name].join(3)
        self.assertFalse(self.manager.jobs[name].is_alive())
        return self.manager.snapshot()[name]

    def test_delete_qwen_removes_cpu_gpu_and_partials_only(self):
        for name in ("qwen.gguf", "qwen.gguf.part", "smart/llama-server.exe",
                     "smart-cpu/llama-server.exe", "smart/.receipt.json",
                     mm.CPU[0], mm.GPU[0] + ".part", mm.CUDART[0],
                     "llama-b9999-bin-win-cpu-x64.zip.part"):
            self.file(name)
        preserved = [self.file(name) for name in ("redux-q8_0.gguf", "parakeet-cli.exe", "history/data.json")]
        release = Mock()
        self.manager.release = release
        self.manager.delete("cleanup")
        state = self.wait("cleanup")
        self.assertEqual(state["state"], "missing")
        self.assertEqual(state["disk_bytes"], 0)
        release.assert_called_once_with("cleanup")
        self.assertTrue(all(path.exists() for path in preserved))
        self.assertFalse(any(os.path.lexists(p) for p in self.manager.owned_paths("cleanup")))

    def test_asr_delete_survives_restart_without_auto_download(self):
        self.file("redux-q8_0.gguf")
        self.file("parakeet-lib/library.dll")
        cli = self.file("parakeet-cli.exe")
        qwen = self.file("qwen.gguf")
        self.manager.delete("asr")
        self.wait("asr")
        self.assertTrue(cli.exists())  # checked-in CLI is not a downloaded runtime
        self.assertTrue(qwen.exists())
        restarted = mm.ModelDownloads(self.events.append)
        with patch.object(mm, "ensure_asr") as download:
            restarted.startup("asr")
            restarted.jobs["asr"].join(2)
            restarted.close()
        download.assert_not_called()
        self.assertEqual(restarted.snapshot()["asr"]["state"], "missing")

    def test_pause_and_cancel_survive_restart(self):
        for intent in ("pause", "cancel"):
            self.manager.stop("asr", intent)
            restarted = mm.ModelDownloads(self.events.append)
            with patch.object(mm, "ensure_asr") as download:
                restarted.startup("asr")
                restarted.jobs["asr"].join(2)
            download.assert_not_called()
            self.assertEqual(restarted.intents["asr"], intent)

    def test_locked_file_failure_is_persistent_and_retryable(self):
        target = self.file("redux-q8_0.gguf")
        with patch.object(mm, "remove_owned", side_effect=PermissionError("File is in use")):
            self.manager.delete("asr")
            state = self.wait("asr")
        self.assertEqual(state["state"], "failed")
        self.assertTrue(state["installed"])
        self.assertTrue(target.exists())
        restarted = mm.ModelDownloads(self.events.append)
        restarted.startup("asr")
        restarted.jobs["asr"].join(2)
        self.assertIn("File is in use", restarted.snapshot()["asr"]["error"])
        self.manager.delete("asr")
        self.assertEqual(self.wait("asr")["state"], "missing")

    def test_delete_waits_for_worker_and_duplicate_clicks(self):
        started, finish = threading.Event(), threading.Event()
        def download(**kwargs):
            started.set()
            finish.wait(2)
            kwargs["control"]()
        with patch.object(mm, "ensure_asr", side_effect=download):
            self.manager.start("asr")
            self.assertTrue(started.wait(1))
            self.manager.delete("asr")
            deleting = self.manager.jobs["asr"]
            self.manager.delete("asr")
            self.manager.start("asr")
            self.assertIs(self.manager.jobs["asr"], deleting)
            self.assertEqual(self.manager.snapshot()["asr"]["state"], "deleting")
            finish.set()
            self.assertEqual(self.wait("asr")["state"], "missing")

    def test_linked_model_directory_is_not_followed(self):
        outside = self.root.parent / "outside"
        outside.mkdir()
        kept = outside / "keep.txt"
        kept.write_text("keep")
        link = self.root / "smart"
        try:
            link.symlink_to(outside, target_is_directory=True)
        except OSError:
            self.skipTest("Creating symbolic links is not permitted on this account")
        try:
            with self.assertRaisesRegex(OSError, "linked"):
                remove_owned(link, self.root)
            self.assertEqual(kept.read_text(), "keep")
        finally:
            link.unlink()

    def test_disk_usage_counts_selected_model_only(self):
        self.file("redux-q8_0.gguf", b"1234")
        self.file("parakeet-lib/library.dll", b"12")
        self.file("qwen.gguf", b"123456789")
        self.manager._set("asr", state="failed")
        self.assertEqual(self.manager.snapshot()["asr"]["disk_bytes"], 6)


class ControlTests(unittest.TestCase):
    def test_controls_for_each_model_state(self):
        from desktop import model_controls
        cases = [({}, ("download",)),
                 ({"state": "downloading"}, ("pause", "cancel")),
                 ({"state": "paused"}, ("resume", "cancel")),
                 ({"state": "failed", "partial": True}, ("resume", "cancel")),
                 ({"state": "ready"}, ("verify", "delete")),
                 ({"state": "failed", "installed": True}, ("verify", "delete")),
                 ({"state": "verifying", "operation": "verify"}, ()),
                 ({"state": "verifying", "operation": "repair"}, ("pause", "cancel")),
                 ({"state": "deleting"}, ()), ({"state": "pausing"}, ()),
                 ({"state": "canceling"}, ())]
        for state, expected in cases:
            with self.subTest(state=state):
                self.assertEqual(model_controls(state), expected)


if __name__ == "__main__":
    unittest.main()
