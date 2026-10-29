"""Exercise the packaged engine offline with disposable local data only."""
import argparse
import json
import os
import socket
import subprocess
import tempfile
import time
from pathlib import Path


def run(executable):
    with tempfile.TemporaryDirectory(prefix="wavetype-smoke-") as folder:
        root = Path(folder)
        data = root / "STTCore"
        runtime = data / "runtime"
        runtime.mkdir(parents=True)
        history = data / "history" / "keep.txt"
        history.parent.mkdir()
        history.write_text("preserve history", encoding="utf-8")
        settings = data / "ui.json"
        settings.write_text('{"smart": false}', encoding="utf-8")
        for relative in ("Qwen3-4B-Instruct-2507-Q4_K_M.gguf", "smart/llama-server.exe",
                         "smart-cpu/llama-server.exe", "llama-b11564-bin-win-cpu-x64.zip.part"):
            path = runtime / relative
            path.parent.mkdir(exist_ok=True)
            path.write_bytes(b"isolated test fixture")
        environment = {**os.environ, "LOCALAPPDATA": str(root), "STT_RUNTIME_DIR": str(runtime),
                       "HTTPS_PROXY": "http://127.0.0.1:9", "HTTP_PROXY": "http://127.0.0.1:9",
                       "NO_PROXY": ""}
        for restart in range(2):
            process = subprocess.Popen([str(executable), "serve", "--no-mic"], env=environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                endpoint = data / "endpoint.json"
                deadline = time.monotonic() + 20
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Packaged engine exited during startup")
                    try:
                        info = json.loads(endpoint.read_text())
                        if info["pid"] == process.pid:
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError("Engine endpoint not ready")
                    time.sleep(.1)
                with socket.create_connection(("127.0.0.1", info["port"]), timeout=40) as connection:
                    with connection.makefile("rwb") as stream:
                        def command(name, **args):
                            stream.write(json.dumps({"id": 1, "token": info["token"], "command": name,
                                                     "args": args}).encode() + b"\n")
                            stream.flush()
                            result = json.loads(stream.readline())
                            if not result["ok"]:
                                raise RuntimeError(result["error"])
                            return result["result"]

                        def settled(name):
                            deadline = time.monotonic() + 35
                            while time.monotonic() < deadline:
                                value = command("model_status")["models"][name]
                                if value["state"] not in ("verifying", "downloading", "deleting", "pausing", "canceling"):
                                    return value
                                time.sleep(.1)
                            raise TimeoutError("Model operation did not finish")

                        command("settings", smart=False, mode="hold")
                        asr = settled("asr")
                        if restart == 0:
                            assert asr["state"] == "failed", asr
                            settled("cleanup")
                            command("model_delete", model="cleanup")
                            assert settled("cleanup")["disk_bytes"] == 0
                            command("model_delete", model="asr")
                            assert settled("asr")["disk_bytes"] == 0
                        else:
                            assert asr["state"] == "missing" and asr["disk_bytes"] == 0, asr
                            assert settled("cleanup")["state"] == "missing"
                        command("shutdown")
                assert process.wait(timeout=10) == 0
                assert history.read_text() == "preserve history"
                assert settings.read_text() == '{"smart": false}'
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
        print("PASS: packaged offline startup, Settings IPC, both model deletions, CPU/GPU cleanup, "
              "restart persistence, personal-data preservation and graceful shutdown.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    run(parser.parse_args().executable.resolve())
