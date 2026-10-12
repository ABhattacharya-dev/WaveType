"""Pinned, resumable first-run downloads; never used after files are installed."""

import hashlib
import os
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path

import smart
import stt


ASR = ("https://huggingface.co/mudler/parakeet-cpp-gguf/resolve/main/redux-q8_0.gguf",
       "3429a4598946c406dbb4af5bb589d4dd307b069d550d98e24bef6779c4e6988f")
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
    offset = partial.stat().st_size if partial.exists() else 0
    request = urllib.request.Request(url, headers={"Range": f"bytes={offset}-"} if offset else {})
    with urllib.request.urlopen(request, timeout=60) as response:
        append = offset and response.status == 206
        with partial.open("ab" if append else "wb") as output:
            shutil.copyfileobj(response, output, 1024 * 1024)
    if _sha256(partial) != expected:
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


def ensure_asr():
    fetch(stt.RUNTIME / "redux-q8_0.gguf", *ASR)
    if not (stt.RUNTIME / "parakeet-cli.exe").is_file():
        raise FileNotFoundError("parakeet-cli.exe is missing from runtime")


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


def ensure_cleanup():
    fetch(smart.MODEL, *CLEANUP)
    gpu = gpu_available()
    destination = smart.RUNTIME / ("smart" if gpu else "smart-cpu")
    if not (destination / "llama-server.exe").is_file():
        packages = (GPU, CUDART) if gpu else (CPU,)
        for filename, digest in packages:
            archive = fetch(smart.RUNTIME / filename, RELEASE + filename, digest)
            _extract(archive, destination)
            archive.unlink()
    return destination / "llama-server.exe", 99 if gpu else 0
