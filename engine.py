"""Resident local dictation engine and JSON-lines IPC server."""

import argparse
import ctypes
import io
import json
import logging
import os
import queue
import secrets
import socketserver
import subprocess
import sys
import threading
import time
import wave
from collections import deque
from array import array
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import sounddevice as sd
import webrtcvad

import smart
import stt
from vocabulary import apply_vocabulary
from windows_support import ChildJob, Hotkey, foreground_app, foreground_window, insert_text
from ipc_protocol import APP_DIR, ENDPOINT
from user_data import (dictionary_get, dictionary_set, history_append,
                       history_change, history_compact, history_list)
from vocabulary import VOCABULARY


LOG = APP_DIR / "engine.log"
SAMPLE_RATE = 16000
IDLE_UNLOAD = 300
ASR_IDLE_UNLOAD = 20


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


class ParakeetLibraryASR:
    """One loaded model context reused for every recording."""

    def __init__(self, library, model=stt.RUNTIME / "redux-q8_0.gguf"):
        self.dll = ctypes.CDLL(str(library))
        self.dll.parakeet_capi_abi_version.restype = ctypes.c_int
        if self.dll.parakeet_capi_abi_version() != 10:
            raise OSError("unsupported Parakeet library ABI")
        self.dll.parakeet_capi_load.argtypes = [ctypes.c_char_p]
        self.dll.parakeet_capi_load.restype = ctypes.c_void_p
        self.dll.parakeet_capi_load_error.restype = ctypes.c_char_p
        self.dll.parakeet_capi_transcribe_pcm.argtypes = [ctypes.c_void_p, ctypes.POINTER(ctypes.c_float),
                                                         ctypes.c_int, ctypes.c_int, ctypes.c_int]
        self.dll.parakeet_capi_transcribe_pcm.restype = ctypes.c_void_p
        self.dll.parakeet_capi_last_error.argtypes = [ctypes.c_void_p]
        self.dll.parakeet_capi_last_error.restype = ctypes.c_char_p
        self.dll.parakeet_capi_free_string.argtypes = [ctypes.c_void_p]
        self.dll.parakeet_capi_free.argtypes = [ctypes.c_void_p]
        self.lock = threading.Lock()
        self.context = self.dll.parakeet_capi_load(os.fsencode(model))
        if not self.context:
            raise OSError(self.dll.parakeet_capi_load_error().decode(errors="replace"))

    def transcribe(self, pcm, rate):
        samples = array("h")
        samples.frombytes(pcm)
        normalized = array("f", (sample / 32768.0 for sample in samples))
        data = (ctypes.c_float * len(normalized)).from_buffer(normalized)
        with self.lock:
            pointer = self.dll.parakeet_capi_transcribe_pcm(self.context, data, len(normalized), rate, 0)
            if not pointer:
                raise RuntimeError(self.dll.parakeet_capi_last_error(self.context).decode(errors="replace"))
            try:
                result = ctypes.string_at(pointer).decode("utf-8")
            finally:
                self.dll.parakeet_capi_free_string(pointer)
        return apply_vocabulary(result.strip())

    def close(self):
        with self.lock:
            if self.context:
                self.dll.parakeet_capi_free(self.context)
                self.context = None


def cleanup_needed(text):
    import re
    simple = re.fullmatch(r"\s*(?:hello|hi|hey|thanks|thank you|good morning|good afternoon|good evening)(?:[ ,]+everyone)?[.!?]?\s*", text, re.I)
    return bool(text.strip()) and not bool(simple)


