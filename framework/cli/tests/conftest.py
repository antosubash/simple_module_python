"""Fixtures shared by the module-asset tests in this directory.

These test files have no ``__init__.py`` (test basenames are globally unique
instead), so a plain helper import across files is not available — a fixture is
how the factory below gets shared.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture
def make_importable_module(tmp_path: Path):
    """Return a factory creating a real importable package bound to a ModuleBase.

    ``get_module_package_name`` derives the package from the class's
    ``__module__``, and ``compute_module_assets`` then resolves that package via
    ``importlib.resources.files``. So the package has to genuinely exist on
    ``sys.path`` — a mock won't exercise the code path we care about.

    Returns ``(module_instance, package_dir)``.
    """
    from simple_module_core import ModuleBase, ModuleMeta

    def _make(pkg_name: str, klass_name: str, *, root: Path | None = None):
        base = root or tmp_path
        pkg = base / pkg_name
        pkg.mkdir(parents=True, exist_ok=True)
        (pkg / "__init__.py").write_text("", encoding="utf-8")
        if str(base) not in sys.path:
            sys.path.insert(0, str(base))
        sys.modules.pop(pkg_name, None)

        klass = type(
            klass_name,
            (ModuleBase,),
            {"meta": ModuleMeta(name=klass_name), "__module__": f"{pkg_name}.module"},
        )
        return klass(), pkg

    return _make
