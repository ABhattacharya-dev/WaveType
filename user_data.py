"""Engine-owned personal data and dated dictation history."""

import json
import os
import re
import threading
import uuid
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit


DATA_LOCK = threading.RLock()


def _name_key(value):
    return " ".join(value.casefold().split())


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


def dictionary_set(terms_path, vocabulary_path, kind, entries, shortcuts_path=None):
    if kind not in ("snippets", "vocabulary") or not isinstance(entries, dict):
        raise ValueError("invalid dictionary kind or entries")
    if len(entries) > 1000:
        raise ValueError("too many dictionary entries")
    normalized_keys = set()
    aliases = {}
    for key, value in entries.items():
        if not isinstance(key, str) or not key.strip() or len(key) > 120:
            raise ValueError("dictionary keys must be nonempty text up to 120 characters")
        normalized = _name_key(key)
        if normalized in normalized_keys:
            raise ValueError("duplicate dictionary key")
        normalized_keys.add(normalized)
        if kind == "snippets":
            if not isinstance(value, str) or len(value) > 4000:
                raise ValueError("snippet values must be text up to 4000 characters")
        elif not isinstance(value, list) or any(not isinstance(alias, str) or not alias.strip()
                                                or len(alias) > 120 for alias in value):
            raise ValueError("vocabulary values must be lists of nonempty aliases")
        if kind == "vocabulary":
            for alias in value:
                candidate = alias.strip().casefold()
                if candidate in aliases and aliases[candidate] != key:
                    raise ValueError("ambiguous vocabulary alias")
                aliases[candidate] = key
    path = terms_path if kind == "snippets" else vocabulary_path
    with DATA_LOCK:
        if kind == "snippets":
            shortcuts_path = shortcuts_path or Path(terms_path).with_name("shortcuts.json")
            if normalized_keys & {_name_key(name) for name in shortcuts_get(shortcuts_path)}:
                raise ValueError("snippet key already used by a shortcut")
        _atomic(path, json.dumps(entries, ensure_ascii=False, indent=2) + "\n")
    return {"kind": kind, "count": len(entries)}


def shortcuts_get(path):
    with DATA_LOCK:
        return _validated_shortcuts(_read_json(path))


def _validated_shortcuts(entries):
    if not isinstance(entries, dict) or len(entries) > 1000:
        raise ValueError("shortcuts must be an object with at most 1000 entries")
    normalized = set()
    clean = {}
    for name, record in entries.items():
        if (not isinstance(name, str) or not name.strip() or len(name) > 120 or
                any(ord(char) < 32 for char in name)):
            raise ValueError("shortcut names must be nonempty text up to 120 characters")
        key = _name_key(name)
        if key in normalized:
            raise ValueError("duplicate shortcut name")
        normalized.add(key)
        if not isinstance(record, dict) or set(record) != {"type", "target"}:
            raise ValueError("shortcut must have type and target")
        kind, target = record["type"], record["target"]
        if kind not in ("app", "directory", "url") or not isinstance(target, str):
            raise ValueError("invalid shortcut type or target")
        target = target.strip()
        if not target or len(target) > 2048 or any(ord(char) < 32 for char in target):
            raise ValueError("shortcut target must be nonempty text up to 2048 characters")
        if kind in ("app", "directory"):
            if not Path(target).is_absolute():
                raise ValueError("app and folder paths must be absolute")
            if kind == "app" and Path(target).suffix.lower() not in (".exe", ".lnk"):
                raise ValueError("app path must end in .exe or .lnk")
        else:
            try:
                url = urlsplit(target)
                if (url.scheme not in ("http", "https") or not url.hostname or
                        any(char.isspace() for char in target)):
                    raise ValueError()
                url.port
            except ValueError as exc:
                raise ValueError("website URL must be a valid http or https address") from exc
        clean[name.strip()] = {"type": kind, "target": target}
    return clean


def shortcuts_set(path, terms_path, entries):
    clean = _validated_shortcuts(entries)
    with DATA_LOCK:
        if {_name_key(name) for name in clean} & {_name_key(name) for name in _read_json(terms_path)}:
            raise ValueError("shortcut name already used by a snippet")
        _atomic(path, json.dumps(clean, ensure_ascii=False, indent=2) + "\n")
    return clean


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
        app = value.get("app") or ""
        if isinstance(app, dict):
            app = app.get("process") or ""
        rows.append({"id": f"{path.stem}:{number}", "date": path.stem,
                     "time": value.get("time", ""), "text": value.get("text", ""),
                     "app": str(app)})
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


def history_append(directory, record):
    if not record.get("text", "").strip():
        return None
    now = datetime.now().astimezone()
    app = record.get("app") or ""
    if isinstance(app, dict):
        app = app.get("process") or ""
    record = {"date": now.date().isoformat(), "time": now.timetz().isoformat(timespec="seconds"),
              "text": record["text"], "app": str(app)}
    path = Path(directory) / f"{record['date']}.jsonl"
    with DATA_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            with path.open(encoding="utf-8") as source:
                number = sum(1 for _ in source) + 1
        else:
            number = 1
        with path.open("a", encoding="utf-8") as output:
            output.write(json.dumps(record, ensure_ascii=False) + "\n")
    return {"id": f"{record['date']}:{number}", **record}


def history_change(directory, record_id, action):
    if action != "delete" or not isinstance(record_id, str):
        raise ValueError("invalid history action")
    day, separator, number = record_id.partition(":")
    try:
        valid = separator and datetime.fromisoformat(day).date().isoformat() == day and int(number) > 0
    except ValueError:
        valid = False
    if not valid:
        raise ValueError("invalid history id")
    with DATA_LOCK:
        path = Path(directory) / f"{day}.jsonl"
        rows = _records(path)
        index = next((index for index, row in enumerate(rows) if row["id"] == record_id), None)
        if index is None:
            raise ValueError("history entry not found")
        rows.pop(index)
        if rows:
            _atomic(path, "".join(json.dumps({key: row[key] for key in ("date", "time", "text", "app")},
                                             ensure_ascii=False) + "\n" for row in rows))
        else:
            path.unlink(missing_ok=True)


def history_compact(directory):
    """Keep final text and discard WAVs generated by earlier engine versions."""
    with DATA_LOCK:
        for path in _history_files(directory):
            rows = _records(path)
            compact = "".join(json.dumps({key: row[key] for key in ("date", "time", "text", "app")},
                                         ensure_ascii=False) + "\n" for row in rows)
            if path.read_text(encoding="utf-8") != compact:
                _atomic(path, compact)
        audio_dir = Path(directory) / "audio"
        if audio_dir.is_dir():
            for path in audio_dir.glob("*.wav"):
                if re.fullmatch(r"[0-9a-f]{32}\.wav", path.name):
                    path.unlink()
            if not any(audio_dir.iterdir()):
                audio_dir.rmdir()