def meaning_guard(raw, cleaned):
    """Reject likely meaning drift while allowing common grammar inflections."""
    import re
    if smart.JSON_START.match(raw):
        return True  # JSON structure and placeholders are validated by smart.py.
    correction = re.search(r"\b(?:actually|sorry|i mean|no wait|scratch that|make it|make that)\b", raw, re.I)
    number_correction = re.search(r"\bno\b\s*[,;]?\s*\d", raw, re.I)
    numbers = lambda s: re.findall(r"\b\d+(?:[.:]\d+)?\b", s)
    if re.search(r"\b(?:don't|doesn't|didn't|not|never|no)\b", raw, re.I) and not re.search(
            r"\b(?:don't|doesn't|didn't|not|never|no)\b", cleaned, re.I):
        if not (correction or number_correction):
            return False
    if numbers(cleaned) and not set(numbers(cleaned)) <= set(numbers(raw)):
        return False
    if not (correction or number_correction) and len(re.findall(r"\w+", cleaned)) < 0.7 * len(re.findall(r"\w+", raw)):
        return False
    common = {"a", "an", "the", "am", "is", "are", "was", "were", "be", "been", "to", "at",
              "on", "in", "of", "for", "and", "or", "but", "do", "does", "did", "it", "that"}
    irregular = {"went": "go", "goes": "go", "bought": "buy", "knew": "know", "known": "know",
                 "doesnt": "not", "dont": "not", "didnt": "not"}
    def words(value):
        return {irregular.get(word.replace("'", ""), word.replace("'", ""))
                for word in re.findall(r"[a-z']+", value.lower())}
    original = words(raw)
    introduced = {w for w in words(cleaned) - original if len(w) > 3 and w not in common
                  and not any(form in original for form in (w.rstrip("s"), w.rstrip("s") + "e",
                                                       w.removesuffix("ed"), w.removesuffix("ing")))}
    return not introduced


