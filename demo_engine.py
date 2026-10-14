"""Headless IPC demo: hold, tap, and cancel using a WAV file."""

import argparse
from pathlib import Path

from client import EngineClient


def result(client):
    for event in client.events():
        if event["event"] == "result":
            return event["text"]
        if event["event"] == "error":
            raise RuntimeError(event["message"])


def main(wav):
    client = EngineClient(start=True, no_mic=True)
    try:
        client.command("subscribe")
        client.command("settings", mode="hold", smart=False)
        client.command("replay", path=str(wav))
        client.command("release")
        print("hold:", result(client))
        client.command("replay", path=str(wav))
        client.command("cancel")
        print("cancel: idle" if client.command("status")["state"] == "idle" else "cancel: failed")
        client.command("settings", mode="tap", smart=False)
        client.command("replay", path=str(wav))
        client.command("release")
        client.command("press")
        print("tap:", result(client))
    finally:
        client.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    arguments = parser.parse_args()
    main(arguments.wav.resolve())
