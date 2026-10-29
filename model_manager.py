"""Pinned, resumable first-run downloads; never used after files are installed."""

import hashlib
import ctypes
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.request
import urllib.error
import zipfile
from pathlib import Path

import smart
import stt
from model_files import files_under, remove_owned


ASR = ("https://huggingface.co/mudler/parakeet-cpp-gguf/resolve/main/redux-q8_0.gguf",
       "3429a4598946c406dbb4af5bb589d4dd307b069d550d98e24bef6779c4e6988f")
ASR_LIBRARY = ("https://github.com/mudler/parakeet.cpp/releases/download/v0.6.1/parakeet-v0.6.1-lib-win-cpu-x64.zip",
               "95b41515efeab246094d1793a1c0a12d727bc1cc01e4c28fe37a16a994b26774")
ASR_LIBRARY_DLL_SHA256 = "173c87722e8c6f1f459fa91878c0f489790a256b858f033fdb63f078b9cf59f0"  # From pinned ZIP.
CLEANUP = ("https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
           "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597")
RELEASE = "https://github.com/ggml-org/llama.cpp/releases/download/b11564/"
CPU = ("llama-b11564-bin-win-cpu-x64.zip", "d2cf631bd9ae31ca6426a691d42d37de2f9ac2985d687ed651b1f45013b23af8")
GPU = ("llama-b11564-bin-win-cuda-12.4-x64.zip", "f09ba10d4b16e04190ef81cedf71f9f262bf1b162855b621261263042d481f69")
CUDART = ("cudart-llama-bin-win-cuda-12.4-x64.zip", "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6")
ASR_LIBRARY_PATH = stt.RUNTIME / "parakeet-lib" / "parakeet-v0.6.1-lib-win-cpu-x64" / "parakeet.dll"
MIN_FREE_BYTES = 128 * 1024 * 1024
_worker_control = threading.local()


class DownloadStopped(Exception):
    def __init__(self, action):
        self.action = action
        super().__init__(action)


def _sha256(path):
    phase = getattr(_worker_control, "verifying", None)
    if phase:
        phase(path)
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            control = getattr(_worker_control, "check", None)
            if control:
                control()
            digest.update(chunk)
    return digest.hexdigest()


def fetch(path, url, expected, progress=None, control=None):
    path = Path(path)
    if path.is_file() and _sha256(path) == expected:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    if partial.exists() and _sha256(partial) == expected:
        partial.replace(path)
        return path
    for attempt in range(2):
        offset = partial.stat().st_size if partial.exists() else 0
        request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
        try:
            response = urllib.request.urlopen(request, timeout=30)
        except urllib.error.HTTPError as exc:
            if offset and exc.code == 416 and attempt == 0:
                partial.unlink(missing_ok=True)
                continue
            raise
        with response:
            content_range = response.headers.get("Content-Range", "")
            valid_range = response.status == 206 and content_range.startswith(f"bytes {offset}-")
            if offset and response.status == 206 and not valid_range:
                if attempt == 0:
                    partial.unlink(missing_ok=True)
                    continue
                raise ValueError(f"invalid download range: {path.name}")
            append = bool(offset and valid_range)
            downloaded = offset if append else 0
            length = int(response.headers.get("Content-Length") or 0)
            total = downloaded + length if length else 0
            if length and shutil.disk_usage(path.parent).free < length + MIN_FREE_BYTES:
                raise OSError(f"Not enough free disk space for {path.name}.")
            with partial.open("ab" if append else "wb") as output:
                if progress:
                    progress(path.name, downloaded, total)
                while True:
                    if control:
                        control()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    output.write(chunk)
                    downloaded += len(chunk)
                    if progress:
                        progress(path.name, downloaded, total)
            if total and downloaded != total:
                raise OSError(f"Download interrupted: {path.name}. Retry to resume.")
        break
    if control:
        control()
    if _sha256(partial) != expected:
        partial.unlink(missing_ok=True)
        raise ValueError(f"Integrity check failed for {path.name}. Retry the download.")
    partial.replace(path)
    return path


