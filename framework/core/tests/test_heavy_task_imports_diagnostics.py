"""SM028: a module's tasks.py importing a heavy package at module level."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pytest
from simple_module_core.diagnostics._heavy_task_imports import check_heavy_task_imports
from simple_module_core.diagnostics._types import DiagnosticLevel


@dataclass
class _Meta:
    name: str = "Vision"


@dataclass
class _Mod:
    meta: _Meta


def _run(tmp_path: Path, source: str | None):
    if source is not None:
        (tmp_path / "tasks.py").write_text(source)
    return check_heavy_task_imports(_Mod(_Meta()), tmp_path)  # pyright: ignore[reportArgumentType]


@pytest.mark.parametrize(
    "line",
    [
        "import torch",
        "import torch.nn as nn",
        "from osgeo import gdal",
        "from sklearn.ensemble import RandomForestClassifier",
        "import cv2",
        "import rasterio",
        "import tensorflow as tf",
        "import ultralytics",
    ],
)
def test_flags_top_level_heavy_import(tmp_path: Path, line: str) -> None:
    diags = _run(tmp_path, f"from celery import shared_task\n{line}\n")
    assert [d.code for d in diags] == ["SM028"]
    assert diags[0].level == DiagnosticLevel.WARNING
    assert (diags[0].file or "").endswith("tasks.py:2")


def test_flags_import_guarded_by_try(tmp_path: Path) -> None:
    diags = _run(tmp_path, "try:\n    import torch\nexcept ImportError:\n    torch = None\n")
    assert [d.code for d in diags] == ["SM028"]


def test_silent_when_import_is_inside_a_function(tmp_path: Path) -> None:
    src = "def run():\n    import torch\n    return torch\n"
    assert _run(tmp_path, src) == []


def test_silent_under_type_checking(tmp_path: Path) -> None:
    src = "from typing import TYPE_CHECKING\nif TYPE_CHECKING:\n    import torch\n"
    assert _run(tmp_path, src) == []


def test_silent_on_light_imports_and_lookalikes(tmp_path: Path) -> None:
    assert _run(tmp_path, "import json\nimport torchlike\nfrom . import torch_utils\n") == []


def test_silent_without_tasks_py_or_on_syntax_error(tmp_path: Path) -> None:
    assert _run(tmp_path, None) == []
    assert _run(tmp_path, "def (:\n") == []
