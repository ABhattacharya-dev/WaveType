import json
import tempfile
import unittest
from pathlib import Path

from user_data import (dictionary_get, dictionary_set, history_append,
                       history_change, history_compact, history_list)


class UserDataTests(unittest.TestCase):
    def test_dictionary_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            terms, vocabulary = (Path(temporary) / name for name in ("terms.json", "vocab.json"))
            dictionary_set(terms, vocabulary, "snippets", {"second email": "a@example.com"})
            dictionary_set(terms, vocabulary, "vocabulary", {"Parakeet": ["parakeet redox"]})
            self.assertEqual(dictionary_get(terms, vocabulary)["snippets"]["second email"], "a@example.com")
            with self.assertRaises(ValueError):
                dictionary_set(terms, vocabulary, "vocabulary", {"Parakeet": "wrong"})
            with self.assertRaises(ValueError):
                dictionary_set(terms, vocabulary, "vocabulary",
                               {"Parakeet": ["same"], "Redux": ["same"]})

    def test_history_stores_only_displayed_fields_and_deletes(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry = history_append(directory, {"text": "Cleaned.", "app": "ChatGPT.exe",
                                               "raw": "insert my email", "timings": {"asr_ms": 1}})
            self.assertEqual(history_list(directory)[0]["id"], entry["id"])
            stored = json.loads(next(directory.glob("*.jsonl")).read_text())
            self.assertEqual(set(stored), {"date", "time", "text", "app"})
            self.assertEqual(stored["app"], "ChatGPT.exe")
            with self.assertRaises(ValueError):
                history_change(directory, entry["id"], "undo")
            history_change(directory, entry["id"], "delete")
            self.assertEqual(history_list(directory), [])

    def test_old_history_compacts_and_removes_generated_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "2026-10-12.jsonl"
            path.write_text(json.dumps({"id": "a" * 32, "time": "12:00:00", "text": "Old entry.",
                                        "raw": "Old entry", "app": {"process": "Notepad.exe",
                                                                         "title": "Private"}}) + "\n", encoding="utf-8")
            audio = Path(temporary) / "audio"
            audio.mkdir()
            (audio / ("a" * 32 + ".wav")).write_bytes(b"RIFFprobe")
            (audio / "keep.wav").write_bytes(b"user file")
            entry = history_list(temporary)[0]
            self.assertEqual(entry["date"], "2026-10-12")
            self.assertEqual(entry["app"], "Notepad.exe")
            history_compact(temporary)
            self.assertEqual(set(json.loads(path.read_text())), {"date", "time", "text", "app"})
            self.assertFalse((audio / ("a" * 32 + ".wav")).exists())
            self.assertTrue((audio / "keep.wav").exists())
            self.assertEqual(history_list(temporary)[0]["text"], "Old entry.")

    def test_delete_middle_history_row_keeps_others(self):
        with tempfile.TemporaryDirectory() as temporary:
            history_append(temporary, {"text": "First", "app": "A.exe"})
            middle = history_append(temporary, {"text": "Middle", "app": "B.exe"})
            history_append(temporary, {"text": "Last", "app": "C.exe"})
            history_change(temporary, middle["id"], "delete")
            self.assertEqual([row["text"] for row in history_list(temporary)], ["Last", "First"])


if __name__ == "__main__":
    unittest.main()
