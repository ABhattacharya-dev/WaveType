"""User supplied recognition aliases, separate from spoken insert-my snippets."""

import json
import os
import re
import sys
from pathlib import Path


VOCABULARY = (Path(os.environ.get("LOCALAPPDATA", Path.home())) / "STTCore" /
              "personal_vocabulary.json" if getattr(sys, "frozen", False) else
              Path(__file__).with_name("personal_vocabulary.json"))


def apply_vocabulary(text, path=VOCABULARY):
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return text
    if not isinstance(entries, dict):
        raise ValueError("personal_vocabulary.json must be an object")
    aliases = {}
    for canonical, variants in entries.items():
        if not isinstance(canonical, str) or not canonical.strip() or not isinstance(variants, list):
            raise ValueError("invalid personal vocabulary entry")
        for variant in variants:
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError("invalid personal vocabulary alias")
            key = variant.strip().casefold()
            if key in aliases and aliases[key] != canonical:
                raise ValueError("ambiguous personal vocabulary alias")
            aliases[key] = canonical
    if not aliases:
        return text
    choices = "|".join(re.escape(alias) for alias in sorted(aliases, key=len, reverse=True))
    pattern = re.compile(r"(?<!\w)(?:" + choices + r")(?!\w)", re.I)
    return pattern.sub(lambda match: aliases[match.group().casefold()], text)
