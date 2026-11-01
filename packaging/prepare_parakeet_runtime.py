"""Stage the pinned Parakeet DLL for the Windows installer without committing binaries."""

import argparse
import hashlib
import sys
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from model_manager import ASR_LIBRARY, ASR_LIBRARY_DLL_SHA256, fetch  # noqa: E402


DLL_IN_ARCHIVE = "parakeet-v0.6.1-lib-win-cpu-x64/parakeet.dll"


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def prepare(destination, archive):
    destination = Path(destination)
    if destination.is_file() and sha256(destination.read_bytes()) == ASR_LIBRARY_DLL_SHA256:
        return destination
    archive = fetch(archive, *ASR_LIBRARY)
    with zipfile.ZipFile(archive) as contents:
        dll = contents.read(DLL_IN_ARCHIVE)
    if sha256(dll) != ASR_LIBRARY_DLL_SHA256:
        raise ValueError("Pinned Parakeet archive contains an unexpected runtime DLL.")
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_suffix(".tmp")
    temporary.write_bytes(dll)
    temporary.replace(destination)
    return destination


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--destination", type=Path, default=ROOT / "build" / "parakeet-runtime" / "parakeet.dll")
    parser.add_argument("--archive", type=Path, default=ROOT / "build" / "parakeet-lib.zip")
    args = parser.parse_args()
    print(f"Verified bundled Parakeet DLL: {prepare(args.destination, args.archive)}")
