"""Generate Windows version metadata and an exact, privacy-checked bundle manifest."""

import argparse
import hashlib
import importlib.metadata
import json
import re
import struct
import shutil
import sys
from pathlib import Path


def versions(version):
    match = re.fullmatch(r"(\d+)\.(\d+)\.(\d+)(?:-[a-zA-Z0-9.-]+)?", version)
    if not match:
        raise ValueError("use a semantic version, for example 0.1.0-beta.1")
    numeric = (*map(int, match.groups()), 0)
    if any(number > 65535 for number in numeric):
        raise ValueError("Windows version components must be at most 65535")
    return numeric


def prepare(version):
    numeric = versions(version)
    Path("build").mkdir(exist_ok=True)
    for name, description in (("WaveType", "WaveType local dictation"),
                              ("WaveTypeEngine", "WaveType local speech engine")):
        source = f"""VSVersionInfo(
  ffi=FixedFileInfo(filevers={numeric!r}, prodvers={numeric!r}, mask=0x3f,
                   flags=0x0, OS=0x40004, fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[StringFileInfo([StringTable('040904B0', [
    StringStruct('CompanyName', 'ABhattacharya-dev'),
    StringStruct('FileDescription', {description!r}),
    StringStruct('FileVersion', {version!r}),
    StringStruct('InternalName', {name!r}),
    StringStruct('OriginalFilename', {f'{name}.exe'!r}),
    StringStruct('ProductName', 'WaveType'),
    StringStruct('ProductVersion', {version!r}),
    StringStruct('LegalCopyright', 'WaveType contributors')
  ])]), VarFileInfo([VarStruct('Translation', [1033, 1200])])]
)
"""
        Path(f"build/{name}-version.txt").write_text(source, encoding="utf-8")


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def require_x64(path):
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            raise ValueError(f"not a Windows executable: {path}")
        stream.seek(0x3C)
        offset = struct.unpack("<I", stream.read(4))[0]
        stream.seek(offset)
        if stream.read(4) != b"PE\0\0" or struct.unpack("<H", stream.read(2))[0] != 0x8664:
            raise ValueError(f"not an AMD64 executable: {path}")


def manifest(bundle, version):
    versions(version)
    bundle = bundle.resolve()
    require_x64(bundle / "WaveType.exe")
    require_x64(bundle / "engine" / "WaveTypeEngine.exe")
    dependencies = {}
    for name in ("sounddevice", "cffi", "pycparser", "webrtcvad-wheels"):
        distribution = importlib.metadata.distribution(name)
        dependencies[name] = distribution.version
        for entry in distribution.files or []:
            if entry.name.upper().startswith(("LICENSE", "COPYING", "COPYRIGHT")):
                target = bundle / "licenses" / f"{name}-{entry.name}.txt"
                shutil.copy2(distribution.locate_file(entry), target)
    shutil.copy2(Path(sys.base_prefix) / "LICENSE.txt", bundle / "licenses" / "Python-LICENSE.txt")
    (bundle / "build-info.json").write_text(json.dumps({
        "version": version, "python": sys.version.split()[0],
        "pyinstaller": importlib.metadata.version("pyinstaller"), "dependencies": dependencies,
    }, indent=2) + "\n", encoding="utf-8")
    files = []
    for path in sorted(bundle.rglob("*")):
        if not path.is_file() or path.name == "install-manifest.json":
            continue
        relative = path.relative_to(bundle)
        if (path.suffix.lower() in (".gguf", ".wav", ".jsonl", ".part", ".pfx", ".pem") or
                path.name in ("personal_terms.json", "personal_vocabulary.json", "ui.json", "endpoint.json") or
                any(part in ("history", ".venv", "artifacts") for part in relative.parts)):
            raise ValueError(f"private or model file must not be bundled: {relative}")
        files.append({"path": relative.as_posix(), "bytes": path.stat().st_size, "sha256": sha256(path)})
    (bundle / "install-manifest.json").write_text(json.dumps({
        "product": "WaveType", "version": version, "architecture": "x64", "files": files,
    }, indent=2) + "\n", encoding="utf-8")

    def escape(text):
        return text.replace("$", "$$").replace('"', '$\\"')

    lines = []
    for relative in [row["path"] for row in files] + ["install-manifest.json"]:
        target = '$INSTDIR\\' + escape(relative.replace('/', chr(92)))
        lines.extend([f'IfFileExists "{target}" 0 +4', f'Delete "{target}"',
                      f'IfFileExists "{target}" 0 +2', 'StrCpy $RemovalFailed 1'])
    directories = sorted((path.relative_to(bundle) for path in bundle.rglob("*") if path.is_dir()),
                         key=lambda path: len(path.parts), reverse=True)
    lines.extend(f'RMDir "$INSTDIR\\{escape(str(path))}"' for path in directories)
    Path("build/uninstall-files.nsh").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"Manifest: {len(files)} files, x64 executables, no models or personal data bundled.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("action", choices=("prepare", "manifest"))
    parser.add_argument("--version", required=True)
    parser.add_argument("--bundle", type=Path, default=Path("dist/WaveType"))
    args = parser.parse_args()
    if args.action == "prepare":
        prepare(args.version)
    else:
        manifest(args.bundle, args.version)
