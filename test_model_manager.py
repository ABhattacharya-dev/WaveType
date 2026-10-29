import hashlib
import tempfile
import threading
import unittest
import urllib.error
import zipfile
from pathlib import Path
from unittest.mock import Mock, patch

import model_manager


class Response:
    def __init__(self, content, status=200, headers=None):
        self.content = content
        self.status = status
        self.headers = headers or {"Content-Length": str(len(content))}
        self.position = 0

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        pass

    def read(self, size):
        chunk = self.content[self.position:self.position + size]
        self.position += len(chunk)
        return chunk


class DownloadTests(unittest.TestCase):
    def setUp(self):
        # Every test owns its intent file; no tests write to a developer's runtime.
        self.intent_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.intent_dir.cleanup)
        original = model_manager.ModelDownloads.__init__
        def isolated(manager, *args, **kwargs):
            original(manager, *args, **kwargs)
            manager.intent_path = Path(self.intent_dir.name) / "intent.json"
            manager.intents = {}
        patcher = patch.object(model_manager.ModelDownloads, "__init__", isolated)
        patcher.start()
        self.addCleanup(patcher.stop)

    def test_ignored_range_restarts_instead_of_appending(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "redux-q8_0.gguf"
            target.with_name(target.name + ".part").write_bytes(b"old")
            with patch("urllib.request.urlopen", return_value=Response(b"model")) as open_url:
                model_manager.fetch(target, "https://example.test/model", hashlib.sha256(b"model").hexdigest())
            self.assertEqual(open_url.call_args.args[0].headers["Range"], "bytes=3-")
            self.assertEqual(target.read_bytes(), b"model")

    def test_range_not_satisfiable_restarts_once(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "model.gguf"
            target.with_name(target.name + ".part").write_bytes(b"stale")
            failure = urllib.error.HTTPError("url", 416, "range", {}, None)
            with patch("urllib.request.urlopen", side_effect=[failure, Response(b"good")]) as open_url:
                model_manager.fetch(target, "https://example.test/model", hashlib.sha256(b"good").hexdigest())
            self.assertEqual(open_url.call_count, 2)
            self.assertEqual(target.read_bytes(), b"good")

    def test_pause_keeps_partial_and_cancel_removes_it(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "redux-q8_0.gguf"
            checks = 0

            def pause():
                nonlocal checks
                checks += 1
                if checks == 2:
                    raise model_manager.DownloadStopped("pause")

            with patch("urllib.request.urlopen", return_value=Response(b"model")):
                with self.assertRaises(model_manager.DownloadStopped):
                    model_manager.fetch(target, "https://example.test/model", "unused", control=pause)
            self.assertEqual(target.with_name(target.name + ".part").read_bytes(), b"model")

            with patch.object(model_manager.stt, "RUNTIME", Path(folder)):
                manager = model_manager.ModelDownloads(lambda _event: None)
                manager.states["asr"]["state"] = "paused"
                manager.stop("asr", "cancel")
                self.assertEqual(manager.snapshot()["asr"]["state"], "missing")
            self.assertFalse(target.with_name(target.name + ".part").exists())

    def test_low_disk_space_keeps_partial_for_retry(self):
        with tempfile.TemporaryDirectory() as folder:
            target = Path(folder) / "model.gguf"
            with (patch("urllib.request.urlopen", return_value=Response(b"model")),
                  patch.object(model_manager.shutil, "disk_usage", return_value=Mock(free=1))):
                with self.assertRaisesRegex(OSError, "Not enough free disk space"):
                    model_manager.fetch(target, "https://example.test/model", "unused")
            self.assertFalse(target.exists())

    def test_incomplete_extraction_is_not_ready(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            archive = root / "runtime.zip"
            destination = root / "runtime"
            with zipfile.ZipFile(archive, "w") as contents:
                contents.writestr("bin/llama-server.exe", b"verified runtime")
            model_manager._extract(archive, destination)
            self.assertTrue(model_manager._package_ready(destination, archive.name))
            (destination / "bin" / "llama-server.exe").write_bytes(b"damaged")
            self.assertFalse(model_manager._package_ready(destination, archive.name))
            model_manager._extract(archive, destination)
            with self.assertRaises(model_manager.DownloadStopped):
                model_manager._extract(archive, destination,
                                       control=lambda: (_ for _ in ()).throw(model_manager.DownloadStopped("pause")))
            self.assertFalse(model_manager._package_ready(destination, archive.name))

    def test_existing_parakeet_library_uses_pinned_file_hash(self):
        with tempfile.TemporaryDirectory() as folder:
            library = Path(folder) / "parakeet.dll"
            library.write_bytes(b"original")
            with (patch.object(model_manager, "ASR_LIBRARY_PATH", library),
                  patch.object(model_manager, "ASR_LIBRARY_DLL_SHA256",
                               hashlib.sha256(b"original").hexdigest())):
                self.assertTrue(model_manager.asr_library_ready())
                library.write_bytes(b"corrupt")
                self.assertFalse(model_manager.asr_library_ready())

    def test_previous_qwen_runtime_works_offline_until_repair(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            model = root / "qwen.gguf"
            model.write_bytes(b"qwen")
            executable = root / "smart-cpu" / "llama-server.exe"
            executable.parent.mkdir()
            executable.write_bytes(b"previous runtime")
            with (patch.object(model_manager.smart, "RUNTIME", root),
                  patch.object(model_manager.smart, "MODEL", model),
                  patch.object(model_manager, "CLEANUP", ("unused", hashlib.sha256(b"qwen").hexdigest())),
                  patch.object(model_manager, "gpu_available", return_value=False),
                  patch("urllib.request.urlopen") as open_url):
                manager = model_manager.ModelDownloads(lambda _event: None)
                self.assertTrue(manager._ready("cleanup"))
                self.assertTrue(manager._legacy("cleanup"))
                self.assertEqual(model_manager.ensure_cleanup(require_memory=False)[0], executable)
                open_url.assert_not_called()

    def test_independent_jobs_and_duplicate_start(self):
        started = threading.Event()
        release = threading.Event()
        notices = []
        manager = model_manager.ModelDownloads(notices.append)

        def download(**_kwargs):
            started.set()
            release.wait(2)

        asr_checks = 0

        def ready(name):
            nonlocal asr_checks
            if name == "cleanup":
                return False
            asr_checks += 1
            return asr_checks == 2

        with (patch.object(manager, "_ready", side_effect=ready),
              patch.object(model_manager, "ensure_asr", side_effect=download) as asr):
            manager.start("asr")
            self.assertTrue(started.wait(1))
            manager.start("asr")
            manager.start("cleanup", download=False)
            release.set()
            manager.jobs["asr"].join(2)
            manager.jobs["cleanup"].join(2)
        self.assertEqual(asr.call_count, 1)
        self.assertEqual(manager.snapshot()["asr"]["state"], "ready")
        self.assertEqual(manager.snapshot()["cleanup"]["state"], "missing")
        self.assertTrue(any(event["state"] == "ready" for event in notices))


if __name__ == "__main__":
    unittest.main()
