"""Resident local dictation engine and JSON-lines IPC server."""

import argparse
import io
import json
import logging
import os
import secrets
import socketserver
import subprocess
import threading
import time
import wave
from collections import deque
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

import sounddevice as sd

import smart
import stt
from vocabulary import apply_vocabulary
from windows_support import ChildJob, Hotkey, foreground_app, insert_text


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "STTCore"
ENDPOINT = APP_DIR / "endpoint.json"
LOG = APP_DIR / "engine.log"
SAMPLE_RATE = 16000
IDLE_UNLOAD = 300


def wav_bytes(pcm, rate=SAMPLE_RATE):
    output = io.BytesIO()
    with wave.open(output, "wb") as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(rate)
        wav.writeframes(pcm)
    return output.getvalue()


class ParakeetASR:
    def __init__(self, executable=stt.RUNTIME / "parakeet-cli.exe", model=stt.RUNTIME / "redux-q8_0.gguf", threads=8):
        self.executable, self.model, self.threads = Path(executable), Path(model), threads

    def transcribe(self, pcm, rate):
        if not self.executable.is_file() or not self.model.is_file():
            raise FileNotFoundError("Parakeet runtime or model missing")
        result = subprocess.run([str(self.executable), "transcribe", "--model", str(self.model),
                                 "--input", "-", "--threads", str(self.threads)],
                                input=wav_bytes(pcm, rate), capture_output=True, timeout=90,
                                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if result.returncode:
            raise RuntimeError(result.stderr.decode(errors="replace").strip() or "Parakeet failed")
        return apply_vocabulary(result.stdout.decode(errors="replace").strip())


def cleanup_needed(text):
    import re
    if smart.JSON_START.match(text):
        return True
    return bool(re.search(r"\b(?:um|uh|actually|sorry|i mean|scratch that|make it|make that|no wait)\b", text, re.I))


def meaning_guard(raw, cleaned):
    """Reject lost protected values, negation and numbers; allow explicit numeric corrections."""
    import re
    numbers = lambda s: re.findall(r"\b\d+(?:[.:]\d+)?\b", s)
    if re.search(r"\b(?:don't|doesn't|didn't|not|never|no)\b", raw, re.I) and not re.search(
            r"\b(?:don't|doesn't|didn't|not|never|no)\b", cleaned, re.I):
        if not re.search(r"\b(?:not\s+\S+\s+(?:make it|make that)|no wait)\b", raw, re.I):
            return False
    if numbers(cleaned) and not set(numbers(cleaned)) <= set(numbers(raw)):
        return False
    common = {"a", "an", "the", "am", "is", "are", "was", "were", "be", "been", "to", "at",
              "on", "in", "of", "for", "and", "or", "but", "do", "does", "did", "it", "that"}
    words = lambda s: set(re.findall(r"[a-z']+", s.lower()))
    introduced = {w for w in words(cleaned) - words(raw) if len(w) > 3 and w not in common}
    return not introduced


def append_history(record):
    if not record["text"].strip():
        return
    now = datetime.now().astimezone()
    record = {"time": now.timetz().isoformat(timespec="seconds"), **record}
    stt.HISTORY_DIR.mkdir(exist_ok=True)
    with (stt.HISTORY_DIR / f"{now.date().isoformat()}.jsonl").open("a", encoding="utf-8") as output:
        output.write(json.dumps(record, ensure_ascii=False) + "\n")


class DictationEngine:
    def __init__(self, asr=None, capture=True, hotkey=False):
        self.asr = asr or ParakeetASR()
        self.lock = threading.RLock()
        self.state = "idle"
        self.mode = "hold"
        self.smart_enabled = False
        self.cleaner = None
        self.cleaner_used = 0
        self.samples = []
        self.pending = []
        self.segment = []
        self.level = 0.0
        self.noise = 100.0
        self.quiet_frames = 0
        self.pre_roll = deque(maxlen=15)
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.listeners = set()
        self.stream = None
        self.rate = SAMPLE_RATE
        self.capture_rate = SAMPLE_RATE
        self.start_time = 0.0
        self.foreground = None
        self.insert = False
        self.job = ChildJob()
        from model_manager import ensure_asr
        ensure_asr()
        if capture:
            self._start_capture()
        self.hotkey = None
        self.hotkey_enabled = False
        if hotkey:
            self._enable_hotkey()
        threading.Thread(target=self._idle_loop, daemon=True).start()

    def _start_capture(self):
        device = sd.query_devices(kind="input")
        try:
            self.stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                            blocksize=320, callback=self._audio)
            self.rate = SAMPLE_RATE
            self.capture_rate = SAMPLE_RATE
            self.stream.start()
        except sd.PortAudioError:
            self.rate = int(device["default_samplerate"])
            self.capture_rate = self.rate
            self.stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16",
                                            blocksize=max(1, self.rate // 50), callback=self._audio)
            self.stream.start()

    def _audio(self, indata, frames, timing, status):
        if status:
            logging.warning("audio: %s", status)
        chunk = bytes(indata)
        view = memoryview(chunk).cast("h")
        level = (sum(abs(value) for value in view) / max(1, len(view)))
        with self.lock:
            self.level = min(1.0, level / 10000)
            if self.state in ("recording", "locked"):
                self.samples.append(chunk)
                self.segment.append(chunk)
                threshold = max(250, self.noise * 3)
                self.quiet_frames = self.quiet_frames + 1 if level < threshold else 0
                if self.quiet_frames >= 30 and len(self.segment) >= 200:
                    payload = b"".join(self.segment)
                    self.pending.append(self.executor.submit(self.asr.transcribe, payload, self.rate))
                    self.segment.clear()
                    self.quiet_frames = 0
            else:
                self.noise = self.noise * 0.98 + level * 0.02
                self.pre_roll.append(chunk)
        if int(time.monotonic() * 10) != int((time.monotonic() - frames / self.rate) * 10):
            self.emit("level", {"value": self.level})

    def emit(self, kind, data):
        event = {"event": kind, **data}
        dead = []
        for writer in tuple(self.listeners):
            try:
                writer(event)
            except OSError:
                dead.append(writer)
        for writer in dead:
            self.listeners.discard(writer)

    def _state(self, value):
        self.state = value
        self.emit("state", {"value": value, "mode": self.mode})

    def _hotkey(self, action):
        if self.hotkey_enabled:
            def run():
                try:
                    self.command(action, {"insert": True})
                except Exception as exc:
                    self.emit("error", {"message": str(exc)})
            threading.Thread(target=run, daemon=True).start()

    def _enable_hotkey(self):
        if self.hotkey is None:
            self.hotkey = Hotkey(self._hotkey)
            self.hotkey.start()
        self.hotkey_enabled = True

    def _ensure_cleaner(self):
        if self.cleaner is None:
            from model_manager import ensure_cleanup
            executable, layers = ensure_cleanup()
            self.cleaner = smart.SmartCleanup(gpu_layers=layers, executable=executable)
            try:
                self.cleaner.start()
            except (OSError, TimeoutError):
                self.cleaner.close()
                if layers == 0:
                    self.cleaner = None
                    raise
                cpu = smart.RUNTIME / "smart-cpu" / "llama-server.exe"
                self.cleaner = smart.SmartCleanup(gpu_layers=0, executable=cpu if cpu.exists() else executable)
                self.cleaner.start()
        self.cleaner_used = time.monotonic()

    def _idle_loop(self):
        while True:
            time.sleep(5)
            with self.lock:
                if self.cleaner and self.state == "idle" and time.monotonic() - self.cleaner_used > IDLE_UNLOAD:
                    self.cleaner.close()
                    self.cleaner = None

    def command(self, name, args):
        with self.lock:
            if name == "status":
                return {"state": self.state, "mode": self.mode, "level": self.level,
                        "smart_ready": self.cleaner is not None, "sample_rate": self.rate}
            if name == "settings":
                if self.state != "idle":
                    raise ValueError("settings require idle state")
                if "mode" in args:
                    if args["mode"] not in ("hold", "tap"):
                        raise ValueError("mode must be hold or tap")
                    self.mode = args["mode"]
                if "smart" in args:
                    self.smart_enabled = bool(args["smart"])
                if "hotkey" in args:
                    self.hotkey_enabled = bool(args["hotkey"])
                    if self.hotkey_enabled:
                        self._enable_hotkey()
                if self.smart_enabled:
                    self._ensure_cleaner()
                return {"mode": self.mode, "smart": self.smart_enabled, "hotkey": self.hotkey_enabled}
            if name in ("start", "press"):
                if self.state == "locked" and self.mode == "tap":
                    return self._finish()
                if self.state != "idle":
                    raise ValueError("engine is busy")
                self.rate = self.capture_rate
                self.samples = list(self.pre_roll)
                self.segment = list(self.pre_roll)
                self.pending = []
                self.start_time = time.perf_counter()
                self.foreground = foreground_app()
                self.insert = bool(args.get("insert", False))
                self._state("locked" if self.mode == "tap" else "recording")
                return {"state": self.state}
            if name == "release":
                if self.state == "locked":
                    return {"state": self.state}
                if self.state != "recording":
                    raise ValueError("not recording")
                return self._finish()
            if name == "cancel":
                if self.state not in ("recording", "locked"):
                    raise ValueError("nothing to cancel")
                self.samples.clear()
                self.segment.clear()
                self._state("idle")
                return {"state": self.state}
            if name == "replay":
                if self.state != "idle":
                    raise ValueError("engine is busy")
                source = Path(args["path"]).resolve()
                with wave.open(str(source), "rb") as wav:
                    if wav.getnchannels() != 1 or wav.getsampwidth() != 2:
                        raise ValueError("WAV must be mono 16-bit PCM")
                    payload, rate = wav.readframes(wav.getnframes()), wav.getframerate()
                self.rate = rate
                self.samples = [payload]
                self.segment = [payload]
                self.pending = []
                self.start_time = time.perf_counter()
                self.foreground = foreground_app()
                self.insert = bool(args.get("insert", False))
                self._state("locked" if self.mode == "tap" else "recording")
                return {"state": self.state}
            if name == "shutdown":
                return {"state": "stopping"}
            raise ValueError(f"unknown command: {name}")

    def _finish(self):
        tail = b"".join(self.segment)
        futures = list(self.pending)
        if tail:
            futures.append(self.executor.submit(self.asr.transcribe, tail, self.rate))
        if not futures:
            raise ValueError("no audio recorded")
        release_at = time.perf_counter()
        self._state("processing")
        threading.Thread(target=self._process, args=(futures, release_at), daemon=True).start()
        return {"state": "processing"}

    def _process(self, futures, release_at):
        timings = {}
        try:
            start = time.perf_counter()
            raw = " ".join(filter(None, (future.result() for future in futures)))
            timings["asr_ms"] = round((time.perf_counter() - start) * 1000, 1)
            start = time.perf_counter()
            plain = stt.format_transcript(raw)
            timings["shortcuts_ms"] = round((time.perf_counter() - start) * 1000, 1)
            final = plain
            if self.smart_enabled and cleanup_needed(raw):
                start = time.perf_counter()
                try:
                    candidate = stt.format_transcript(raw, self.cleaner)
                    if not meaning_guard(plain, candidate):
                        raise ValueError("cleanup changed a protected fact")
                    final = candidate
                except Exception as exc:
                    logging.warning("cleanup fallback: %s", exc)
                    self.emit("error", {"message": "Cleanup failed; raw transcript used"})
                timings["cleanup_ms"] = round((time.perf_counter() - start) * 1000, 1)
            else:
                timings["cleanup_ms"] = 0.0
            if self.insert and final:
                start = time.perf_counter()
                try:
                    insert_text(final)
                except OSError as exc:
                    self.emit("error", {"message": f"Text insertion failed: {exc}"})
                timings["insert_ms"] = round((time.perf_counter() - start) * 1000, 1)
            timings["release_to_ready_ms"] = round((time.perf_counter() - release_at) * 1000, 1)
            try:
                append_history({"text": final, "raw": raw, "cleaned": final,
                                "timings": timings, "app": self.foreground, "mode": self.mode})
            except OSError as exc:
                self.emit("error", {"message": f"History could not be saved: {exc}"})
            self.emit("result", {"raw": raw, "text": final, "timings": timings})
        except Exception as exc:
            logging.exception("dictation failed")
            self.emit("error", {"message": str(exc)})
        finally:
            with self.lock:
                self.samples.clear()
                self.segment.clear()
                self.pending.clear()
                self._state("idle")

    def close(self):
        with self.lock:
            if self.stream:
                self.stream.stop()
                self.stream.close()
            if self.cleaner:
                self.cleaner.close()
            self.executor.shutdown(wait=False, cancel_futures=True)
            self.job.close()


class IPCHandler(socketserver.StreamRequestHandler):
    def handle(self):
        write_lock = threading.Lock()
        def send(payload):
            with write_lock:
                self.wfile.write(json.dumps(payload, ensure_ascii=False).encode("utf-8") + b"\n")
                self.wfile.flush()
        authorized = False
        for line in self.rfile:
            try:
                message = json.loads(line)
                if not authorized:
                    if not secrets.compare_digest(str(message.get("token", "")), self.server.token):
                        raise PermissionError("invalid engine token")
                    authorized = True
                if message.get("command") == "subscribe":
                    self.server.engine.listeners.add(send)
                    send({"id": message.get("id"), "ok": True})
                else:
                    result = self.server.engine.command(message["command"], message.get("args", {}))
                    send({"id": message.get("id"), "ok": True, "result": result})
                    if message["command"] == "shutdown":
                        threading.Thread(target=self.server.shutdown, daemon=True).start()
            except Exception as exc:
                try:
                    send({"id": message.get("id") if isinstance(message, dict) else None,
                          "ok": False, "error": str(exc)})
                except OSError:
                    break
        self.server.engine.listeners.discard(send)


class IPCServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


def serve(capture=True, hotkey=False):
    APP_DIR.mkdir(parents=True, exist_ok=True)
    logging.basicConfig(filename=LOG, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    engine = DictationEngine(capture=capture, hotkey=hotkey)
    token = secrets.token_hex(32)
    with IPCServer(("127.0.0.1", 0), IPCHandler) as server:
        server.engine, server.token = engine, token
        temporary = ENDPOINT.with_suffix(".tmp")
        temporary.write_text(json.dumps({"port": server.server_address[1], "token": token,
                                         "pid": os.getpid()}), encoding="utf-8")
        temporary.replace(ENDPOINT)
        try:
            server.serve_forever(poll_interval=0.2)
        finally:
            ENDPOINT.unlink(missing_ok=True)
            engine.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("serve", nargs="?")
    parser.add_argument("--no-mic", action="store_true")
    parser.add_argument("--hotkey", action="store_true")
    options = parser.parse_args()
    serve(capture=not options.no_mic, hotkey=options.hotkey)