def gpu_available():
    try:
        result = subprocess.run(["nvidia-smi", "--query-gpu=memory.total", "--format=csv,noheader,nounits"],
                                capture_output=True, text=True, timeout=3)
        return result.returncode == 0 and any(int(x.strip()) >= 3500 for x in result.stdout.splitlines())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        return False


def free_memory_gb():
    if os.name != "nt":
        return float("inf")
    class MEMORYSTATUSEX(ctypes.Structure):
        _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong)] + [
            (name, ctypes.c_ulonglong) for name in (
                "ullTotalPhys", "ullAvailPhys", "ullTotalPageFile", "ullAvailPageFile",
                "ullTotalVirtual", "ullAvailVirtual", "ullAvailExtendedVirtual")]
    state = MEMORYSTATUSEX()
    state.dwLength = ctypes.sizeof(state)
    if not ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(state)):
        return float("inf")
    return state.ullAvailPhys / (1024 ** 3)


def ensure_asr(progress=None, control=None):
    bundled_cli = Path(getattr(sys, "_MEIPASS", "")) / "runtime" / "parakeet-cli.exe"
    local_cli = stt.RUNTIME / "parakeet-cli.exe"
    if getattr(sys, "frozen", False):
        if not bundled_cli.is_file():
            raise FileNotFoundError("bundled Parakeet CLI is missing")
        if not local_cli.is_file() or _sha256(local_cli) != _sha256(bundled_cli):
            stt.RUNTIME.mkdir(parents=True, exist_ok=True)
            shutil.copy2(bundled_cli, local_cli)
    fetch(stt.RUNTIME / "redux-q8_0.gguf", *ASR, progress=progress, control=control)
    if not local_cli.is_file():
        raise FileNotFoundError("parakeet-cli.exe is missing from runtime")
    if not asr_library_ready():
        archive = fetch(stt.RUNTIME / "parakeet-lib.zip", *ASR_LIBRARY, progress=progress, control=control)
        _extract(archive, stt.RUNTIME / "parakeet-lib", control=control)
        archive.unlink(missing_ok=True)
    return ASR_LIBRARY_PATH


def asr_library_ready():
    return ASR_LIBRARY_PATH.is_file() and _sha256(ASR_LIBRARY_PATH) == ASR_LIBRARY_DLL_SHA256


def _extract(archive, destination, control=None):
    destination.mkdir(parents=True, exist_ok=True)
    receipt = destination / f".{archive.name}.verified.json"
    receipt.unlink(missing_ok=True)
    entries = {}
    with zipfile.ZipFile(archive) as files:
        required = sum(member.file_size for member in files.infolist() if not member.is_dir())
        if shutil.disk_usage(destination).free < required + MIN_FREE_BYTES:
            raise OSError(f"Not enough free disk space to extract {archive.name}.")
        for member in files.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("unsafe runtime archive")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with files.open(member) as source, target.open("wb") as output:
                    while chunk := source.read(1024 * 1024):
                        if control:
                            control()
                        output.write(chunk)
                entries[member.filename] = _sha256(target)
    temporary = receipt.with_suffix(".tmp")
    temporary.write_text(json.dumps(entries), encoding="utf-8")
    temporary.replace(receipt)


def _package_ready(destination, filename):
    try:
        entries = json.loads((destination / f".{filename}.verified.json").read_text(encoding="utf-8"))
        return bool(entries) and all(
            (destination / name).resolve().is_relative_to(destination.resolve()) and
            _sha256(destination / name) == digest for name, digest in entries.items())
    except (OSError, ValueError, TypeError):
        return False


def _legacy_runtime(destination, packages):
    """Earlier releases verified ZIPs before extraction but kept no receipt."""
    return ((destination / "llama-server.exe").is_file() and
            all(not (destination / f".{filename}.verified.json").exists()
                for filename, _ in packages))


