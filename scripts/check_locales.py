"""Check catalogue keys and interpolation placeholders against adjacent en.json files.

Full parity is required for FULL_PARITY languages, including missing catalogues.
Other translations are community-contributed: report differences without failing.
"""

from __future__ import annotations

import json
import os
import re
from collections import Counter
from pathlib import Path

FULL_PARITY = ("de",)
ROOT = Path(__file__).resolve().parent.parent
PLACEHOLDER = re.compile(r"\{\{[^{}]+\}\}|(?<!\{)\{[^{}]+\}(?!\})")


def catalogues(root: Path) -> list[Path]:
    """Find all English locale catalogues without traversing dependencies."""
    found = []
    for directory, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d not in {"node_modules", ".git", ".venv"})
        path = Path(directory)
        if "en.json" in files and "locales" in str(path.relative_to(root)):
            found.append(path / "en.json")
    return sorted(found)


def flatten(data: object, prefix: str = "") -> dict[str, str]:
    """Flatten nested objects, rejecting non-string leaves and ambiguous keys."""
    if not isinstance(data, dict):
        raise ValueError(f"{prefix or '<root>'}: expected an object")
    result: dict[str, str] = {}
    for key, value in data.items():
        name = f"{prefix}.{key}" if prefix else key
        if isinstance(value, dict):
            entries = flatten(value, name)
        elif isinstance(value, str):
            entries = {name: value}
        else:
            raise ValueError(f"{name}: expected a string")
        if result.keys() & entries.keys():
            raise ValueError(f"{name}: duplicate flattened key")
        result.update(entries)
    return result


def load(path: Path) -> dict[str, str]:
    return flatten(json.loads(path.read_text(encoding="utf-8")))


def differences(source: dict[str, str], target: dict[str, str]) -> list[str]:
    problems = []
    for key in sorted(source.keys() - target.keys()):
        problems.append(f"missing key: {key}")
    for key in sorted(target.keys() - source.keys()):
        problems.append(f"extra key: {key}")
    for key in sorted(source.keys() & target.keys()):
        expected = Counter(PLACEHOLDER.findall(source[key]))
        actual = Counter(PLACEHOLDER.findall(target[key]))
        if expected != actual:
            problems.append(
                f"placeholder mismatch: {key}: expected {dict(expected)}, got {dict(actual)}"
            )
    return problems


def check(root: Path = ROOT) -> int:
    failures = reports = checked = 0
    sources = catalogues(root)
    for source_path in sources:
        try:
            source = load(source_path)
        except (OSError, ValueError) as exc:
            print(f"FAIL {source_path.relative_to(root)}: {exc}")
            failures += 1
            continue
        targets = set(source_path.parent.glob("*.json")) - {source_path}
        targets.update(source_path.with_name(f"{lang}.json") for lang in FULL_PARITY)
        for target_path in sorted(targets):
            enforced = target_path.stem in FULL_PARITY
            try:
                problems = differences(source, load(target_path))
            except (OSError, ValueError) as exc:
                problems = [str(exc)]
            checked += 1
            label = "FAIL" if enforced else "REPORT"
            if problems:
                failures += int(enforced)
                reports += int(not enforced)
                print(f"{label} {target_path.relative_to(root)}:")
                for problem in problems:
                    print(f"  {problem}")
            else:
                print(f"OK {target_path.relative_to(root)} ({len(source)} keys)")
    print(
        f"Checked {checked} translations across {len(sources)} English catalogues: "
        f"{failures} enforced failures, {reports} community reports."
    )
    return int(failures > 0)


if __name__ == "__main__":
    raise SystemExit(check())
