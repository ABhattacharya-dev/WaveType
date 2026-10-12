"""Replay WAV recordings and compute latency distributions or word error rate."""

import argparse
import json
import re
import statistics
import sys
from pathlib import Path

from client import EngineClient


def words(text):
    return re.findall(r"\w+(?:'\w+)?", text.casefold())


def word_errors(reference, hypothesis):
    expected, actual = words(reference), words(hypothesis)
    previous = list(range(len(actual) + 1))
    for index, word in enumerate(expected, 1):
        current = [index]
        for column, candidate in enumerate(actual, 1):
            current.append(min(current[-1] + 1, previous[column] + 1,
                               previous[column - 1] + (word != candidate)))
        previous = current
    return previous[-1], len(expected)


def percentile(values, percent):
    values = sorted(values)
    return values[max(0, (len(values) * percent + 99) // 100 - 1)]


def run(wavs, smart=False, tier="auto", references=None, warmup=False):
    client = EngineClient(start=True, no_mic=True)
    client.sock.settimeout(180)
    client.command("settings", mode="hold", smart=smart, tier=tier)
    client.command("subscribe")
    rows = []
    try:
        if warmup:
            client.command("replay", path=str(Path(wavs[0]).resolve()))
            client.command("release")
            for event in client.events():
                if event["event"] == "result":
                    break
        for wav in wavs:
            client.command("replay", path=str(Path(wav).resolve()))
            client.command("release")
            for event in client.events():
                if event["event"] == "result":
                    row = {"wav": str(wav), "raw": event["raw"], "text": event["text"],
                           "timings": event["timings"]}
                    if references and str(wav) in references:
                        errors, total = word_errors(references[str(wav)], event["raw"])
                        row["wer"] = errors / total if total else 0.0
                    rows.append(row)
                    break
                if event["event"] == "error":
                    print(event["message"], file=sys.stderr)
    finally:
        client.close()
    stages = sorted({stage for row in rows for stage in row["timings"]})
    summary = {stage: {"p50_ms": percentile([row["timings"].get(stage, 0) for row in rows], 50),
                       "p95_ms": percentile([row["timings"].get(stage, 0) for row in rows], 95)}
               for stage in stages}
    if references:
        summary["mean_wer"] = statistics.mean(row["wer"] for row in rows if "wer" in row)
    return {"tier": tier, "smart": smart, "count": len(rows), "stages": summary, "results": rows}


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("wavs", nargs="*", type=Path)
    parser.add_argument("--manifest", type=Path, help='JSONL rows: {"wav":"path","reference":"spoken words"}')
    parser.add_argument("--smart", action="store_true")
    parser.add_argument("--tier", choices=("auto", "cpu"), default="auto")
    parser.add_argument("--warmup", action="store_true", help="Replay the first WAV once before measuring")
    options = parser.parse_args()
    references = None
    if options.manifest:
        references = {}
        for line in options.manifest.read_text(encoding="utf-8").splitlines():
            item = json.loads(line)
            wav = str((options.manifest.parent / item["wav"]).resolve())
            references[wav] = item["reference"]
        options.wavs = [Path(path) for path in references]
    if not options.wavs:
        parser.error("provide WAV files or --manifest")
    print(json.dumps(run(options.wavs, options.smart, options.tier, references, options.warmup), ensure_ascii=False, indent=2))
