"""Tests for scaffold_module and pyproject updates in new_module."""

from __future__ import annotations

from pathlib import Path

import pytest
from new_module import scaffold_module, update_host_pyproject, update_root_pyproject

MINIMAL_HOST_PYPROJECT = (
    '[project]\ndependencies = [\n    "products",\n]\n\n'
    "[tool.uv.sources]\nproducts = { workspace = true }\n"
)
MINIMAL_ROOT_PYPROJECT = (
    '[tool.ty.environment]\nextra-paths = [\n    "modules/products",\n]\n\n'
    '[tool.pytest.ini_options]\ntestpaths = ["modules/products/tests"]\n'
)


class TestScaffoldModule:
    """Integration tests that run the scaffolding and verify output files."""

    def test_scaffold_creates_all_files(self, scaffolded_orders: Path):
        mod_dir = scaffolded_orders.parent
        src_dir = scaffolded_orders

        expected_files = [
            mod_dir / "pyproject.toml",
            src_dir / "__init__.py",
            src_dir / "py.typed",
            src_dir / "module.py",
            src_dir / "models.py",
            src_dir / "service.py",
            src_dir / "deps.py",
            src_dir / "contracts" / "__init__.py",
            src_dir / "contracts" / "schemas.py",
            src_dir / "contracts" / "service.py",
            src_dir / "endpoints" / "__init__.py",
            src_dir / "endpoints" / "api.py",
            src_dir / "endpoints" / "views.py",
            mod_dir / "tests" / "test_orders.py",
        ]
        for f in expected_files:
            assert f.exists(), f"Missing: {f}"

    def test_scaffold_pyproject_has_entry_point(self, scaffolded_orders: Path):
        content = (scaffolded_orders.parent / "pyproject.toml").read_text()
        assert 'orders = "orders.module:OrdersModule"' in content

    def test_scaffold_module_class_name(self, scaffolded_orders: Path):
        content = (scaffolded_orders / "module.py").read_text()
        assert "class OrdersModule(ModuleBase):" in content
        assert 'name="Orders"' in content

    def test_scaffold_model_is_singular(self, scaffolded_orders: Path):
        content = (scaffolded_orders / "models.py").read_text()
        assert "class Order(Base, AuditMixin):" in content

    def test_scaffold_rejects_duplicate(self, module_root: Path):
        (module_root / "modules" / "orders").mkdir()

        with pytest.raises(SystemExit):
            scaffold_module("orders")

    def test_scaffold_compound_name(self, module_root: Path):
        scaffold_module("blog_posts")

        src_dir = module_root / "modules" / "blog_posts" / "blog_posts"
        assert (src_dir / "module.py").exists()

        module_content = (src_dir / "module.py").read_text()
        assert "class BlogPostsModule(ModuleBase):" in module_content

        model_content = (src_dir / "models.py").read_text()
        assert "class BlogPost(Base, AuditMixin):" in model_content

        schema_content = (src_dir / "contracts" / "schemas.py").read_text()
        assert "class BlogPostOut(BaseModel):" in schema_content
        assert "class BlogPostCreate(BaseModel):" in schema_content
        assert "class BlogPostUpdate(BaseModel):" in schema_content


class TestUpdateHostPyproject:
    def test_adds_module_dependency(self, module_root: Path):
        host_dir = module_root / "host"
        host_dir.mkdir()
        (host_dir / "pyproject.toml").write_text(MINIMAL_HOST_PYPROJECT)

        update_host_pyproject("orders")

        content = (host_dir / "pyproject.toml").read_text()
        assert '"orders"' in content
        assert "orders = { workspace = true }" in content

    def test_skips_if_already_present(self, module_root: Path):
        host_dir = module_root / "host"
        host_dir.mkdir()
        original = (
            '[project]\nname = "simple-module-host"\ndependencies = [\n'
            '    "products",\n    "orders",\n]\n\n[tool.uv.sources]\n'
            "products = { workspace = true }\norders = { workspace = true }\n"
        )
        (host_dir / "pyproject.toml").write_text(original)

        update_host_pyproject("orders")

        assert (host_dir / "pyproject.toml").read_text() == original


class TestUpdateRootPyproject:
    def test_adds_paths(self, module_root: Path):
        (module_root / "pyproject.toml").write_text(MINIMAL_ROOT_PYPROJECT)

        update_root_pyproject("orders")

        content = (module_root / "pyproject.toml").read_text()
        assert '"modules/orders"' in content
        assert '"modules/orders/tests"' in content

    def test_adds_paths_with_multiple_existing_modules(self, module_root: Path):
        # Regression: matches the real repo layout where "host" comes after modules/*
        (module_root / "pyproject.toml").write_text(
            "[tool.ty.environment]\nextra-paths = [\n"
            '    "framework/core",\n'
            '    "framework/db",\n'
            '    "framework/hosting",\n'
            '    "modules/auth",\n'
            '    "modules/dashboard",\n'
            '    "modules/products",\n'
            '    "host",\n]\n\n'
            "[tool.pytest.ini_options]\n"
            "testpaths = ["
            '"framework/core/tests", '
            '"modules/auth/tests", '
            '"modules/products/tests"]\n'
        )

        update_root_pyproject("orders")

        content = (module_root / "pyproject.toml").read_text()
        # Insertion point must be after last modules/* entry, not after "host"
        assert '"modules/orders",\n    "host"' in content
        assert '"modules/products/tests", "modules/orders/tests"' in content

    def test_skips_if_already_present(self, module_root: Path):
        original = (
            "[tool.ty.environment]\nextra-paths = [\n"
            '    "modules/products",\n    "modules/orders",\n]\n\n'
            "[tool.pytest.ini_options]\n"
            'testpaths = ["modules/products/tests", "modules/orders/tests"]\n'
        )
        (module_root / "pyproject.toml").write_text(original)

        update_root_pyproject("orders")

        assert (module_root / "pyproject.toml").read_text() == original

    def test_warns_when_no_insertion_point(self, module_root: Path, capsys: pytest.CaptureFixture):
        (module_root / "pyproject.toml").write_text(
            '[tool.ty.environment]\nextra-paths = ["host"]\n'
            "[tool.pytest.ini_options]\ntestpaths = []\n"
        )

        update_root_pyproject("orders")

        assert "warning" in capsys.readouterr().err.lower()
