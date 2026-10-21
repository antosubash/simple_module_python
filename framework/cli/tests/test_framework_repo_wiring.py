"""Wiring a scaffolded module into the monorepo's pyproject files, and the script wrapper."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest
from simple_module_cli.framework_repo import (
    _insert_after_last_match,
    update_host_pyproject,
    update_release_matrix,
    update_root_pyproject,
)

HOST = (
    '[project]\ndependencies = [\n    "products",\n]\n\n'
    "[tool.uv.sources]\nproducts = { workspace = true }\n"
)
ROOT_TOML = (
    '[tool.ty.environment]\nextra-paths = [\n    "modules/products",\n    "host",\n]\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["modules/products/tests"]\n'
)


@pytest.fixture
def repo(tmp_path: Path) -> Path:
    (tmp_path / "host").mkdir()
    (tmp_path / "host" / "pyproject.toml").write_text(HOST)
    (tmp_path / "pyproject.toml").write_text(ROOT_TOML)
    return tmp_path


class TestInsertAfterLastMatch:
    def test_inserts_after_last_match_and_before_trailer(self):
        content = "a = 1\nb = 2\n# trailer\n"
        assert _insert_after_last_match(content, r"^b = 2$", "c = 3\n") == (
            "a = 1\nb = 2\nc = 3\n# trailer\n"
        )

    def test_none_without_a_match(self):
        assert _insert_after_last_match("nothing\n", r"^XYZ$", "x\n") is None


class TestUpdateHostPyproject:
    def test_adds_dependency_and_workspace_source_by_dist_name(self, repo: Path):
        update_host_pyproject(repo, "orders")
        content = (repo / "host" / "pyproject.toml").read_text()
        assert '"simple_module_orders"' in content
        assert "simple_module_orders = { workspace = true }" in content

    def test_idempotent(self, repo: Path):
        update_host_pyproject(repo, "orders")
        once = (repo / "host" / "pyproject.toml").read_text()
        update_host_pyproject(repo, "orders")
        assert (repo / "host" / "pyproject.toml").read_text() == once


class TestUpdateRootPyproject:
    def test_inserts_after_last_module_not_after_host(self, repo: Path):
        update_root_pyproject(repo, "orders")
        content = (repo / "pyproject.toml").read_text()
        assert '"modules/orders",\n    "host"' in content
        assert '"modules/products/tests", "modules/orders/tests"' in content

    def test_idempotent(self, repo: Path):
        update_root_pyproject(repo, "orders")
        once = (repo / "pyproject.toml").read_text()
        update_root_pyproject(repo, "orders")
        assert (repo / "pyproject.toml").read_text() == once

    def test_warns_without_insertion_point(self, repo: Path, capsys: pytest.CaptureFixture):
        (repo / "pyproject.toml").write_text("[tool.pytest.ini_options]\ntestpaths = []\n")
        update_root_pyproject(repo, "orders")
        assert "warning" in capsys.readouterr().err.lower()


RELEASE = (
    "jobs:\n  publish-pypi:\n    strategy:\n      matrix:\n        package:\n"
    "          - simple_module_core\n          - simple_module_users\n"
    "    environment:\n      name: pypi\n  publish-npm:\n    matrix:\n"
    "          - simple_module_other\n"
)


class TestUpdateReleaseMatrix:
    def test_appends_to_the_publish_pypi_matrix_only(self, repo: Path):
        wf = repo / ".github" / "workflows"
        wf.mkdir(parents=True)
        (wf / "release.yml").write_text(RELEASE)
        update_release_matrix(repo, "orders")
        content = (wf / "release.yml").read_text()
        assert "- simple_module_users\n          - simple_module_orders\n    environment" in content
        update_release_matrix(repo, "orders")
        assert (wf / "release.yml").read_text() == content


def _load_script():
    path = Path(__file__).resolve().parents[3] / "scripts" / "new_module.py"
    spec = importlib.util.spec_from_file_location("new_module_script", path)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = mod
    spec.loader.exec_module(mod)
    return mod


class TestScript:
    def test_scaffolds_and_wires(self, repo: Path, monkeypatch: pytest.MonkeyPatch):
        script = _load_script()
        monkeypatch.setattr(script, "ROOT", repo)
        monkeypatch.setattr(sys, "argv", ["new_module.py", "orders"])
        assert script.main() == 0
        assert (repo / "modules" / "orders" / "orders" / "module.py").is_file()
        assert '"simple_module_orders"' in (repo / "host" / "pyproject.toml").read_text()
        assert '"modules/orders/tests"' in (repo / "pyproject.toml").read_text()

    @pytest.mark.parametrize("bad", ["Orders", "blog-posts", "2fast"])
    def test_rejects_invalid_names(self, repo: Path, monkeypatch: pytest.MonkeyPatch, bad: str):
        script = _load_script()
        monkeypatch.setattr(script, "ROOT", repo)
        monkeypatch.setattr(sys, "argv", ["new_module.py", bad])
        assert script.main() == 1
        assert not (repo / "modules" / bad).exists()
