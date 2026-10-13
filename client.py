"""Minimal JSON-lines client for the local engine."""

import json
import socket
import subprocess
import sys
import time
from pathlib import Path
from collections import deque

from ipc_protocol import ENDPOINT


class EngineClient:
    def __init__(self, start=False, no_mic=False):
        if start and not self._reachable():
            flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
            executable = (Path(sys.executable).parent / "engine" / "STTEngine.exe"
                          if getattr(sys, "frozen", False) else None)
            command = ([str(executable), "serve"] if executable else
                       [sys.executable, str(Path(__file__).with_name("engine.py")), "serve"])
            if executable and not executable.is_file():
                raise FileNotFoundError(f"bundled engine is missing: {executable}")
            process = subprocess.Popen([*command, *(["--no-mic"] if no_mic else [])], stdin=subprocess.DEVNULL,
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                             creationflags=flags, close_fds=True)
            deadline = time.monotonic() + 3600
            while time.monotonic() < deadline and not self._reachable():
                if process.poll() is not None:
                    raise RuntimeError("engine startup failed; see engine.log")
                time.sleep(0.1)
        info = json.loads(ENDPOINT.read_text(encoding="utf-8"))
        self.token = info["token"]
        self.sock = socket.create_connection(("127.0.0.1", info["port"]), timeout=180)
        self.file = self.sock.makefile("rwb")
        self.next_id = 0
        self.backlog = deque()

    @staticmethod
    def _reachable():
        try:
            info = json.loads(ENDPOINT.read_text(encoding="utf-8"))
            with socket.create_connection(("127.0.0.1", info["port"]), timeout=0.5) as connection:
                connection.sendall(json.dumps({"id": 0, "token": info["token"],
                                               "command": "status"}).encode("utf-8") + b"\n")
                with connection.makefile("rb") as response:
                    return bool(json.loads(response.readline()).get("ok"))
        except (OSError, ValueError, KeyError):
            return False

    def command(self, name, **args):
        self.next_id += 1
        request_id = self.next_id
        self.file.write(json.dumps({"id": request_id, "token": self.token,
                                    "command": name, "args": args}).encode("utf-8") + b"\n")
        self.file.flush()
        while True:
            response = json.loads(self.file.readline())
            if response.get("id") == request_id:
                if not response["ok"]:
                    raise RuntimeError(response["error"])
                return response.get("result")
            self.backlog.append(response)

    def events(self):
        while self.backlog:
            event = self.backlog.popleft()
            if "event" in event:
                yield event
        for line in self.file:
            event = json.loads(line)
            if "event" in event:
                yield event

    def close(self):
        self.file.close()
        self.sock.close()


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("--mode", choices=("hold", "tap"), default="hold")
    parser.add_argument("--smart", action="store_true")
    options = parser.parse_args()
    client = EngineClient(start=True, no_mic=True)
    client.command("settings", mode=options.mode, smart=options.smart)
    client.command("subscribe")
    client.command("replay", path=str(options.wav))
    client.command("press" if options.mode == "tap" else "release")
    for event in client.events():
        if event["event"] == "result":
            print(event["text"])
            print(json.dumps(event["timings"]))
            break
        if event["event"] == "error":
            print(event["message"], file=sys.stderr)
            break
    client.close()
