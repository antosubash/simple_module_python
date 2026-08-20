"""Fixtures shared by the module-asset tests in this directory.

These test files have no ``__init__.py`` (test basenames are globally unique
instead), so a plain helper import across files is not available — a fixture is
how the factory below gets shared.
"""

from __future__ import annotations

import subprocess
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


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "HOME": str(repo),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )


def _write_module_pkg(root: Path, dist_name: str, version: str, *, models: bool) -> None:
    pkg = dist_name.replace("-", "_")
    (root / pkg).mkdir(parents=True)
    (root / pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / pkg / "module.py").write_text("class M:\n    pass\n", encoding="utf-8")
    if models:
        (root / pkg / "models.py").write_text("# tables\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "{version}"\n'
        f'dependencies = ["simple_module_core>=0.1,<1.0"]\n\n'
        f"[project.entry-points.simple_module]\n"
        f'{pkg} = "{pkg}.module:M"\n',
        encoding="utf-8",
    )


@pytest.fixture
def make_git_module_repo(tmp_path: Path):
    """Factory: build a local git repo holding one or more module packages.

    ``modules`` is a list of ``(dist_name, version, subdir_or_None,
    ships_models)`` tuples; ``tags`` are created at HEAD. Returns the repo
    path — use ``git+`` + ``.as_uri()`` to feed it to `smpy add` specs.
    """

    counter = {"n": 0}

    def factory(
        modules: list[tuple[str, str, str | None, bool]],
        *,
        tags: list[str] | None = None,
        extra_pyproject_dirs: list[str] | None = None,
    ) -> Path:
        counter["n"] += 1
        repo = tmp_path / f"repo{counter['n']}"
        repo.mkdir()
        for dist_name, version, subdir, models in modules:
            root = repo / subdir if subdir else repo
            root.mkdir(parents=True, exist_ok=True)
            _write_module_pkg(root, dist_name, version, models=models)
        for d in extra_pyproject_dirs or []:
            (repo / d).mkdir(parents=True, exist_ok=True)
            (repo / d / "pyproject.toml").write_text(
                '[project]\nname = "not-a-module"\nversion = "0"\n', encoding="utf-8"
            )
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "init")
        for tag in tags or []:
            _git(repo, "tag", tag)
        return repo

    return factory
