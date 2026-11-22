"""SM034: ``subscribe_durable`` without an explicit ``name=``."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from simple_module_core.diagnostics._durable_names import check_durable_names
from simple_module_core.diagnostics._types import DiagnosticLevel


@dataclass
class _Meta:
    name: str = "Orders"


@dataclass
class _Mod:
    meta: _Meta


def _run(tmp_path: Path, source: str, filename: str = "module.py"):
    (tmp_path / filename).write_text(source)
    return check_durable_names(_Mod(_Meta()), tmp_path)  # pyright: ignore[reportArgumentType]


def test_unnamed_subscription_warns_with_file_and_line(tmp_path: Path) -> None:
    diags = _run(tmp_path, "def reg(bus):\n    bus.subscribe_durable(E, handler)\n")
    assert len(diags) == 1
    d = diags[0]
    assert d.code == "SM034"
    assert d.level == DiagnosticLevel.WARNING
    assert d.file == f"{tmp_path / 'module.py'}:2"
    assert "constants.py" in (d.suggestion or "")
    assert "import path" in d.message


def test_named_subscription_is_clean(tmp_path: Path) -> None:
    assert _run(tmp_path, "bus.subscribe_durable(E, handler, name=c.HANDLER)\n") == []


def test_non_call_reference_is_ignored(tmp_path: Path) -> None:
    src = (
        "fn = bus.subscribe_durable\n# bus.subscribe_durable(E, h)\ns = 'subscribe_durable(E, h)'\n"
    )
    assert _run(tmp_path, src) == []


def test_nested_file_found_and_tests_dir_skipped(tmp_path: Path) -> None:
    (tmp_path / "tests").mkdir()
    (tmp_path / "tests" / "t.py").write_text("bus.subscribe_durable(E, h)\n")
    diags = _run(tmp_path, "bus.subscribe_durable(E, h)\n", "service.py")
    assert len(diags) == 1
