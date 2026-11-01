"""Confirm the packaged engine rejects an untrusted local HTTPS proxy."""

import argparse
import json
import os
import socket
import socketserver
import ssl
import subprocess
import tempfile
import threading
import time
from pathlib import Path


class Proxy(socketserver.ThreadingTCPServer):
    allow_reuse_address = True
    daemon_threads = True


class ProxyConnection(socketserver.BaseRequestHandler):
    def handle(self):
        request = b""
        while b"\r\n\r\n" not in request and len(request) < 8192:
            block = self.request.recv(4096)
            if not block:
                return
            request += block
        if not request.startswith(b"CONNECT "):
            return
        self.request.sendall(b"HTTP/1.1 200 Connection Established\r\n\r\n")
        try:
            with self.server.context.wrap_socket(self.request, server_side=True):
                pass
        except (OSError, ssl.SSLError):
            pass  # The expected client behavior is to reject this test certificate.


def run(executable, openssl):
    with tempfile.TemporaryDirectory(prefix="wavetype-tls-smoke-") as folder:
        root = Path(folder)
        certificate, key = root / "untrusted.pem", root / "untrusted.key"
        subprocess.run([str(openssl), "req", "-x509", "-newkey", "rsa:2048", "-nodes",
                        "-days", "1", "-subj", "/CN=huggingface.co", "-keyout", str(key),
                        "-out", str(certificate)], check=True, capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        context.load_cert_chain(str(certificate), str(key))
        with Proxy(("127.0.0.1", 0), ProxyConnection) as proxy:
            proxy.context = context
            thread = threading.Thread(target=proxy.serve_forever, daemon=True)
            thread.start()
            runtime = root / "STTCore" / "runtime"
            environment = {**os.environ, "LOCALAPPDATA": str(root),
                           "STT_RUNTIME_DIR": str(runtime),
                           "HTTPS_PROXY": f"http://127.0.0.1:{proxy.server_address[1]}",
                           "HTTP_PROXY": f"http://127.0.0.1:{proxy.server_address[1]}",
                           "NO_PROXY": ""}
            process = subprocess.Popen([str(executable), "serve", "--no-mic"], env=environment,
                                       stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                       stderr=subprocess.DEVNULL,
                                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            try:
                endpoint = root / "STTCore" / "endpoint.json"
                deadline = time.monotonic() + 30
                while True:
                    if process.poll() is not None:
                        raise RuntimeError("Packaged engine exited before creating its endpoint")
                    try:
                        info = json.loads(endpoint.read_text(encoding="utf-8"))
                        if info["pid"] == process.pid:
                            break
                    except (OSError, ValueError):
                        pass
                    if time.monotonic() > deadline:
                        raise TimeoutError("Packaged engine endpoint was not ready")
                    time.sleep(.1)
                with socket.create_connection(("127.0.0.1", info["port"]), timeout=10) as connection:
                    with connection.makefile("rwb") as stream:
                        def command(name):
                            stream.write(json.dumps({"id": 1, "token": info["token"],
                                                     "command": name, "args": {}}).encode() + b"\n")
                            stream.flush()
                            reply = json.loads(stream.readline())
                            if not reply["ok"]:
                                raise RuntimeError(reply["error"])
                            return reply["result"]

                        while time.monotonic() < deadline:
                            state = command("model_status")["models"]["asr"]
                            if state["state"] == "failed":
                                break
                            time.sleep(.1)
                        else:
                            raise TimeoutError("Packaged model download did not fail as expected")
                        if "Parakeet model download failed" not in state["error"] or \
                                "certificate" not in state["error"].casefold():
                            raise AssertionError(f"Unexpected TLS error: {state['error']}")
                        command("shutdown")
                if process.wait(timeout=10) != 0:
                    raise RuntimeError("Packaged engine did not exit cleanly")
            finally:
                if process.poll() is None:
                    process.terminate()
                    process.wait(timeout=10)
                proxy.shutdown()
                thread.join(timeout=5)
        print("PASS: packaged model download rejected an untrusted TLS certificate and named the model failure.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("executable", type=Path)
    parser.add_argument("--openssl", type=Path, required=True)
    args = parser.parse_args()
    run(args.executable.resolve(), args.openssl.resolve())
