"""Ordered, atomic JSON publication for the single-writer reference runtime."""
from __future__ import annotations

import json
import os
from pathlib import Path
import tempfile


def atomic_json(path: Path, value: dict | list) -> None:
    """Publish complete bytes before acknowledging a state or evidence write."""
    data = json.dumps(value, indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    fd, temporary = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        directory = os.open(path.parent, os.O_RDONLY | os.O_DIRECTORY)
        try:
            os.fsync(directory)
        finally:
            os.close(directory)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
