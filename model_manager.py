"""Pinned, resumable first-run downloads; never used after files are installed."""

import hashlib
import ctypes
import os
import shutil
import subprocess
import sys
import urllib.request
import zipfile
from pathlib import Path

import smart
import stt


ASR = ("https://huggingface.co/mudler/parakeet-cpp-gguf/resolve/main/redux-q8_0.gguf",
       "3429a4598946c406dbb4af5bb589d4dd307b069d550d98e24bef6779c4e6988f")
ASR_LIBRARY = ("https://github.com/mudler/parakeet.cpp/releases/download/v0.6.1/parakeet-v0.6.1-lib-win-cpu-x64.zip",
               "95b41515efeab246094d1793a1c0a12d727bc1cc01e4c28fe37a16a994b26774")
CLEANUP = ("https://huggingface.co/unsloth/Qwen3-4B-Instruct-2507-GGUF/resolve/main/Qwen3-4B-Instruct-2507-Q4_K_M.gguf",
           "3605803b982cb64aead44f6c1b2ae36e3acdb41d8e46c8a94c6533bc4c67e597")
RELEASE = "https://github.com/ggml-org/llama.cpp/releases/download/b11564/"
CPU = ("llama-b11564-bin-win-cpu-x64.zip", "d2cf631bd9ae31ca6426a691d42d37de2f9ac2985d687ed651b1f45013b23af8")
GPU = ("llama-b11564-bin-win-cuda-12.4-x64.zip", "f09ba10d4b16e04190ef81cedf71f9f262bf1b162855b621261263042d481f69")
CUDART = ("cudart-llama-bin-win-cuda-12.4-x64.zip", "8c79a9b226de4b3cacfd1f83d24f962d0773be79f1e7b75c6af4ded7e32ae1d6")


def _sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def fetch(path, url, expected):
    path = Path(path)
    if path.is_file() and _sha256(path) == expected:
        return path
    path.parent.mkdir(parents=True, exist_ok=True)
    partial = path.with_name(path.name + ".part")
    if partial.exists() and _sha256(partial) == expected:
        partial.replace(path)
        return path
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    with urllib.request.urlopen(request, timeout=60) as response:
        append = offset and response.status == 206
        with partial.open("ab" if append else "wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
    if _sha256(partial) != expected:
        partial.unlink(missing_ok=True)
        raise ValueError(f"download integrity check failed: {path.name}")
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


def ensure_asr():
    bundled_cli = Path(getattr(sys, "_MEIPASS", "")) / "runtime" / "parakeet-cli.exe"
    if getattr(sys, "frozen", False) and not (stt.RUNTIME / "parakeet-cli.exe").is_file():
        if not bundled_cli.is_file():
            raise FileNotFoundError("bundled Parakeet CLI is missing")
        stt.RUNTIME.mkdir(parents=True, exist_ok=True)
        shutil.copy2(bundled_cli, stt.RUNTIME / "parakeet-cli.exe")
    fetch(stt.RUNTIME / "redux-q8_0.gguf", *ASR)
    if not (stt.RUNTIME / "parakeet-cli.exe").is_file():
        raise FileNotFoundError("parakeet-cli.exe is missing from runtime")
    library = stt.RUNTIME / "parakeet-lib" / "parakeet-v0.6.1-lib-win-cpu-x64" / "parakeet.dll"
    if not library.is_file():
        archive = fetch(stt.RUNTIME / "parakeet-lib.zip", *ASR_LIBRARY)
        _extract(archive, stt.RUNTIME / "parakeet-lib")
        archive.unlink(missing_ok=True)
    return library


def _extract(archive, destination):
    destination.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(archive) as files:
        for member in files.infolist():
            target = (destination / member.filename).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError("unsafe runtime archive")
            if member.is_dir():
                target.mkdir(parents=True, exist_ok=True)
            else:
                target.parent.mkdir(parents=True, exist_ok=True)
                with files.open(member) as source, target.open("wb") as output:
                    shutil.copyfileobj(source, output)


def ensure_cleanup(cpu_only=False):
    gpu = not cpu_only and gpu_available()
    if not gpu and free_memory_gb() < 3.5:
        raise MemoryError("not enough free RAM for optional cleanup; use raw dictation")
    fetch(smart.MODEL, *CLEANUP)
    destination = smart.RUNTIME / ("smart" if gpu else "smart-cpu")
    if not (destination / "llama-server.exe").is_file():
        packages = (GPU, CUDART) if gpu else (CPU,)
        for filename, digest in packages:
            archive = fetch(smart.RUNTIME / filename, RELEASE + filename, digest)
            _extract(archive, destination)
            archive.unlink()
    return destination / "llama-server.exe", 99 if gpu else 0
