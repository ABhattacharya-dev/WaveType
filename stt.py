import io
import json
import re
import subprocess
import sys
import wave
from pathlib import Path

import sounddevice as sd


RUNTIME = Path(__file__).resolve().parent / "runtime"
TERMS_FILE = RUNTIME.parent / "personal_terms.json"
SHORTCUT = re.compile(r"\binsert\s+my\s+(name|email|address)\b", re.IGNORECASE)


def replace_shortcuts(text):
    if not SHORTCUT.search(text):
        return text

    try:
        terms = json.loads(TERMS_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        terms = {}
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise SystemExit(f"Cannot read {TERMS_FILE.name}: {exc}") from exc

    if not isinstance(terms, dict):
        raise SystemExit(f"{TERMS_FILE.name} must contain a JSON object.")

    missing = set()

    def replace(match):
        key = match.group(1).lower()
        value = terms.get(key)
        if not isinstance(value, str) or not value.strip():
            missing.add(key)
            return match.group()
        return value

    result = SHORTCUT.sub(replace, text)
    for key in sorted(missing):
        print(f"No saved value for {key} in {TERMS_FILE.name}.", file=sys.stderr)
    return result


def main():
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
    print(replace_shortcuts(result.stdout.decode(errors="replace").strip()))


if __name__ == "__main__":
    main()
