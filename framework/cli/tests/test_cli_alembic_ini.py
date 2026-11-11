"""Both alembic.ini files split path lists on os.pathsep (GH #872)."""

from __future__ import annotations

import os
import shutil
import warnings
from pathlib import Path

import pytest
from alembic.config import Config
from simple_module_cli import app_project

_REPO = Path(__file__).resolve().parents[3]
_INIS = [
    _REPO / "host" / "alembic.ini",
    Path(app_project.__file__).parent / "templates" / "host" / "alembic.ini",
]


@pytest.mark.parametrize("ini", _INIS, ids=["repo-host", "scaffold-template"])
def test_prepend_sys_path_with_a_space_splits_on_pathsep(tmp_path: Path, ini: Path) -> None:
    """Without ``path_separator`` Alembic warns and splits ``my app`` into two paths."""
    copy = tmp_path / "my app" / "alembic.ini"
    copy.parent.mkdir()
    shutil.copy(ini, copy)
    config = Config(str(copy))
    config.set_main_option("prepend_sys_path", f"%(here)s{os.pathsep}%(here)s/src")
    with warnings.catch_warnings():
        warnings.simplefilter("error")
        paths = config.get_prepend_sys_paths_list()
    assert paths == [str(copy.parent), f"{copy.parent}/src"]
