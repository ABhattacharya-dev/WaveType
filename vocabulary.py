"""User supplied recognition aliases, separate from spoken insert-my snippets."""

import json
import re
from pathlib import Path


VOCABULARY = Path(__file__).with_name("personal_vocabulary.json")


def apply_vocabulary(text, path=VOCABULARY):
    try:
        entries = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError:
        return text
    if not isinstance(entries, dict):
        raise ValueError("personal_vocabulary.json must be an object")
    aliases = []
    for canonical, variants in entries.items():
        if not isinstance(canonical, str) or not canonical.strip() or not isinstance(variants, list):
            raise ValueError("invalid personal vocabulary entry")
        for variant in variants:
            if not isinstance(variant, str) or not variant.strip():
                raise ValueError("invalid personal vocabulary alias")
            aliases.append((variant.strip(), canonical))
    for variant, canonical in sorted(aliases, key=lambda item: len(item[0]), reverse=True):
        text = re.sub(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", canonical, text, flags=re.I)
    return text
