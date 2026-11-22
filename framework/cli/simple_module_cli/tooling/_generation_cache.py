"""Content fingerprints for the generation pipeline (never cache a failed stage)."""

from __future__ import annotations

import hashlib
import json
import os
from collections.abc import Callable, Iterable
from pathlib import Path


def file_hashes(paths: Iterable[Path]) -> dict[str, str | None]:
    result = {}
    for path in sorted(set(paths)):
        result[str(path)] = (
            hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None
        )
    return result


def source_files(root: Path, suffixes: set[str]) -> list[Path]:
    files = []
    for directory, dirs, names in os.walk(root):
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", "tests", "tests-js", "static"}
        ]
        files.extend(Path(directory) / n for n in names if Path(n).suffix in suffixes)
    return files


class GenerationCache:
    def __init__(self, path: Path):
        self.path = path
        try:
            self.state = json.loads(path.read_text(encoding="utf-8"))
            if not isinstance(self.state, dict):
                self.state = {}
        except (OSError, ValueError):
            self.state = {}

    def run(
        self,
        name: str,
        inputs: Callable[[], object],
        outputs: list[Path],
        generate: Callable[[], object],
    ) -> bool:
        def stamp():
            return {"inputs": inputs(), "outputs": file_hashes(outputs)}

        if self.state.get(name) == stamp():
            return False
        generate()
        self.state[name] = stamp()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        # Replace atomically: an interrupted generation must leave a readable cache.
        temporary = self.path.with_suffix(f".{os.getpid()}.tmp")
        temporary.write_text(json.dumps(self.state, sort_keys=True), encoding="utf-8")
        temporary.replace(self.path)
        return True