def ensure_cleanup(cpu_only=False, progress=None, control=None, require_memory=True,
                   repair_legacy=False):
    gpu = not cpu_only and gpu_available()
    if require_memory and not gpu and free_memory_gb() < 3.5:
        raise MemoryError("not enough free RAM for optional cleanup; use raw dictation")
    fetch(smart.MODEL, *CLEANUP, progress=progress, control=control)
    destination = smart.RUNTIME / ("smart" if gpu else "smart-cpu")
    packages = (GPU, CUDART) if gpu else (CPU,)
    if repair_legacy or not _legacy_runtime(destination, packages):
        for filename, digest in packages:
            if not _package_ready(destination, filename):
                archive = fetch(smart.RUNTIME / filename, RELEASE + filename, digest, progress=progress, control=control)
                _extract(archive, destination, control=control)
                archive.unlink()
    if not (destination / "llama-server.exe").is_file():
        raise FileNotFoundError("Smart cleanup runtime is incomplete. Retry to repair it.")
    return destination / "llama-server.exe", 99 if gpu else 0


def setup_models(cleanup=False):
    """Installer entry point: downloads only, without microphone or model inference."""
    percentages = {}

    def progress(name, downloaded, total):
        percent = int(downloaded * 100 / total) if total else 0
        if percent >= percentages.get(name, -5) + 5:
            percentages[name] = percent
            print(f"Downloading {name}: {percent}% ({downloaded // (1024 * 1024)} MiB)", flush=True)

    print("Preparing Parakeet Redux: downloading and verifying local speech files...", flush=True)
    ensure_asr(progress=progress)
    print("Speech recognition files are ready.", flush=True)
    if cleanup:
        print("Preparing optional Smart cleanup: downloading and verifying Qwen/runtime...", flush=True)
        _, layers = ensure_cleanup(progress=progress)
        print(f"Smart cleanup files are ready ({'NVIDIA GPU' if layers else 'CPU'} tier).", flush=True)
    print("Setup complete. Speech processing runs locally.", flush=True)


