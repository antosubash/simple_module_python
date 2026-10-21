"""``create_module(framework_repo=True)``: the variant ``make new-module`` scaffolds."""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path

import pytest
from simple_module_cli.case import to_singular
from simple_module_cli.scaffolding import create_module


@pytest.fixture
def orders(tmp_path: Path) -> Path:
    return create_module(
        tmp_path / "orders", name="orders", framework_version="0.0.37", framework_repo=True
    )


class TestToSingular:
    @pytest.mark.parametrize(
        ("plural", "singular"),
        [
            ("orders", "order"),
            ("blog_posts", "blog_post"),
            ("access", "access"),
            ("inventory", "inventory"),
        ],
    )
    def test_singular(self, plural: str, singular: str):
        assert to_singular(plural) == singular


class TestRichModuleContent:
    """Both variants get the CRUD sample, permissions, menu and locale wiring."""

    @pytest.mark.parametrize("framework_repo", [True, False])
    def test_every_python_file_parses_and_has_the_crud_layers(self, tmp_path: Path, framework_repo):
        dest = create_module(tmp_path / "m", name="blog_posts", framework_repo=framework_repo)
        pkg = dest / "blog_posts"
        for py in dest.rglob("*.py"):
            ast.parse(py.read_text(), filename=str(py))
        for rel in [
            "constants.py", "models.py", "service.py", "deps.py", "py.typed",
            "contracts/schemas.py", "locales/en.json", "pages/Browse.tsx", "pages/Edit.tsx",
        ]:  # fmt: skip
            assert (pkg / rel).is_file(), rel
        assert "class BlogPost(Base, AuditMixin, table=True)" in (pkg / "models.py").read_text()

    def test_no_magic_strings_in_module_and_endpoints(self, orders: Path):
        """Permissions, page keys and menu labels come from constants.py."""
        pkg = orders / "orders"
        module_py = (pkg / "module.py").read_text()
        views = (pkg / "endpoints" / "views.py").read_text()
        assert "label_key=MENU_LABEL_KEY" in module_py
        assert "register_module_settings(" in module_py
        assert "app.state.orders =" not in module_py
        assert "PAGE_BROWSE," in views
        assert 'render("Orders/' not in views
        assert '"orders.view"' not in module_py
        assert 'PERM_ORDERS_VIEW = "orders.view"' in (pkg / "constants.py").read_text()

    def test_locale_catalog_carries_the_menu_key(self, orders: Path):
        data = json.loads((orders / "orders" / "locales" / "en.json").read_text())
        assert data["nav"]["title"] == "Orders"
        assert data["browse"]["new_button"] == "New Order"


class TestFrameworkRepoVariant:
    def test_pyproject_is_workspace_sourced_and_passes_check_metadata(self, orders: Path):
        data = tomllib.loads((orders / "pyproject.toml").read_text())
        project = data["project"]
        assert project["name"] == "simple_module_orders"
        assert project["license"] == "MIT"
        assert "simple-module" in project["keywords"]
        assert "Repository" in project["urls"]
        assert "simple_module_core==0.0.37" in project["dependencies"]
        assert data["tool"]["uv"]["sources"]["simple_module_core"] == {"workspace": True}
        assert project["entry-points"]["simple_module"]["orders"] == "orders.module:OrdersModule"

    def test_readme_license_and_no_ci_workflows(self, orders: Path):
        readme = (orders / "README.md").read_text()
        assert len(readme.encode()) >= 500
        assert readme.startswith("# ") and "Install" in readme and "Usage" in readme
        assert "MIT License" in (orders / "LICENSE").read_text()
        assert not (orders / ".github").exists()

    def test_pages_use_typed_i18n_keys(self, orders: Path):
        for page in ("Browse.tsx", "Create.tsx", "Edit.tsx"):
            content = (orders / "orders" / "pages" / page).read_text()
            assert "const { t } = useT();" in content
            assert "t(keys.orders." in content

    def test_workspace_tsconfig_resolves_ui_from_root_node_modules(self, orders: Path):
        assert (
            "../../node_modules/@simple-module-py/ui/src/*"
            in (orders / "tsconfig.json").read_text()
        )

    def test_standalone_variant_keeps_literal_pages_and_no_workspace_sources(self, tmp_path: Path):
        dest = create_module(tmp_path / "m", name="orders")
        assert "keys." not in (dest / "orders" / "pages" / "Browse.tsx").read_text()
        assert "tool.uv.sources" not in (dest / "pyproject.toml").read_text()
        assert not (dest / "LICENSE").exists()

    def test_duplicate_destination_is_refused(self, orders: Path):
        with pytest.raises(FileExistsError):
            create_module(orders, name="orders", framework_repo=True)
