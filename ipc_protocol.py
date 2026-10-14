"""Shared endpoint location without importing the inference engine."""

import os
from pathlib import Path


APP_DIR = Path(os.environ.get("LOCALAPPDATA", Path.home())) / "STTCore"
ENDPOINT = APP_DIR / "endpoint.json"
