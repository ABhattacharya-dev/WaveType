"""GitHub release discovery and resumable, verified installer downloads."""

import hashlib
import json
import os
import queue
import re
import threading
import time
import urllib.request
from pathlib import Path


RELEASE_API = "https://api.github.com/repos/ABhattacharya-dev/WaveType/releases?per_page=30"
CHECK_INTERVAL = 24 * 60 * 60
MANUAL_COOLDOWN = 60
MAX_CHECKSUM_BYTES = 64 * 1024
VERSION = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)-beta1\.(\d+)$")


def version_key(value):
    match = VERSION.fullmatch(value)
    return tuple(map(int, match.groups())) if match else None


def select_release(releases, current):
    baseline = version_key(current)
    if baseline is None:
        return None
    candidates = []
    for release in releases:
        version = release.get("tag_name", "")
        key = version_key(version)
        if release.get("draft") or key is None or key <= baseline:
            continue
        name = f"WaveType-{version.removeprefix('v')}-Setup-x64.exe"
        assets = {item.get("name"): item for item in release.get("assets", [])}
        installer, checksums = assets.get(name), assets.get("SHA256SUMS.txt")
        if installer and checksums and installer.get("size", 0) > 0:
            candidates.append((key, {"version": version.removeprefix("v"),
                                     "installer": installer, "checksums": checksums}))
    return max(candidates, default=(None, None))[1]


def checksum_for(text, filename):
    for line in text.splitlines():
        match = re.fullmatch(r"([0-9a-fA-F]{64})\s+\*?(.+)", line.strip())
        if match and match.group(2) == filename:
            return match.group(1).lower()
    raise ValueError("The release has no SHA-256 checksum for its installer.")


def _github_request(url):
    if not url.startswith(("https://api.github.com/repos/ABhattacharya-dev/WaveType/",
                           "https://github.com/ABhattacharya-dev/WaveType/releases/download/")):
        raise ValueError("Unexpected release download address.")
    return urllib.request.Request(url, headers={"User-Agent": "WaveType-Updater",
                                                "Accept": "application/vnd.github+json"})


def installed_version(executable):
    try:
        value = json.loads((Path(executable).parent / "build-info.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        return None
    return value if version_key(value) else None


class UpdateManager:
    def __init__(self, directory, current_version, opener=None):
        self.directory = Path(directory) / "updates"
        self.current_version = current_version
        self.opener = opener or urllib.request.urlopen
        self.events = queue.SimpleQueue()
        self.release = None
        self.expected_hash = None
        self.busy = False
        self.last_check = float("-inf")
        self.last_auto_check = float("-inf")
        self.stop = threading.Event()
        self.stop_action = None
        self.state = "idle"

    def _emit(self, state, **details):
        self.state = state
        self.events.put({"state": state, **details})

    def check(self, automatic=False):
        now = time.monotonic()
        if self.busy or now - self.last_check < MANUAL_COOLDOWN:
            return False
        if automatic and now - self.last_auto_check < CHECK_INTERVAL:
            return False
        self.last_check = now
        if automatic:
            self.last_auto_check = now
        self.busy = True
        self._emit("checking")
        threading.Thread(target=self._check, args=(automatic,), daemon=True).start()
        return True

    def _check(self, automatic):
        try:
            with self.opener(_github_request(RELEASE_API), timeout=15) as response:
                releases = json.load(response)
            if not isinstance(releases, list):
                raise ValueError("The release feed was invalid.")
            release = select_release(releases, self.current_version)
            if release is None:
                self.release = None
                self._emit("current")
                return
            checksum_asset = release["checksums"]
            with self.opener(_github_request(checksum_asset["browser_download_url"]), timeout=15) as response:
                checksum_text = response.read(MAX_CHECKSUM_BYTES + 1)
            if len(checksum_text) > MAX_CHECKSUM_BYTES:
                raise ValueError("The release checksum file is too large.")
            expected = checksum_for(checksum_text.decode("utf-8"), release["installer"]["name"])
            self.release, self.expected_hash = release, expected
            self._emit("available", version=release["version"])
        except (OSError, ValueError, KeyError, TypeError, UnicodeError) as exc:
            self._emit("error", message=f"Could not check for updates: {exc}")
        finally:
            self.busy = False
            if automatic and self.state == "available":
                self.download()

    def download(self):
        if self.busy or not self.release or not self.expected_hash:
            return False
        self.stop.clear()
        self.stop_action = None
        self.busy = True
        threading.Thread(target=self._download, daemon=True).start()
        return True

    def pause(self):
        if self.busy and self.state == "downloading":
            self.stop_action = "paused"
            self.stop.set()
            return True
        return False

    def cancel(self):
        if self.busy and self.state == "downloading":
            self.stop_action = "canceled"
            self.stop.set()
            return True
        if self.release:
            self._files()[0].unlink(missing_ok=True)
            self._files()[1].unlink(missing_ok=True)
            self._emit("canceled")
            return True
        return False

    def _files(self):
        name = self.release["installer"]["name"]
        return self.directory / (name + ".part"), self.directory / name

    def ready_installer(self):
        if self.state != "ready" or not self.release:
            return None
        return self._files()[1]

    def _download(self):
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            partial, final = self._files()
            expected_size = self.release["installer"]["size"]
            if final.exists() and final.stat().st_size == expected_size and self._hash(final) == self.expected_hash:
                self._emit("ready", version=self.release["version"])
                return
            final.unlink(missing_ok=True)
            offset = partial.stat().st_size if partial.exists() else 0
            if offset > expected_size:
                partial.unlink()
                offset = 0
            headers = {"Range": f"bytes={offset}-"} if offset else {}
            request = _github_request(self.release["installer"]["browser_download_url"])
            request.headers.update(headers)
            with self.opener(request, timeout=30) as response:
                status = getattr(response, "status", 200)
                if offset and status != 206:
                    offset = 0
                if status not in (200, 206):
                    raise ValueError(f"Download returned HTTP {status}.")
                if status == 206 and response.headers.get("Content-Range", "").split("/", 1)[-1] != str(expected_size):
                    raise ValueError("The resumed download has an unexpected size.")
                if status == 206 and not response.headers.get("Content-Range", "").startswith(f"bytes {offset}-"):
                    raise ValueError("The server resumed at the wrong offset.")
                with partial.open("ab" if offset else "wb") as output:
                    received = offset
                    self._emit("downloading", received=received, total=expected_size)
                    while True:
                        if self.stop.is_set():
                            if self.stop_action == "canceled":
                                output.close()
                                partial.unlink(missing_ok=True)
                            self._emit(self.stop_action or "paused")
                            return
                        block = response.read(256 * 1024)
                        if not block:
                            break
                        received += len(block)
                        if received > expected_size:
                            raise ValueError("The installer exceeded its published size.")
                        output.write(block)
                        self._emit("downloading", received=received, total=expected_size)
            if partial.stat().st_size != expected_size or self._hash(partial) != self.expected_hash:
                partial.unlink(missing_ok=True)
                raise ValueError("The installer failed its SHA-256 check.")
            os.replace(partial, final)
            self._emit("ready", version=self.release["version"])
        except (OSError, ValueError, KeyError) as exc:
            self._emit("error", message=f"Could not download the update: {exc}")
        finally:
            self.busy = False

    @staticmethod
    def _hash(path):
        digest = hashlib.sha256()
        with path.open("rb") as source:
            for block in iter(lambda: source.read(1024 * 1024), b""):
                digest.update(block)
        return digest.hexdigest()
