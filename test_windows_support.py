"""Text insertion boundaries, including Notepad's clipboard-safe path."""

import ctypes
import os
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, call, patch

import windows_support as support


@unittest.skipUnless(os.name == "nt", "Windows input only")
class TextInsertionTests(unittest.TestCase):
    def test_notepad_paste_restores_every_saved_clipboard_format(self):
        saved = [(13, b"old text\0\0"), (49152, b"custom")]
        fake = SimpleNamespace(RegisterClipboardFormatW=lambda _name: 49153,
                               GetClipboardSequenceNumber=lambda: 7,
                               SendInput=lambda count, _items, _size: count)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support, "_clipboard_snapshot", return_value=(saved, 7)),
              patch.object(support, "_clipboard_set") as set_clipboard,
              patch.object(support.time, "sleep")):
            support._paste_notepad("Ada 🌍", 123)
        self.assertEqual(set_clipboard.call_count, 2)
        self.assertEqual(set_clipboard.call_args_list[0].args[0], 123)
        self.assertEqual(set_clipboard.call_args_list[0].args[1][0],
                         (13, "Ada 🌍".encode("utf-16-le") + b"\0\0"))
        self.assertEqual(set_clipboard.call_args_list[0].args[1][1], (49153, b"\0\0\0\0"))
        self.assertEqual(set_clipboard.call_args_list[1], call(123, saved))

    def test_focus_change_restores_clipboard_without_pasting(self):
        send = Mock(return_value=4)
        fake = SimpleNamespace(RegisterClipboardFormatW=lambda _name: 49153,
                               GetClipboardSequenceNumber=lambda: 7, SendInput=send)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", side_effect=[123, 456]),
              patch.object(support, "_clipboard_snapshot", return_value=([], 7)),
              patch.object(support, "_clipboard_set") as set_clipboard):
            with self.assertRaisesRegex(OSError, "focused window changed"):
                support._paste_notepad("text", 123)
        self.assertEqual(set_clipboard.call_count, 2)
        send.assert_not_called()

    def test_new_user_clipboard_content_is_not_overwritten(self):
        send = Mock(return_value=4)
        values = iter((7, 7, 8, 8))
        fake = SimpleNamespace(RegisterClipboardFormatW=lambda _name: 49153,
                               GetClipboardSequenceNumber=lambda: next(values), SendInput=send)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support, "_clipboard_snapshot", return_value=([], 7)),
              patch.object(support, "_clipboard_set") as set_clipboard):
            with self.assertRaisesRegex(OSError, "Clipboard changed"):
                support._paste_notepad("text", 123)
        self.assertEqual(set_clipboard.call_count, 1)
        send.assert_not_called()

    def test_notepad_uses_paste_after_modifier_release(self):
        fake = SimpleNamespace(GetAsyncKeyState=lambda _key: 0)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support, "foreground_app", return_value={"process": "Notepad.exe"}),
              patch.object(support, "_paste_notepad") as paste):
            support.insert_text("Ada", 123)
        paste.assert_called_once_with("Ada", 123)

    def test_other_apps_keep_unicode_input_including_surrogate_pairs(self):
        captured = []

        def send(count, pointer, _size):
            items = ctypes.cast(pointer, ctypes.POINTER(support.INPUT))
            captured.extend((items[i].ki.wScan, items[i].ki.dwFlags) for i in range(count))
            return count

        fake = SimpleNamespace(GetAsyncKeyState=lambda _key: 0, SendInput=send)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support, "foreground_app", return_value={"process": "chrome.exe"}),
              patch.object(support, "_paste_notepad") as paste):
            support.insert_text("A🌍", 123)
        self.assertEqual(captured, [(65, 4), (65, 6), (0xD83C, 4), (0xD83C, 6),
                                    (0xDF0D, 4), (0xDF0D, 6)])
        paste.assert_not_called()

    def test_unknown_foreground_process_keeps_unicode_input(self):
        fake = SimpleNamespace(GetAsyncKeyState=lambda _key: 0,
                               SendInput=lambda count, _items, _size: count)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support, "foreground_app", return_value={"process": None}),
              patch.object(support, "_paste_notepad") as paste):
            support.insert_text("hello", 123)
        paste.assert_not_called()

    def test_held_modifier_prevents_insertion(self):
        fake = SimpleNamespace(GetAsyncKeyState=lambda _key: 0x8000)
        with (patch.object(support, "user32", fake),
              patch.object(support, "foreground_window", return_value=123),
              patch.object(support.time, "monotonic", side_effect=[0, 1]),
              patch.object(support, "_paste_notepad") as paste):
            with self.assertRaisesRegex(OSError, "release modifier keys"):
                support.insert_text("text", 123)
        paste.assert_not_called()

    def test_unsupported_clipboard_format_is_left_untouched(self):
        close = Mock()
        fake = SimpleNamespace(OpenClipboard=lambda _window: True,
                               GetClipboardSequenceNumber=lambda: 7,
                               EnumClipboardFormats=lambda _current: 2,
                               CloseClipboard=close)
        with patch.object(support, "user32", fake):
            with self.assertRaisesRegex(OSError, "cannot preserve"):
                support._clipboard_snapshot()
        close.assert_called_once_with()


if __name__ == "__main__":
    unittest.main()
