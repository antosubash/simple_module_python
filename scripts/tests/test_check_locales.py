"""The locale gate enforces German while keeping community reports advisory."""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location(
    "check_locales", Path(__file__).resolve().parents[1] / "check_locales.py"
)
assert spec is not None and spec.loader is not None
locales = importlib.util.module_from_spec(spec)
spec.loader.exec_module(locales)


def write_catalogue(root: Path, lang: str, data: dict) -> None:
    directory = root / "module" / "locales"
    directory.mkdir(parents=True, exist_ok=True)
    (directory / f"{lang}.json").write_text(json.dumps(data), encoding="utf-8")


def test_german_required_community_advisory(tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
    write_catalogue(tmp_path, "en", {"hello": "Hello {name}"})
    assert locales.check(tmp_path) == 1
    assert "FAIL module/locales/de.json" in capsys.readouterr().out
    write_catalogue(tmp_path, "de", {"hello": "Hallo {name}"})
    write_catalogue(tmp_path, "es", {"extra": "Hola"})
    assert locales.check(tmp_path) == 0
    output = capsys.readouterr().out
    assert "REPORT module/locales/es.json" in output
    assert "missing key: hello" in output
    assert "extra key: extra" in output


def test_nested_plural_keys_and_placeholder_identity() -> None:
    source = locales.flatten(
        {"items": {"count_one": "{count} for {{name}}", "count_other": "{count} for {{name}}"}}
    )
    target = locales.flatten(
        {"items": {"count_one": "{count} für {{name}}", "count_other": "{count} für {name}"}}
    )
    problems = locales.differences(source, target)
    assert len(problems) == 1
    assert "placeholder mismatch: items.count_other" in problems[0]
    assert locales.differences({"x": "{name} {name}"}, {"x": "{name}"})


def test_invalid_german_and_dependency_exclusion(tmp_path: Path) -> None:
    write_catalogue(tmp_path, "en", {"hello": "Hello"})
    write_catalogue(tmp_path, "de", {"hello": 42})
    write_catalogue(tmp_path / "node_modules", "en", {"ignored": "Ignored"})
    assert len(locales.catalogues(tmp_path)) == 1
    assert locales.check(tmp_path) == 1
