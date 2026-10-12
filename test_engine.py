import io
import json
import tempfile
import time
import unittest
import wave
from pathlib import Path
from unittest.mock import Mock, patch

import engine
from vocabulary import apply_vocabulary


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.asr = Mock()
        self.asr.transcribe.return_value = "Hello there."
        self.job = patch.object(engine, "ChildJob")
        self.models = patch("model_manager.ensure_asr")
        self.job.start()
        self.models.start()
        self.core = engine.DictationEngine(asr=self.asr, capture=False)

    def tearDown(self):
        self.core.close()
        self.models.stop()
        self.job.stop()

    def test_hold_tap_cancel_and_result(self):
        events = []
        self.core.listeners.add(events.append)
        self.assertEqual(self.core.command("start", {})["state"], "recording")
        self.assertEqual(self.core.command("cancel", {})["state"], "idle")
        self.core.command("settings", {"mode": "tap"})
        self.assertEqual(self.core.command("press", {})["state"], "locked")
        self.assertEqual(self.core.command("release", {})["state"], "locked")
        self.core.command("cancel", {})
        with tempfile.TemporaryDirectory() as directory:
            clip = Path(directory) / "speech.wav"
            clip.write_bytes(engine.wav_bytes(b"\0\0" * 16000))
            self.core.command("replay", {"path": str(clip)})
            self.core.command("press", {})
            deadline = time.monotonic() + 3
            while not any(x["event"] == "result" for x in events) and time.monotonic() < deadline:
                time.sleep(0.01)
        self.assertEqual([x for x in events if x["event"] == "result"][0]["text"], "Hello there.")
        self.assertEqual(self.core.state, "idle")

    def test_guards(self):
        self.assertTrue(engine.cleanup_needed("meet at six sorry seven"))
        self.assertFalse(engine.cleanup_needed("Good morning everyone."))
        self.assertFalse(engine.meaning_guard("Tomorrow.", "To my house."))
        self.assertFalse(engine.meaning_guard("Meet at 8.", "Meet at 9."))

    def test_vocabulary_aliases(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "vocabulary.json"
            path.write_text(json.dumps({"Parakeet Redux": ["parakeet redox"]}), encoding="utf-8")
            self.assertEqual(apply_vocabulary("Use parakeet redox.", path), "Use Parakeet Redux.")


if __name__ == "__main__":
    unittest.main()
