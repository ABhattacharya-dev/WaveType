import io
import subprocess
import sys
import wave
from pathlib import Path

import sounddevice as sd


RUNTIME = Path(__file__).resolve().parent / "runtime"


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
    print(result.stdout.decode(errors="replace").strip())


if __name__ == "__main__":
    main()
