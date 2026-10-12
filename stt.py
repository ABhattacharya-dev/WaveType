import argparse
import io
import json
import re
import subprocess
import sys
import wave
from datetime import datetime
from pathlib import Path

import sounddevice as sd

from smart import restore, smart_session


RUNTIME = Path(__file__).resolve().parent / "runtime"
TERMS_FILE = RUNTIME.parent / "personal_terms.json"
HISTORY_DIR = RUNTIME.parent / "history"
SHORTCUT_START = re.compile(r"\binsert\s+my\s+", re.IGNORECASE)


def save_history(text):
    if not text.strip():
        return

    now = datetime.now().astimezone()
    entry = {"time": now.timetz().isoformat(timespec="seconds"), "text": text}
    try:
        HISTORY_DIR.mkdir(exist_ok=True)
        with (HISTORY_DIR / f"{now.date().isoformat()}.jsonl").open("a", encoding="utf-8") as history:
            history.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError as exc:
        print(f"Could not save history: {exc}", file=sys.stderr)


def replace_shortcuts(text, protect=None):
    if not SHORTCUT_START.search(text):
        return text

    try:
        terms = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        terms = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {TERMS_FILE.name}: {exc}") from exc

    if not isinstance(terms, dict):
        raise SystemExit(f"{TERMS_FILE.name} must contain a JSON object.")

    shortcuts = {}
    for key, value in terms.items():
        normalized = " ".join(key.lower().split())
        if not normalized or normalized in shortcuts:
            raise SystemExit(f"{TERMS_FILE.name} contains a blank or duplicate key: {key!r}")
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
        print(f"No saved value for {key} in {TERMS_FILE.name}.", file=sys.stderr)
    return result


def format_transcript(text, cleaner=None):
    if cleaner is None or not text.strip():
        return replace_shortcuts(text)
    values = {}

    def protect(value):
        index = len(values)
        marker = f"ZXQ{index}QXZ"
        while marker in text or marker in values:
            index += 1
            marker = f"ZXQ{index}QXZ"
        values[marker] = value
        return marker

    protected = replace_shortcuts(text, protect)
    try:
        return cleaner.clean(protected, values)
    except (OSError, ValueError, KeyError, IndexError, TypeError, RecursionError):
        print("Smart cleanup failed; using original transcript.", file=sys.stderr)
        return restore(protected, values)


def transcribe():
    chunks = []
    sample_rate = int(sd.query_devices(kind="input")["default_samplerate"])

    def record(indata, frames, time, status):
        if status:
            print(status, file=sys.stderr)
        chunks.append(bytes(indata))

    input("Press Enter to record...")
    with sd.RawInputStream(samplerate=sample_rate, channels=1, dtype="int16", callback=record):
        input("Recording. Press Enter to stop...")

    if not chunks:
        raise SystemExit("No audio recorded.")

    audio = io.BytesIO()
    with wave.open(audio, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(sample_rate)
        wav.writeframes(b"".join(chunks))

    result = subprocess.run(
        [str(RUNTIME / "parakeet-cli.exe"), "transcribe", "--model", str(RUNTIME / "redux-q8_0.gguf"), "--input", "-", "--threads", "8"],
        input=audio.getvalue(),
        capture_output=True,
    )
    if result.returncode:
        raise SystemExit(result.stderr.decode(errors="replace").strip())
    return result.stdout.decode(errors="replace").strip()


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument("--show-raw", action="store_true", help="Show the raw transcript before cleanup; do not save it.")
    args = parser.parse_args(argv)
    enabled = input("Smart cleanup? [y/N]: ").strip().lower() == "y"
    with smart_session(enabled) as cleaner:
        raw = transcribe()
        if args.show_raw:
            print(f"Raw transcript: {raw}", file=sys.stderr, flush=True)
        text = format_transcript(raw, cleaner)
        print(text, flush=True)
        save_history(text)


if __name__ == "__main__":
    main()
