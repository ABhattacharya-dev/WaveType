"""Measure replay release-to-result latency with the UI running or closed."""

import argparse
import json
import time
from pathlib import Path

from client import EngineClient
from evaluate import percentile


def run(wav, count=5, smart=False, tier="auto"):
    client = EngineClient(start=True, no_mic=True)
    client.command("settings", mode="hold", smart=smart, tier=tier)
    client.command("subscribe")
    rows = []
    try:
        for attempt in range(count + 1):
            client.command("replay", path=str(Path(wav).resolve()))
            released = time.perf_counter()
            client.command("release")
            for event in client.events():
                if event["event"] == "result":
                    if attempt:
                        rows.append({"wall_ms": round((time.perf_counter() - released) * 1000, 1),
                                     **event["timings"], "text": event["text"]})
                    break
            while client.command("status")["state"] != "idle":
                time.sleep(0.005)
    finally:
        client.close()
    stages = ("wall_ms", "release_to_ready_ms", "asr_ms", "asr_compute_ms", "shortcuts_ms",
              "cleanup_ms", "insert_ms")
    return {"count": len(rows), "tier": tier, "smart": smart, "text": rows[0]["text"],
            "stages": {name: {"p50_ms": percentile([row.get(name, 0) for row in rows], 50),
                              "p95_ms": percentile([row.get(name, 0) for row in rows], 95)}
                       for name in stages}}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wav", type=Path)
    parser.add_argument("--count", type=int, default=5)
    parser.add_argument("--smart", action="store_true")
    parser.add_argument("--tier", choices=("auto", "cpu"), default="auto")
    args = parser.parse_args()
    print(json.dumps(run(args.wav, args.count, args.smart, args.tier), indent=2))
