"""Run offline cleanup fixtures without recording audio or writing user history."""
import argparse
import json
import statistics
import time
from pathlib import Path

from smart import MODEL, SmartCleanup


CASES = [
    ("grammar", "She don't like coffee and he go to work every day.", ["She doesn't like coffee, and he goes to work every day.", "She doesn't like coffee and he goes to work every day."]),
    ("grammar", "Yesterday I go to the store and buy two apple.", ["Yesterday I went to the store and bought two apples."]),
    ("grammar", "Where is the files that you was editing?", ["Where are the files that you were editing?"]),
    ("grammar", "I have been waiting since two hours.", ["I have been waiting for two hours."]),
    ("preserve", "I do not want to cancel the appointment.", ["I do not want to cancel the appointment."]),
    ("preserve", "This is very, very important.", ["This is very, very important."]),
    ("preserve", "Can you explain why the sky is blue?", ["Can you explain why the sky is blue?"]),
    ("correction", "Hello there, let's meet you guys tomorrow at sharp 8pm ooh sorry not 8 lets make it to 7pm.", ["Hello there, let's meet you guys tomorrow at 7 PM sharp.", "Hello there, let's meet you guys tomorrow at 7 PM."]),
    ("correction", "Send it to John, sorry, send it to Jane instead.", ["Send it to Jane instead.", "Send it to Jane."]),
    ("correction", "Order three tickets, no make that four, actually five tickets.", ["Order five tickets."]),
    ("correction", "Let's meet on Monday, sorry Tuesday, at nine.", ["Let's meet on Tuesday at nine.", "Let's meet on Tuesday at 9."]),
    ("json", "Write in JSON format key is name value is AB and key is city value is Kolkata.", {"name": "AB", "city": "Kolkata"}),
    ("json", "Write in JSON format name is AB, age is the number 25, active is boolean true, manager is null.", {"name": "AB", "age": 25, "active": True, "manager": None}),
    ("json", "Write in JSON format user is an object with name AB and age number 25, end user object, tags is an array of strings red and blue.", {"user": {"name": "AB", "age": 25}, "tags": ["red", "blue"]}),
    ("json", "Write in JSON format phone is the string 001234 and count is number three sorry number four.", {"phone": "001234", "count": 4}),
    ("grammar", "I didn't knew that the shops was closed.", ["I didn't know that the shops were closed."]),
    ("correction", "The price is fifteen dollars, sorry, fifty dollars.", ["The price is fifty dollars.", "The price is 50 dollars.", "The price is $50."]),
    ("preserve", "Do not send the file to Jane. Send it to John.", ["Do not send the file to Jane. Send it to John."]),
    ("json", "Write in JSON format settings is an object with enabled boolean false and retries number two, end settings object, title is Draft.", {"settings": {"enabled": False, "retries": 2}, "title": "Draft"}),
    ("correction", "Deliver to 12 Park Road, no, 21 Park Road, tomorrow.", ["Deliver to 21 Park Road tomorrow.", "Deliver to 21 Park Road, tomorrow."]),
    ("correction", "The meeting is Thursday, sorry Wednesday, at noon.", ["The meeting is Wednesday at noon.", "The meeting is on Wednesday at noon."]),
    ("correction", "Email Alex, actually Sam, the updated invoice.", ["Email Sam the updated invoice."]),
    ("grammar", "Neither of these options are available.", ["Neither of these options is available."]),
    ("preserve", "I'm sorry you couldn't attend. We missed you.", ["I'm sorry you couldn't attend. We missed you.", "I'm sorry you couldn't attend—we missed you."]),
    ("json", "Write in JSON format quantity is number eight, no number six, paid is boolean false, note is null.", {"quantity": 6, "paid": False, "note": None}),
    ("correction", "I am looking for a new card—actually, a new phone.", ["I am looking for a new phone.", "I'm looking for a new phone."]),
    ("correction", "Lets see you tomorrow not tomorrow make it today", ["Let's see you today."]),
    ("correction", "Choose the blue shirt, actually the green shirt.", ["Choose the green shirt."]),
    ("correction", "The flight is on Friday not Friday make it Thursday.", ["The flight is on Thursday."]),
    ("correction", "hey are you free today not today make it tomorrow", ["Hey, are you free tomorrow?"]),
    ("correction", "Hey, are you free today? Not today. Make it tomorrow.", ["Hey, are you free tomorrow?"]),
    ("correction", "Hey, are you today? Not today, make it tomorrow.", ["Hey, are you tomorrow?"]),
]


def normalized(text):
    return " ".join(text.lower().replace("’", "'").replace("8pm", "8 pm").replace("7pm", "7 pm").split())


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--model", type=Path, default=MODEL)
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--output", type=Path, default=Path("benchmark-results.json"))
    args = parser.parse_args()
    cleaner = SmartCleanup(args.model)
    records = []
    start = time.perf_counter()
    try:
        cleaner.start()
        startup = time.perf_counter() - start
        print(f"Model ready in {startup:.2f}s.", flush=True)
        for run in range(args.runs):
            for category, source, expected in CASES:
                start = time.perf_counter()
                try:
                    output = cleaner.clean(source, {})
                    passed = (json.dumps(json.loads(output), sort_keys=True) == json.dumps(expected, sort_keys=True) if category == "json" else
                              normalized(output) in [normalized(item) for item in expected])
                    error = None
                except Exception as exc:
                    output, passed, error = None, False, str(exc)
                records.append({"run": run + 1, "category": category, "input": source,
                                "output": output, "passed": passed, "error": error,
                                "seconds": round(time.perf_counter() - start, 4)})
            print(f"Run {run + 1}/{args.runs} complete.", flush=True)
    finally:
        cleaner.close()
    summary = {"model": args.model.name, "startup_seconds": round(startup, 3),
               "cases": len(records), "passed": sum(row["passed"] for row in records),
               "median_seconds": round(statistics.median(row["seconds"] for row in records), 3),
               "max_seconds": max(row["seconds"] for row in records)}
    summary["categories"] = {
        category: {"passed": sum(row["passed"] for row in records if row["category"] == category),
                   "total": sum(row["category"] == category for row in records)}
        for category in sorted({row["category"] for row in records})
    }
    args.output.write_text(json.dumps({"summary": summary, "results": records}, indent=2), encoding="utf-8")
    print(json.dumps(summary))


if __name__ == "__main__":
    main()