class DictationEngine:
    def __init__(self, asr=None, capture=True, hotkey=False):
        if asr is None:
            from model_manager import ensure_asr
            self.asr_library = ensure_asr()
            self.asr = None
        else:
            self.asr_library = None
            self.asr = asr
        self.asr_future = None
        self.asr_used = time.monotonic()
        self.asr_jobs = set()
        self.lock = threading.RLock()
        self.state = "idle"
        self.mode = "hold"
        self.tap_threshold_ms = 250
        self.smart_enabled = False
        self.tier = "auto"
        self.cleaner = None
        self.cleaner_future = None
        self.cleaner_used = 0
        self.pending = []
        self.segment = []
        self.level = 0.0
        self.noise = 100.0
        self.quiet_frames = 0
        self.speech_run = 0
        self.max_speech_run = 0
        self.vad = webrtcvad.Vad(3)
        self.pre_roll = deque(maxlen=15)
        self.executor = ThreadPoolExecutor(max_workers=2)
        self.listeners = set()
        self.stopping = threading.Event()
        self.level_wakeup = threading.Event()
        self.stream = None
        self.rate = SAMPLE_RATE
        self.capture_rate = SAMPLE_RATE
        self.microphone = None
        self.language = "auto"
        self.start_time = 0.0
        self.foreground = None
        self.target_window = None
        self.insert = False
        self.replaying = False
        self.record_history = True
        self.job = None if os.getenv("STT_ENGINE_PARENT_JOB") == "1" else ChildJob()
        if capture:
            self._start_capture()
        self.hotkey = None
        self.hotkey_enabled = False
        self.hotkey_events = queue.Queue()
        self.hotkey_pending_finish = False
        self.hotkey_recording = False
        threading.Thread(target=self._hotkey_loop, daemon=True).start()
        if hotkey:
            self._enable_hotkey()
        threading.Thread(target=self._idle_loop, daemon=True).start()
        threading.Thread(target=self._level_loop, daemon=True).start()

    def _start_capture(self):
        device = sd.query_devices(self.microphone, kind="input")
        try:
            self.stream = sd.RawInputStream(samplerate=SAMPLE_RATE, channels=1, dtype="int16",
                                            blocksize=320, callback=self._audio, device=self.microphone)
            self.rate = SAMPLE_RATE
            self.capture_rate = SAMPLE_RATE
            self.stream.start()
        except sd.PortAudioError:
            self.rate = int(device["default_samplerate"])
            self.capture_rate = self.rate
            self.stream = sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16",
                                            blocksize=max(1, self.rate // 50), callback=self._audio,
                                            device=self.microphone)
            self.stream.start()

    def _audio(self, indata, frames, timing, status):
        if status:
            logging.warning("audio: %s", status)
        chunk = bytes(indata)
        view = memoryview(chunk).cast("h")
        level = (sum(abs(value) for value in view) / max(1, len(view)))
        with self.lock:
            self.level = min(1.0, level / 10000)
            if self.state in ("recording", "locked") and not self.replaying:
                self.segment.append(chunk)
                threshold = max(250, self.noise * 3)
                voice = self.vad.is_speech(chunk, self.rate) and level >= threshold if self.rate == 16000 else level >= threshold
                self.speech_run = self.speech_run + 1 if voice else 0
                self.max_speech_run = max(self.max_speech_run, self.speech_run)
                self.quiet_frames = 0 if voice else self.quiet_frames + 1
                if self.quiet_frames >= 30 and len(self.segment) >= 200 and self.max_speech_run >= 8:
                    payload = b"".join(self.segment)
                    self.pending.append(self._submit_asr(payload, self.rate))
                    self.segment.clear()
                    self.quiet_frames = 0
                    self.speech_run = 0
                    self.max_speech_run = 0
            elif self.state == "idle":
                self.noise = self.noise * 0.98 + level * 0.02
                self.pre_roll.append(chunk)

    def _level_loop(self):
        while not self.stopping.is_set():
            self.level_wakeup.clear()
            if self.listeners:
                self.emit("level", {"value": self.level})
            # Idle heartbeats keep subscribed sockets alive without a 30 Hz UI wakeup.
            self.level_wakeup.wait(1 / 30 if self.state in ("recording", "locked") else 5)

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

    def _asr(self, pcm, rate):
        start = time.perf_counter()
        asr = self.asr_future.result() if self.asr_future else self.asr
        text = asr.transcribe(pcm, rate)
        return text, round((time.perf_counter() - start) * 1000, 1)

    def _submit_asr(self, pcm, rate):
        future = self.executor.submit(self._asr, pcm, rate)
        self.asr_jobs.add(future)
        return future

    def _load_asr(self):
        try:
            return ParakeetLibraryASR(self.asr_library)
        except (OSError, ValueError) as exc:
            logging.warning("Parakeet library unavailable, using CLI: %s", exc)
            return ParakeetASR()

    def _warm_asr(self):
        self.asr_used = time.monotonic()
        if self.asr_library and self.asr_future is None:
            self.asr_future = self.executor.submit(self._load_asr)

    def _state(self, value):
        self.state = value
        self.emit("state", {"value": value, "mode": self.mode})
        self.level_wakeup.set()

    def _hotkey(self, action, held_ms):
        if self.hotkey_enabled:
            self.hotkey_events.put((action, held_ms))

    def _hotkey_loop(self):
        while True:
            event = self.hotkey_events.get()
            try:
                if event is None:
                    return
                if self.stopping.is_set():
                    continue
                action, held_ms = event
                if action == "abort":
                    self.hotkey_pending_finish = False
                    if self.hotkey_recording and self.state == "recording":
                        self.command("cancel", {})
                    continue
                if action == "press" and self.state == "locked" and self.mode == "hybrid":
                    self.hotkey_pending_finish = True
                    continue
                if action == "release" and self.hotkey_pending_finish:
                    self.hotkey_pending_finish = False
                    self.command("press", {"insert": True})
                    self.hotkey_recording = False
                    continue
                if action == "release" and self.state != "recording":
                    continue
                if action == "press" and self.state == "idle":
                    self.hotkey_recording = True
                self.command(action, {"insert": True, "held_ms": held_ms})
                if action == "release" and self.state == "processing":
                    self.hotkey_recording = False
            except Exception as exc:
                self.hotkey_recording = False
                self.emit("error", {"message": str(exc)})
            finally:
                self.hotkey_events.task_done()

    def _enable_hotkey(self):
        if self.hotkey is None:
            self.hotkey = Hotkey(self._hotkey)
            self.hotkey.start()
        self.hotkey_enabled = True

    def _ensure_cleaner(self):
        if self.cleaner is None:
            from model_manager import ensure_cleanup
            executable, layers = ensure_cleanup(cpu_only=self.tier == "cpu")
            cleaner = smart.SmartCleanup(gpu_layers=layers, executable=executable)
            try:
                cleaner.start()
            except (OSError, TimeoutError):
                cleaner.close()
                if layers == 0:
                    raise
                cpu = smart.RUNTIME / "smart-cpu" / "llama-server.exe"
                cleaner = smart.SmartCleanup(gpu_layers=0, executable=cpu if cpu.exists() else executable)
                cleaner.start()
            self.cleaner = cleaner
        self.cleaner_used = time.monotonic()

    def _idle_loop(self):
        while not self.stopping.wait(5):
            with self.lock:
                self._unload_idle_asr()
                if self.cleaner and self.state == "idle" and time.monotonic() - self.cleaner_used > IDLE_UNLOAD:
                    self.cleaner.close()
                    self.cleaner = None

    def _unload_idle_asr(self):
        self.asr_jobs = {job for job in self.asr_jobs if not job.done()}
        if (self.asr_library and self.state == "idle" and self.asr_future and
                self.asr_future.done() and not self.asr_jobs and
                time.monotonic() - self.asr_used > ASR_IDLE_UNLOAD):
            asr = self.asr_future.result()
            if hasattr(asr, "close"):
                asr.close()
            self.asr_future = None

    def command(self, name, args):
        with self.lock:
            if name == "status":
                return {"state": self.state, "mode": self.mode, "level": self.level,
                        "tap_threshold_ms": self.tap_threshold_ms, "hotkey": self.hotkey_enabled,
                        "smart_ready": self.cleaner is not None, "sample_rate": self.rate,
                        "asr_backend": (type(self.asr_future.result()).__name__ if self.asr_future and
                                        self.asr_future.done() else "Parakeet (unloaded)" if self.asr_library else
                                        type(self.asr).__name__), "capture_ready": self.stream is not None,
                        "smart": self.smart_enabled, "tier": self.tier, "microphone": self.microphone,
                        "language": self.language}
            if name == "devices":
                return [{"index": index, "name": device["name"]} for index, device in
                        enumerate(sd.query_devices()) if device["max_input_channels"] > 0]
            if name == "model_status":
                from model_manager import gpu_available, free_memory_gb
                return {"asr_installed": (stt.RUNTIME / "redux-q8_0.gguf").is_file(),
                        "cleanup_installed": smart.MODEL.is_file(), "gpu_available": gpu_available(),
                        "free_memory_gb": round(free_memory_gb(), 1), "language": "Automatic (25 languages)",
                        "tier": self.tier}
            if name == "dictionary_get":
                return dictionary_get(stt.TERMS_FILE, VOCABULARY)
            if name == "dictionary_set":
                return dictionary_set(stt.TERMS_FILE, VOCABULARY, args.get("kind"), args.get("entries"))
            if name == "history_list":
                return history_list(stt.HISTORY_DIR, args.get("limit", 100), args.get("offset", 0))
            if name == "history_change":
                return history_change(stt.HISTORY_DIR, args.get("id"), args.get("action"))
            if name == "settings":
                if self.state != "idle":
                    if args != {"hotkey": False}:
                        raise ValueError("settings require idle state")
                    self.hotkey_enabled = False
                    return {"mode": self.mode, "tap_threshold_ms": self.tap_threshold_ms,
                            "smart": self.smart_enabled, "tier": self.tier, "hotkey": False}
                if "mode" in args:
                    if args["mode"] not in ("hold", "tap", "hybrid"):
                        raise ValueError("mode must be hold, tap, or hybrid")
                    self.mode = args["mode"]
                if "tap_threshold_ms" in args:
                    threshold = args["tap_threshold_ms"]
                    if isinstance(threshold, bool) or not isinstance(threshold, int) or not 100 <= threshold <= 1000:
                        raise ValueError("tap_threshold_ms must be an integer from 100 to 1000")
                    self.tap_threshold_ms = threshold
                if "smart" in args:
                    self.smart_enabled = bool(args["smart"])
                if "tier" in args:
                    if args["tier"] not in ("auto", "cpu"):
                        raise ValueError("tier must be auto or cpu")
                    if args["tier"] != self.tier and self.cleaner:
                        self.cleaner.close()
                        self.cleaner = None
                    self.tier = args["tier"]
                if "language" in args:
                    if args["language"] != "auto":
                        raise ValueError("this Parakeet adapter detects its supported languages automatically")
                    self.language = "auto"
                if "microphone" in args:
                    microphone = args["microphone"]
                    if microphone is not None and (not isinstance(microphone, int) or
                            microphone not in [item["index"] for item in self.command("devices", {})]):
                        raise ValueError("unknown microphone")
                    if microphone != self.microphone:
                        if self.stream:
                            self.stream.stop()
                            self.stream.close()
                            self.stream = None
                        self.microphone = microphone
                        self._start_capture()
                if "hotkey" in args:
                    self.hotkey_enabled = bool(args["hotkey"])
                    if self.hotkey_enabled:
                        self._enable_hotkey()
                if self.smart_enabled:
                    try:
                        self._ensure_cleaner()
                    except Exception:
                        self.smart_enabled = False
                        raise
                return {"mode": self.mode, "tap_threshold_ms": self.tap_threshold_ms,
                        "smart": self.smart_enabled, "tier": self.tier,
                        "hotkey": self.hotkey_enabled, "microphone": self.microphone,
                        "language": self.language}
            click = name == "toggle"
            if name in ("start", "press", "toggle"):
                if self.state == "locked" and (self.mode in ("tap", "hybrid") or click):
                    return self._finish()
                if click and self.state == "recording":
                    return self._finish()
                if self.state != "idle":
                    raise ValueError("engine is busy")
                if self.stream is None:
                    self._start_capture()
                self._warm_asr()
                self.rate = self.capture_rate
                self.replaying = False
                self.segment = list(self.pre_roll)
                self.pending = []
                self.speech_run = self.max_speech_run = self.quiet_frames = 0
                self.start_time = time.perf_counter()
                self.foreground = foreground_app()
                self.target_window = foreground_window()
                self.insert = bool(args.get("insert", False))
                self.record_history = True
                self._state("locked" if self.mode == "tap" or click else "recording")
                if self.smart_enabled and self.cleaner is None:
                    self.cleaner_future = self.executor.submit(self._ensure_cleaner)
                return {"state": self.state}
            if name == "release":
                if self.state == "locked":
                    return {"state": self.state}
                if self.state != "recording":
                    raise ValueError("not recording")
                if self.mode == "hybrid" and args.get("held_ms", self.tap_threshold_ms) < self.tap_threshold_ms:
                    self._state("locked")
                    return {"state": self.state}
                return self._finish()
            if name == "cancel":
                if self.state not in ("recording", "locked"):
                    raise ValueError("nothing to cancel")
                self.segment.clear()
                self.replaying = False
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
                self._warm_asr()
                self.replaying = True
                self.segment = [payload]
                self.pending = []
                self.start_time = time.perf_counter()
                self.foreground = foreground_app()
                self.target_window = foreground_window()
                self.insert = bool(args.get("insert", False))
                self.record_history = bool(args.get("history", False))
                self._state("locked" if self.mode == "tap" else "recording")
                if self.smart_enabled and self.cleaner is None:
                    self.cleaner_future = self.executor.submit(self._ensure_cleaner)
                return {"state": self.state}
            if name == "shutdown":
                return {"state": "stopping"}
            raise ValueError(f"unknown command: {name}")

    def _finish(self):
        tail = b"".join(self.segment)
        futures = list(self.pending)
        if tail:
            futures.append(self._submit_asr(tail, self.rate))
        if not futures:
            raise ValueError("no audio recorded")
        release_at = time.perf_counter()
        self.recording_ms = round((release_at - self.start_time) * 1000, 1)
        self._state("processing")
        threading.Thread(target=self._process, args=(futures, release_at), daemon=True).start()
        return {"state": "processing"}

    def _process(self, futures, release_at):
        timings = {}
        error = lambda message: self.emit("error", {"message": message})
        try:
            start = time.perf_counter()
            parts = [future.result() for future in futures]
            raw = " ".join(filter(None, (text for text, _ in parts)))
            timings["asr_ms"] = round((time.perf_counter() - start) * 1000, 1)
            timings["asr_compute_ms"] = round(sum(milliseconds for _, milliseconds in parts), 1)
            timings["recording_ms"] = self.recording_ms
            start = time.perf_counter()
            plain = stt.format_transcript(raw, on_error=error)
            timings["shortcuts_ms"] = round((time.perf_counter() - start) * 1000, 1)
            final = plain
            if self.smart_enabled and cleanup_needed(raw):
                start = time.perf_counter()
                try:
                    if self.cleaner_future:
                        self.cleaner_future.result()
                        self.cleaner_future = None
                    candidate = stt.format_transcript(raw, self.cleaner, on_error=error)
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
                    if not self.target_window:
                        raise OSError("no focused target window")
                    insert_text(final, self.target_window)
                except OSError as exc:
                    self.emit("error", {"message": f"Text insertion failed: {exc}"})
                timings["insert_ms"] = round((time.perf_counter() - start) * 1000, 1)
            timings["release_to_ready_ms"] = round((time.perf_counter() - release_at) * 1000, 1)
            self.emit("result", {"raw": raw, "text": final, "timings": timings})
            if self.record_history:
                try:
                    record = history_append(stt.HISTORY_DIR,
                                            {"text": final, "app": (self.foreground or {}).get("process", "")})
                    if record:
                        self.emit("history_added", {"id": record["id"]})
                except OSError as exc:
                    self.emit("error", {"message": f"History could not be saved: {exc}"})
        except Exception as exc:
            logging.exception("dictation failed")
            self.emit("error", {"message": str(exc)})
        finally:
            with self.lock:
                self.segment.clear()
                self.pending.clear()
                self.replaying = False
                self.asr_used = time.monotonic()
                self._state("idle")

    def close(self):
        self.hotkey_enabled = False
        self.stopping.set()
        self.level_wakeup.set()
        self.hotkey_events.put(None)
        with self.lock:
            if self.stream:
                self.stream.stop()
                self.stream.close()
            if self.cleaner:
                self.cleaner.close()
            self.executor.shutdown(wait=True, cancel_futures=True)
            asr = self.asr_future.result() if self.asr_future else self.asr
            if hasattr(asr, "close"):
                asr.close()
            if self.job:
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
    if os.name == "nt":
        import msvcrt
        instance = (APP_DIR / "engine.lock").open("a+b")
        instance.write(b"1")
        instance.flush()
        instance.seek(0)
        try:
            msvcrt.locking(instance.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise RuntimeError("engine is already running") from exc
    logging.basicConfig(filename=LOG, level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(message)s")
    try:
        history_compact(stt.HISTORY_DIR)
    except (OSError, ValueError):
        logging.exception("history compaction failed")
    try:
        engine = DictationEngine(capture=capture, hotkey=hotkey)
    except Exception:
        logging.exception("engine startup failed")
        raise
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
    parser.add_argument("action", nargs="?", default="serve", choices=("serve", "setup"))
    parser.add_argument("--no-mic", action="store_true")
    parser.add_argument("--hotkey", action="store_true")
    parser.add_argument("--cleanup", action="store_true", help="Download optional cleanup files during setup")
    options = parser.parse_args()
    if options.action == "setup":
        from model_manager import setup_models
        try:
            setup_models(cleanup=options.cleanup)
        except (OSError, ValueError, MemoryError) as exc:
            print(f"Model setup could not finish: {exc}. Launch WaveType to retry.", file=sys.stderr)
            raise SystemExit(1)
    else:
        serve(capture=not options.no_mic, hotkey=options.hotkey)
