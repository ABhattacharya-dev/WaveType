import io
import json
import tempfile
import unittest
from contextlib import nullcontext, redirect_stderr
from pathlib import Path
from unittest.mock import Mock, patch

import smart
import stt


class SmartTests(unittest.TestCase):
    def test_shortcuts_and_fallback(self):
        with tempfile.TemporaryDirectory() as directory:
            terms = Path(directory) / "terms.json"
            terms.write_text(json.dumps({"second email": "ab@example.com"}), encoding="utf-8")
            with patch.object(stt, "TERMS_FILE", terms):
                original = "Insert my second email, that's my name."
                expected = "ab@example.com, that's my name."
                self.assertEqual(stt.format_transcript(original), expected)
                cleaner = Mock()
                cleaner.clean.side_effect = lambda text, values: smart.validate_output(text, values)
                self.assertEqual(stt.format_transcript(original, cleaner), expected)
                for error in (TimeoutError(), ValueError(), KeyError()):
                    cleaner.clean.side_effect = error
                    with redirect_stderr(io.StringIO()):
                        self.assertEqual(stt.format_transcript(original, cleaner), expected)
                terms.write_text('{"email":""}', encoding="utf-8")
                cleaner.clean.side_effect = lambda text, values: smart.validate_output(text, values)
                with redirect_stderr(io.StringIO()):
                    self.assertEqual(stt.format_transcript("Insert my email.", cleaner), "Insert my email.")

    def test_json_escaping_and_placeholders(self):
        self.assertEqual(smart.restore("ZXQ0QXZ ZXQ1QXZ", {"ZXQ0QXZ": "ZXQ1QXZ", "ZXQ1QXZ": "AB"}), "ZXQ1QXZ AB")
        marker = "ZXQabcdef_0QXZ"
        values = {marker: 'AB "Example"\nStreet'}
        output = smart.validate_output(json.dumps({"user": {"name": marker}, "active": True}), values, True)
        self.assertEqual(json.loads(output), {"user": {"name": values[marker]}, "active": True})
        for bad in ("missing", marker + marker, marker + "ZXQabcdef_1QXZ", marker + "ZXQ123QXZ"):
            with self.assertRaises(ValueError):
                smart.validate_output(bad, values)
        for bad in ('{"x":1,"x":2}', '{"x":NaN}', '{"x":', json.dumps({marker: "value"})):
            with self.assertRaises(ValueError):
                smart.validate_output(bad, values if marker in bad else {}, True)

    def test_limits_and_json_activation(self):
        cleaner = smart.SmartCleanup()
        cleaner.request = Mock(return_value={"choices": [{"finish_reason": "stop", "message": {"content": "{}"}}]})
        cleaner.clean("Write in JSON format, key name value AB", {})
        self.assertIn("response_format", cleaner.request.call_args.args[1])
        cleaner.clean("Please explain write in JSON format.", {})
        self.assertNotIn("response_format", cleaner.request.call_args.args[1])
        cleaner.request.reset_mock()
        with self.assertRaises(ValueError):
            cleaner.clean("a" * 4000, {})
        cleaner.request.assert_not_called()
        cleaner.request.return_value["choices"][0]["finish_reason"] = "length"
        with self.assertRaises(ValueError):
            cleaner.clean("Hello", {})

    def test_session_lifecycle(self):
        with patch.object(smart, "SmartCleanup") as factory:
            with smart.smart_session(False) as cleaner:
                self.assertIsNone(cleaner)
            factory.assert_not_called()
            with self.assertRaises(KeyboardInterrupt):
                with smart.smart_session(True):
                    raise KeyboardInterrupt
            factory.return_value.close.assert_called_once()
        with patch.object(smart, "SmartCleanup") as factory, redirect_stderr(io.StringIO()):
            factory.return_value.start.side_effect = OSError("missing")
            with smart.smart_session(True) as cleaner:
                self.assertIsNone(cleaner)
            factory.return_value.close.assert_called_once()

    def test_repeated_shortcuts(self):
        with tempfile.TemporaryDirectory() as directory:
            terms = Path(directory) / "terms.json"
            terms.write_text('{"name": "AB"}', encoding="utf-8")
            cleaner = Mock()
            cleaner.clean.side_effect = lambda text, values: smart.validate_output(text, values)
            with patch.object(stt, "TERMS_FILE", terms):
                self.assertEqual(stt.format_transcript("Insert my name, insert my name.", cleaner), "AB, AB.")
                self.assertEqual(stt.format_transcript("My name, that's my name.", cleaner), "My name, that's my name.")

    def test_main_saves_only_final(self):
        with (
            patch("builtins.input", return_value="n"),
            patch.object(stt, "smart_session", return_value=nullcontext(None)) as session,
            patch.object(stt, "transcribe", return_value="Hello."),
            patch.object(stt, "save_history") as save,
            patch("builtins.print"),
        ):
            stt.main([])
            session.assert_called_once_with(False)
            save.assert_called_once_with("Hello.")

    def test_show_raw_keeps_only_final_history(self):
        with (
            patch("builtins.input", return_value="y"),
            patch.object(stt, "smart_session", return_value=nullcontext(Mock())),
            patch.object(stt, "transcribe", return_value="Today, no tomorrow."),
            patch.object(stt, "format_transcript", return_value="Tomorrow."),
            patch.object(stt, "save_history") as save,
            patch("builtins.print") as output,
        ):
            stt.main(["--show-raw"])
            output.assert_any_call("Raw transcript: Today, no tomorrow.", file=stt.sys.stderr, flush=True)
            save.assert_called_once_with("Tomorrow.")


if __name__ == "__main__":
    unittest.main()
