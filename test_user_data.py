import json
import tempfile
import unittest
from pathlib import Path

from user_data import (dictionary_get, dictionary_set, history_append, history_audio,
                       history_change, history_list)


class UserDataTests(unittest.TestCase):
    def test_dictionary_round_trip_and_validation(self):
        with tempfile.TemporaryDirectory() as temporary:
            terms, vocabulary = (Path(temporary) / name for name in ("terms.json", "vocab.json"))
            dictionary_set(terms, vocabulary, "snippets", {"second email": "a@example.com"})
            dictionary_set(terms, vocabulary, "vocabulary", {"Parakeet": ["parakeet redox"]})
            self.assertEqual(dictionary_get(terms, vocabulary)["snippets"]["second email"], "a@example.com")
            with self.assertRaises(ValueError):
                dictionary_set(terms, vocabulary, "vocabulary", {"Parakeet": "wrong"})

    def test_history_undo_retry_delete_and_audio(self):
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            entry = history_append(directory, {"text": "Cleaned.", "raw": "insert my email",
                                               "plain": "a@example.com", "cleaned": "Cleaned."}, b"RIFFprobe")
            self.assertEqual(history_list(directory)[0]["id"], entry["id"])
            self.assertTrue(history_audio(directory, entry["id"])["base64"])
            self.assertEqual(history_change(directory, entry["id"], "undo")["text"], "a@example.com")
            self.assertEqual(history_change(directory, entry["id"], "retry", "Revised.")["text"], "Revised.")
            history_change(directory, entry["id"], "delete")
            self.assertEqual(history_list(directory), [])
            with self.assertRaises(FileNotFoundError):
                history_audio(directory, entry["id"])

    def test_old_history_stays_readable(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "2026-10-12.jsonl"
            path.write_text(json.dumps({"time": "12:00:00", "text": "Old entry."}) + "\n", encoding="utf-8")
            entry = history_list(temporary)[0]
            self.assertEqual(entry["raw"], "Old entry.")
            self.assertEqual(entry["date"], "2026-10-12")
            self.assertEqual(history_change(temporary, entry["id"], "undo")["text"], "Old entry.")


if __name__ == "__main__":
    unittest.main()
