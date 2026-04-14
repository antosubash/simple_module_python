"""Tests for the new_module scaffolding script."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Make sure the scripts directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from new_module import (
    scaffold_module,
    to_class_name,
    to_singular,
    update_host_pyproject,
    update_root_pyproject,
    validate_name,
)


class TestValidateName:
    def test_valid_simple_name(self):
        assert validate_name("orders") == "orders"

    def test_valid_name_with_underscore(self):
        assert validate_name("blog_posts") == "blog_posts"

    def test_valid_name_with_digits(self):
        assert validate_name("v2_items") == "v2_items"

    def test_rejects_uppercase(self):
        with pytest.raises(SystemExit):
            validate_name("Orders")

    def test_rejects_hyphens(self):
        with pytest.raises(SystemExit):
            validate_name("blog-posts")

    def test_rejects_starting_with_digit(self):
        with pytest.raises(SystemExit):
            validate_name("2fast")

    def test_rejects_empty(self):
        with pytest.raises(SystemExit):
            validate_name("")


class TestToClassName:
    def test_single_word(self):
        assert to_class_name("orders") == "Orders"

    def test_two_words(self):
        assert to_class_name("blog_posts") == "BlogPosts"

    def test_three_words(self):
        assert to_class_name("user_role_assignments") == "UserRoleAssignments"


class TestToSingular:
    def test_plural(self):
        assert to_singular("orders") == "order"

    def test_already_singular(self):
        assert to_singular("inventory") == "inventory"

    def test_double_s(self):
        assert to_singular("access") == "access"

    def test_plural_compound(self):
        assert to_singular("blog_posts") == "blog_post"


@pytest.fixture
def module_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Provide a temp directory patched as the script's ROOT with modules/ pre-created."""
    import new_module

    monkeypatch.setattr(new_module, "ROOT", tmp_path)
    (tmp_path / "modules").mkdir()
    return tmp_path


class TestScaffoldModule:
    """Integration tests that run the scaffolding and verify output files."""

    def test_scaffold_creates_all_files(self, module_root: Path):
        scaffold_module("orders")

        mod_dir = module_root / "modules" / "orders"
        src_dir = mod_dir / "sm_orders"

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
            assert f.exists(), f"Missing: {f.relative_to(module_root)}"

    def test_scaffold_pyproject_has_entry_point(self, module_root: Path):
        scaffold_module("orders")

        content = (module_root / "modules" / "orders" / "pyproject.toml").read_text()
        assert 'orders = "sm_orders.module:OrdersModule"' in content

    def test_scaffold_module_class_name(self, module_root: Path):
        scaffold_module("orders")

        content = (
            module_root / "modules" / "orders" / "sm_orders" / "module.py"
        ).read_text()
        assert "class OrdersModule(ModuleBase):" in content
        assert 'name="Orders"' in content

    def test_scaffold_model_is_singular(self, module_root: Path):
        scaffold_module("orders")

        content = (
            module_root / "modules" / "orders" / "sm_orders" / "models.py"
        ).read_text()
        assert "class Order(Base, AuditMixin):" in content

    def test_scaffold_rejects_duplicate(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import new_module

        monkeypatch.setattr(new_module, "ROOT", tmp_path)
        (tmp_path / "modules" / "orders").mkdir(parents=True)

        with pytest.raises(SystemExit):
            scaffold_module("orders")

    def test_scaffold_compound_name(self, module_root: Path):
        scaffold_module("blog_posts")

        src_dir = module_root / "modules" / "blog_posts" / "sm_blog_posts"
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
        (host_dir / "pyproject.toml").write_text(
            '[project]\nname = "simple-module-host"\ndependencies = [\n'
            '    "sm-products",\n]\n\n[tool.uv.sources]\n'
            "sm-products = { workspace = true }\n"
        )

        update_host_pyproject("orders")

        content = (host_dir / "pyproject.toml").read_text()
        assert '"sm-orders"' in content
        assert "sm-orders = { workspace = true }" in content

    def test_skips_if_already_present(self, module_root: Path):
        host_dir = module_root / "host"
        host_dir.mkdir()
        original = (
            '[project]\nname = "simple-module-host"\ndependencies = [\n'
            '    "sm-products",\n    "sm-orders",\n]\n\n[tool.uv.sources]\n'
            "sm-products = { workspace = true }\nsm-orders = { workspace = true }\n"
        )
        (host_dir / "pyproject.toml").write_text(original)

        update_host_pyproject("orders")

        assert (host_dir / "pyproject.toml").read_text() == original


class TestUpdateRootPyproject:
    def test_adds_paths(self, module_root: Path):
        (module_root / "pyproject.toml").write_text(
            "[tool.ty.environment]\nextra-paths = [\n"
            '    "modules/products",\n]\n\n'
            "[tool.pytest.ini_options]\n"
            'testpaths = ["modules/products/tests"]\n'
        )

        update_root_pyproject("orders")

        content = (module_root / "pyproject.toml").read_text()
        assert '"modules/orders"' in content
        assert '"modules/orders/tests"' in content
