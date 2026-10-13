"""Engine-owned personal data and dated dictation history."""

import base64
import json
import os
import threading
import uuid
from datetime import datetime
from pathlib import Path


DATA_LOCK = threading.RLock()


def _read_json(path):
    try:
        value = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    if not isinstance(value, dict):
        raise ValueError(f"{Path(path).name} must contain an object")
    return value


def _atomic(path, content):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(content, encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def dictionary_get(terms_path, vocabulary_path):
    with DATA_LOCK:
        return {"snippets": _read_json(terms_path), "vocabulary": _read_json(vocabulary_path)}


def dictionary_set(terms_path, vocabulary_path, kind, entries):
    if kind not in ("snippets", "vocabulary") or not isinstance(entries, dict):
        raise ValueError("invalid dictionary kind or entries")
    if len(entries) > 1000:
        raise ValueError("too many dictionary entries")
    for key, value in entries.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 120:
            raise ValueError("dictionary keys must be nonempty text up to 120 characters")
        if kind == "snippets":
            if not isinstance(value, str) or len(value) > 4000:
                raise ValueError("snippet values must be text up to 4000 characters")
        elif not isinstance(value, list) or any(not isinstance(alias, str) or not alias.strip()
                                                or len(alias) > 120 for alias in value):
            raise ValueError("vocabulary values must be lists of nonempty aliases")
    path = terms_path if kind == "snippets" else vocabulary_path
    with DATA_LOCK:
        _atomic(path, json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    return {"kind": kind, "count": len(entries)}


def _history_files(directory):
    return sorted(Path(directory).glob("????-??-??.jsonl"), reverse=True)


def _records(path):
    if not path.exists():
        return []
    rows = []
    for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        value = json.loads(line)
        value.setdefault("id", f"{path.stem}:{number}")
        value.setdefault("date", path.stem)
        value.setdefault("raw", value.get("text", ""))
        value.setdefault("plain", value["raw"])
        value.setdefault("cleaned", value.get("text", ""))
        rows.append(value)
    return rows


def history_list(directory, limit=100, offset=0):
    if not isinstance(limit, int) or not 1 <= limit <= 500 or not isinstance(offset, int) or offset < 0:
        raise ValueError("invalid history page")
    with DATA_LOCK:
        rows = []
        for path in _history_files(directory):
            rows.extend(reversed(_records(path)))
            if len(rows) >= offset + limit:
                break
        return rows[offset:offset + limit]


def history_append(directory, record, audio=None):
    if not record.get("text", "").strip():
        return None
    now = datetime.now().astimezone()
    record = {"id": uuid.uuid4().hex, "date": now.date().isoformat(),
              "time": now.timetz().isoformat(timespec="seconds"), **record}
    path = Path(directory) / f"{record['date']}.jsonl"
    with DATA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if audio:
            audio_dir = Path(directory) / "audio"
            audio_dir.mkdir(parents=True, exist_ok=True)
            (audio_dir / f"{record['id']}.wav").write_bytes(audio)
            record["has_audio"] = True
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return record


def history_change(directory, record_id, action, text=None):
    if action not in ("delete", "undo", "retry") or not isinstance(record_id, str):
        raise ValueError("invalid history action")
    with DATA_LOCK:
        for path in _history_files(directory):
            rows = _records(path)
            for index, row in enumerate(rows):
                if row["id"] != record_id:
                    continue
                if action == "delete":
                    rows.pop(index)
                    (Path(directory) / "audio" / f"{record_id}.wav").unlink(missing_ok=True)
                elif action == "undo":
                    row["text"] = row["plain"]
                else:
                    if not isinstance(text, str):
                        raise ValueError("retry requires text")
                    row["cleaned"] = row["text"] = text
                if rows:
                    _atomic(path, "".join(json.dumps(item, ensure_ascii=False) + "\n" for item in rows))
                else:
                    path.unlink(missing_ok=True)
                return None if action == "delete" else row
    raise ValueError("history entry not found")


def history_audio(directory, record_id):
    if not isinstance(record_id, str) or not record_id.isascii() or not record_id.isalnum():
        raise ValueError("invalid audio id")
    path = Path(directory) / "audio" / f"{record_id}.wav"
    if not path.is_file():
        raise FileNotFoundError("audio is unavailable for this entry")
    if path.stat().st_size > 32 * 1024 * 1024:
        raise ValueError("audio is too large to download through IPC")
    return {"name": f"dictation-{record_id}.wav", "base64": base64.b64encode(path.read_bytes()).decode("ascii")}
