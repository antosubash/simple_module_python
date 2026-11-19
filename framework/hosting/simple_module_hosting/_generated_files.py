"""Content-aware atomic writes for files consumed by frontend tools."""

import os
from pathlib import Path
from tempfile import mkstemp


def _write_if_changed(path: Path, payload: str) -> bool:
    """Publish complete replacements; keep unchanged mtimes to avoid spurious Vite HMR."""
    try:
        if path.read_text(encoding="utf-8") == payload:
            return False
    except FileNotFoundError:
        pass
    fd, name = mkstemp(dir=path.parent, suffix=".tmp")
    temporary = Path(name)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as writer:
            writer.write(payload)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
    return True