class ModelDownloads:
    """Own the two independent download jobs and their UI-visible state."""

    def __init__(self, notify, tier=lambda: "auto", release=lambda name: None):
        self.notify = notify
        self.tier = tier
        self.release = release
        self.lock = threading.RLock()
        self.jobs = {}
        self.stops = {}
        self.intents = {}
        self.states = {name: {"state": "missing", "downloaded": 0, "total": 0,
                              "file": "", "error": "", "legacy": False, "operation": "",
                              "installed": False, "partial": False, "disk_bytes": 0}
                       for name in ("asr", "cleanup")}

    def _persist(self, name, intent):
        with self.lock:
            self.intents[name] = intent

    @staticmethod
    def owned_paths(name):
        if name == "asr":
            paths = [stt.RUNTIME / item for item in ("redux-q8_0.gguf", "parakeet-lib", "parakeet-lib.zip")]
            # The source checkout's CLI is checked in, and the bundled CLI is application code.
            if getattr(sys, "frozen", False):
                paths.append(stt.RUNTIME / "parakeet-cli.exe")
        elif name == "cleanup":
            paths = [smart.MODEL, smart.RUNTIME / "smart", smart.RUNTIME / "smart-cpu"]
            paths += [smart.RUNTIME / filename for filename, _ in (CPU, GPU, CUDART)]
            # Failed older releases may have left archives beside the current runtimes.
            archive = re.compile(r"(?:llama-b\d+-bin-win-(?:cpu|cuda-\d+\.\d+)-x64|cudart-llama-bin-win-cuda-\d+\.\d+-x64)\.zip(?:\.part)?$")
            if smart.RUNTIME.is_dir():
                paths += [p for p in smart.RUNTIME.iterdir() if archive.fullmatch(p.name)]
        else:
            raise ValueError("unknown model")
        return list(dict.fromkeys(paths + [p.with_name(p.name + ".part") for p in paths if p.suffix and p.suffix != ".part"]))

    def _facts(self, name):
        try:
            paths = self.owned_paths(name)
            weights = stt.RUNTIME / "redux-q8_0.gguf" if name == "asr" else smart.MODEL
            size = sum(file.stat().st_size for path in paths for file in files_under(path))
            return {"installed": weights.exists() or any(p.is_dir() for p in paths),
                    "partial": any(p.exists() for p in paths if p.suffix == ".part"), "disk_bytes": size}
        except OSError:
            return {"installed": True, "partial": False, "disk_bytes": None}

    def startup(self, name):
        intent = self.intents.get(name)
        return self.start(name, download=name == "asr" and intent not in ("pause", "cancel", "delete") and not self.intents.get(name + "_error"),
                          automatic=True)

    def snapshot(self):
        with self.lock:
            return {name: value.copy() for name, value in self.states.items()}

    def _set(self, name, **changes):
        with self.lock:
            if (self.states[name]["state"] == "deleting" and changes.get("state") != "deleting"
                    and threading.current_thread() is not self.jobs.get(name)):
                return
            changes.update(self._facts(name))
            if changes.get("state") == "failed":
                try:
                    self._persist(name + "_error", changes.get("error", "Model operation failed"))
                except OSError as exc:
                    changes["error"] += f" (Could not save this status: {exc})"
            self.states[name].update(changes)
            value = self.states[name].copy()
        self.notify({"event": "model_progress", "model": name, **value})

    def _ready(self, name, tier=None):
        if name == "asr":
            local_cli = stt.RUNTIME / "parakeet-cli.exe"
            bundled_cli = Path(getattr(sys, "_MEIPASS", "")) / "runtime" / "parakeet-cli.exe"
            cli_ready = (local_cli.is_file() and
                         (not getattr(sys, "frozen", False) or
                          bundled_cli.is_file() and _sha256(local_cli) == _sha256(bundled_cli)))
            return (cli_ready and
                    (stt.RUNTIME / "redux-q8_0.gguf").is_file() and
                    _sha256(stt.RUNTIME / "redux-q8_0.gguf") == ASR[1] and
                    asr_library_ready())
        gpu = (tier if tier is not None else self.tier()) != "cpu" and gpu_available()
        packages = (GPU, CUDART) if gpu else (CPU,)
        destination = smart.RUNTIME / ("smart" if gpu else "smart-cpu")
        return (smart.MODEL.is_file() and _sha256(smart.MODEL) == CLEANUP[1] and
                (all(_package_ready(destination, filename) for filename, _ in packages) or
                 _legacy_runtime(destination, packages)))

    def _legacy(self, name):
        if name != "cleanup":
            return False
        gpu = self.tier() != "cpu" and gpu_available()
        destination = smart.RUNTIME / ("smart" if gpu else "smart-cpu")
        return _legacy_runtime(destination, (GPU, CUDART) if gpu else (CPU,))

    def start(self, name, download=True, repair=False, automatic=False):
        if name not in self.states:
            raise ValueError("unknown model")
        with self.lock:
            if name in self.jobs and self.jobs[name].is_alive():
                return self.states[name].copy()
            if download and not automatic:
                self._persist(name, "download")
            if not automatic:
                self._persist(name + "_error", "")
            self.stops[name] = None
            self._set(name, state="verifying", operation="verify" if automatic else "repair" if repair else "download" if download else "verify", error="")
            self.jobs[name] = threading.Thread(target=self._run, args=(name, download, repair), daemon=True)
            self.jobs[name].start()
            return self.states[name].copy()

    def stop(self, name, action):
        if name not in self.states or action not in ("pause", "cancel"):
            raise ValueError("invalid model action")
        with self.lock:
            if self.states[name]["state"] == "deleting":
                return self.states[name].copy()
            self._persist(name, action)
            self._persist(name + "_error", "")
            if name in self.jobs and self.jobs[name].is_alive():
                self.stops[name] = action
                self._set(name, state="pausing" if action == "pause" else "canceling")
            elif action == "cancel":
                try:
                    self._clear_partials(name)
                    self._set(name, state="missing", operation="", downloaded=0, total=0, file="", error="")
                except OSError as exc:
                    self._set(name, state="failed", error=f"Could not cancel download: {exc}")
            return self.states[name].copy()

    def delete(self, name):
        if name not in self.states:
            raise ValueError("unknown model")
        with self.lock:
            if self.states[name]["state"] == "deleting":
                return self.states[name].copy()
            self._persist(name, "delete")
            self._persist(name + "_error", "")
            previous = self.jobs.get(name)
            self.stops[name] = "pause"
            self._set(name, state="deleting", operation="delete", error="", total=0, downloaded=0)
            worker = threading.Thread(target=self._delete, args=(name, previous), daemon=True)
            self.jobs[name] = worker
            worker.start()
            return self.states[name].copy()

    def _delete(self, name, previous):
        try:
            if previous:
                previous.join()
            self.release(name)
            root = stt.RUNTIME if name == "asr" else smart.RUNTIME
            for path in self.owned_paths(name):
                remove_owned(path, root)
            if any(os.path.lexists(p) for p in self.owned_paths(name)):
                raise OSError("Some model files remain. Close other WaveType instances and retry deletion.")
            self._set(name, state="missing", operation="", file="", error="", legacy=False)
        except Exception as exc:
            self._set(name, state="failed", operation="delete", error=f"Could not delete model: {exc}")

    def close(self):
        with self.lock:
            jobs = list(self.jobs.items())
            for name, job in jobs:
                if job.is_alive() and self.states[name]["state"] != "deleting":
                    self.stops[name] = "pause"
        for _, job in jobs:
            job.join()

    @staticmethod
    def _clear_partials(name):
        root = stt.RUNTIME if name == "asr" else smart.RUNTIME
        for path in ModelDownloads.owned_paths(name):
            if path.suffix == ".part":
                remove_owned(path, root)

    def _run(self, name, download, repair):
        def control():
            with self.lock:
                action = self.stops[name]
            if action:
                raise DownloadStopped(action)

        def progress(filename, received, total):
            control()
            self._set(name, state="downloading", file=filename,
                      downloaded=received, total=total, error="")

        def verifying(path):
            control()
            self._set(name, state="verifying", file=path.name)

        try:
            _worker_control.check = control
            _worker_control.verifying = verifying
            control()
            self.release(name)
            self._set(name, state="verifying", downloaded=0, total=0, file="", error="")
            if not download and self.intents.get(name + "_error"):
                self._set(name, state="failed", operation="delete" if self.intents.get(name) == "delete" else "",
                          error=self.intents[name + "_error"])
                return
            ready = self._ready(name)
            control()
            legacy = self._legacy(name)
            if ready and not (repair and legacy):
                self._persist(name + "_error", "")
                self._set(name, state="ready", operation="", legacy=legacy)
                return
            control()
            if not download:
                error = self.intents.get(name + "_error", "")
                if self._facts(name)["installed"] and self.intents.get(name) not in ("pause", "cancel"):
                    error = error or "Installed files need repair. Choose Verify / repair."
                self._set(name, state="failed" if error else "paused" if self.intents.get(name) == "pause" or self._facts(name)["partial"] else "missing", operation="", error=error)
                return
            self._set(name, state="downloading", operation="repair" if repair else "download")
            if name == "asr":
                ensure_asr(progress=progress, control=control)
            else:
                ensure_cleanup(cpu_only=self.tier() == "cpu", progress=progress,
                               control=control, require_memory=False, repair_legacy=repair)
            control()
            self._set(name, state="verifying", file="")
            if not self._ready(name):
                raise ValueError("Downloaded files could not be verified. Retry to repair them.")
            self._set(name, state="ready", operation="", downloaded=0, total=0, error="",
                      legacy=self._legacy(name))
        except DownloadStopped as exc:
            if self.states[name]["state"] == "deleting":
                return
            if exc.action == "cancel":
                try:
                    self._clear_partials(name)
                except OSError as error:
                    self._set(name, state="failed", error=f"Could not cancel download: {error}")
                    return
            self._set(name, state="missing" if exc.action == "cancel" else "paused",
                      operation="", file="", error="")
        except (OSError, ValueError, MemoryError, zipfile.BadZipFile) as exc:
            self._set(name, state="failed", error=str(exc), file="")
        finally:
            _worker_control.check = None
            _worker_control.verifying = None
