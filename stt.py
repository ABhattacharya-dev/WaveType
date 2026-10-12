import argparse
import json
import re
import sys
from pathlib import Path

from smart import restore


RUNTIME = Path(__file__).resolve().parent / "runtime"
TERMS_FILE = RUNTIME.parent / "personal_terms.json"
HISTORY_DIR = RUNTIME.parent / "history"
SHORTCUT_START = re.compile(r"\binsert\s+my\s+", re.IGNORECASE)


def replace_shortcuts(text, protect=None, on_error=None):
    if not SHORTCUT_START.search(text):
        return text

    try:
        terms = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        terms = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError(f"Cannot read {TERMS_FILE.name}: {exc}") from exc

    if not isinstance(terms, dict):
        raise ValueError(f"{TERMS_FILE.name} must contain a JSON object.")

    shortcuts = {}
    for key, value in terms.items():
        normalized = " ".join(key.lower().split())
        if not normalized or normalized in shortcuts:
            raise ValueError(f"{TERMS_FILE.name} contains a blank or duplicate key: {key!r}")
        shortcuts[normalized] = value

    if not shortcuts:
        return text

    names = sorted(shortcuts, key=len, reverse=True)
    choices = "|".join(re.escape(name).replace(r"\ ", r"\s+") for name in names)
    # shortcut: A known key may match the start of an unknown longer phrase; require a spoken delimiter if that becomes a problem.
    shortcut = re.compile(r"\binsert\s+my\s+(" + choices + r")(?!\w)", re.IGNORECASE)
    missing = set()

    def replace(match):
        key = " ".join(match.group(1).lower().split())
        value = shortcuts[key]
        if not isinstance(value, str) or not value.strip():
            missing.add(key)
            return protect(match.group()) if protect else match.group()
        return protect(value) if protect else value

    result = shortcut.sub(replace, text)
    for key in sorted(missing):
        message = f"No saved value for {key} in {TERMS_FILE.name}."
        if on_error:
            on_error(message)
        else:
            print(message, file=sys.stderr)
    return result


def format_transcript(text, cleaner=None, on_error=None):
    if cleaner is None or not text.strip():
        return replace_shortcuts(text, on_error=on_error)
    values = {}

    def protect(value):
        index = len(values)
        marker = f"ZXQ{index}QXZ"
        while marker in text or marker in values:
            index += 1
            marker = f"ZXQ{index}QXZ"
        values[marker] = value
        return marker

    protected = replace_shortcuts(text, protect, on_error)
    try:
        return cleaner.clean(protected, values)
    except (OSError, ValueError, KeyError, IndexError, TypeError, RecursionError):
        if on_error:
            on_error("Smart cleanup failed; using original transcript.")
        else:
            print("Smart cleanup failed; using original transcript.", file=sys.stderr)
        return restore(protected, values)


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-raw", action="store_true", help="Show the raw transcript before cleanup; do not save it.")
    args = parser.parse_args(argv)
    enabled = input("Smart cleanup? [y/N]: ").strip().lower() == "y"
    from client import EngineClient
    client = EngineClient(start=True)
    try:
        try:
            client.command("settings", mode="hold", smart=enabled)
        except RuntimeError as exc:
            if not enabled:
                raise
            print(f"Smart cleanup unavailable: {exc}", file=sys.stderr)
            client.command("settings", mode="hold", smart=False)
        client.command("subscribe")
        input("Press Enter to record...")
        client.command("start")
        input("Recording. Press Enter to stop...")
        client.command("release")
        for event in client.events():
            if event["event"] == "result":
                if args.show_raw:
                    print(f"Raw transcript: {event['raw']}", file=sys.stderr, flush=True)
                print(event["text"], flush=True)
                break
            if event["event"] == "error":
                print(event["message"], file=sys.stderr)
    finally:
        client.close()


if __name__ == "__main__":
    main()
