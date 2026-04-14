"""Tests for the new_module scaffolding script."""

from __future__ import annotations

import ast
import subprocess
import sys
import tomllib
from pathlib import Path

import pytest

# Make sure the scripts directory is importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from new_module import (
    _insert_after_last_match,
    create_file,
    main,
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

    def test_adds_paths_with_multiple_existing_modules(self, module_root: Path):
        """Regression: matches the real repo layout with many modules."""
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
            'testpaths = ['
            '"framework/core/tests", '
            '"modules/auth/tests", '
            '"modules/products/tests"]\n'
        )

        update_root_pyproject("orders")

        content = (module_root / "pyproject.toml").read_text()
        # Inserted after last modules/* entry, not after "host"
        assert '"modules/orders",\n    "host"' in content
        # Inserted after last testpath
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

    def test_warns_when_no_insertion_point(
        self, module_root: Path, capsys: pytest.CaptureFixture
    ):
        """If pyproject has no modules/* entries, emit a warning to stderr."""
        (module_root / "pyproject.toml").write_text(
            '[tool.ty.environment]\nextra-paths = ["host"]\n'
            "[tool.pytest.ini_options]\ntestpaths = []\n"
        )

        update_root_pyproject("orders")

        captured = capsys.readouterr()
        assert "warning" in captured.err.lower()


class TestInsertAfterLastMatch:
    def test_inserts_after_last_matching_line(self):
        content = (
            'dependencies = [\n    "foo",\n    "bar",\n    "baz",\n]\n'
        )
        result = _insert_after_last_match(
            content, r'^    "[\w]+",\s*$', '    "qux",\n'
        )
        assert result is not None
        # New entry appears right after the last `"baz",` line
        assert '"baz",\n    "qux",\n]' in result

    def test_returns_none_when_no_match(self):
        content = "no matching lines here\n"
        result = _insert_after_last_match(content, r"^XYZ$", "inserted\n")
        assert result is None

    def test_respects_last_of_many(self):
        content = "sm-a = 1\nsm-b = 2\nother = x\nsm-c = 3\n"
        result = _insert_after_last_match(
            content, r"^sm-\w+ = \d+$", "sm-d = 4\n"
        )
        # Must insert after `sm-c`, not after `sm-b`
        assert result is not None
        assert result.endswith("sm-c = 3\nsm-d = 4\n")

    def test_inserts_before_trailing_content(self):
        """Insertion preserves everything after the matched line."""
        content = "a = 1\nb = 2\n# trailer\n"
        result = _insert_after_last_match(content, r"^b = 2$", "c = 3\n")
        assert result == "a = 1\nb = 2\nc = 3\n# trailer\n"


class TestCreateFile:
    def test_creates_file_with_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import new_module

        monkeypatch.setattr(new_module, "ROOT", tmp_path)

        target = tmp_path / "foo" / "bar.txt"
        create_file(target, "hello world\n")

        assert target.exists()
        assert target.read_text() == "hello world\n"

    def test_creates_parent_directories(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ):
        import new_module

        monkeypatch.setattr(new_module, "ROOT", tmp_path)

        target = tmp_path / "a" / "b" / "c" / "file.txt"
        create_file(target, "")

        assert target.exists()
        assert target.parent.is_dir()

    def test_dedents_content(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
        import new_module

        monkeypatch.setattr(new_module, "ROOT", tmp_path)

        target = tmp_path / "indented.txt"
        create_file(target, "        line one\n        line two\n")

        assert target.read_text() == "line one\nline two\n"


class TestGeneratedFilesSyntaxValidity:
    """Ensure every generated Python file is syntactically valid and TOML is parseable."""

    def test_all_python_files_parse(self, module_root: Path):
        scaffold_module("orders")

        py_files = list((module_root / "modules" / "orders").rglob("*.py"))
        assert len(py_files) > 0

        for py_file in py_files:
            source = py_file.read_text()
            try:
                ast.parse(source, filename=str(py_file))
            except SyntaxError as e:
                pytest.fail(f"Generated file {py_file.name} has syntax error: {e}")

    def test_pyproject_toml_parses(self, module_root: Path):
        scaffold_module("orders")

        pyproject = module_root / "modules" / "orders" / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())

        assert data["project"]["name"] == "sm-orders"
        assert (
            data["project"]["entry-points"]["simple_module"]["orders"]
            == "sm_orders.module:OrdersModule"
        )

    def test_compound_name_pyproject_toml_parses(self, module_root: Path):
        scaffold_module("blog_posts")

        pyproject = module_root / "modules" / "blog_posts" / "pyproject.toml"
        data = tomllib.loads(pyproject.read_text())

        assert data["project"]["name"] == "sm-blog-posts"
        ep = data["project"]["entry-points"]["simple_module"]
        assert ep["blog_posts"] == "sm_blog_posts.module:BlogPostsModule"


class TestGeneratedTemplateContent:
    """Verify key fragments of generated templates."""

    def test_service_has_full_crud(self, module_root: Path):
        scaffold_module("orders")

        service = (module_root / "modules" / "orders" / "sm_orders" / "service.py").read_text()
        assert "class OrderService:" in service
        assert "async def get_all(self)" in service
        assert "async def get_by_id(self" in service
        assert "async def create(self" in service
        assert "async def update(" in service
        assert "async def delete(self" in service

    def test_api_has_full_crud_endpoints(self, module_root: Path):
        scaffold_module("orders")

        api = (
            module_root / "modules" / "orders" / "sm_orders" / "endpoints" / "api.py"
        ).read_text()
        assert '@router.get("/"' in api
        assert '@router.get("/{order_id}"' in api
        assert '@router.post("/"' in api
        assert '@router.put("/{order_id}"' in api
        assert '@router.delete("/{order_id}"' in api
        assert "status_code=201" in api
        assert "status_code=204" in api

    def test_views_use_inertia(self, module_root: Path):
        scaffold_module("orders")

        views = (
            module_root / "modules" / "orders" / "sm_orders" / "endpoints" / "views.py"
        ).read_text()
        assert "InertiaResponse" in views
        assert "InertiaDep" in views
        assert '"Orders/Browse"' in views
        assert '"Orders/Create"' in views
        assert '"Orders/Edit"' in views

    def test_deps_provides_di_function(self, module_root: Path):
        scaffold_module("orders")

        deps = (module_root / "modules" / "orders" / "sm_orders" / "deps.py").read_text()
        assert "async def get_order_service(" in deps
        assert "Depends(get_db)" in deps

    def test_contracts_protocol_defined(self, module_root: Path):
        scaffold_module("orders")

        protocol = (
            module_root / "modules" / "orders" / "sm_orders" / "contracts" / "service.py"
        ).read_text()
        assert "class IOrderService(Protocol):" in protocol

    def test_contracts_init_exports_public_api(self, module_root: Path):
        scaffold_module("orders")

        init = (
            module_root / "modules" / "orders" / "sm_orders" / "contracts" / "__init__.py"
        ).read_text()
        assert '"OrderCreate"' in init
        assert '"OrderOut"' in init
        assert '"OrderUpdate"' in init
        assert '"IOrderService"' in init

    def test_module_class_registers_routes(self, module_root: Path):
        scaffold_module("orders")

        module_py = (
            module_root / "modules" / "orders" / "sm_orders" / "module.py"
        ).read_text()
        assert "def register_routes(" in module_py
        assert "api_router.include_router(api)" in module_py
        assert "view_router.include_router(views)" in module_py

    def test_module_class_registers_permissions(self, module_root: Path):
        scaffold_module("orders")

        module_py = (
            module_root / "modules" / "orders" / "sm_orders" / "module.py"
        ).read_text()
        assert '"orders.view"' in module_py
        assert '"orders.create"' in module_py
        assert '"orders.edit"' in module_py
        assert '"orders.delete"' in module_py

    def test_model_has_audit_mixin(self, module_root: Path):
        scaffold_module("orders")

        model = (module_root / "modules" / "orders" / "sm_orders" / "models.py").read_text()
        assert "from simple_module_db.mixins import AuditMixin" in model
        assert "class Order(Base, AuditMixin):" in model
        assert '__tablename__ = "orders_order"' in model

    def test_test_file_has_test_classes(self, module_root: Path):
        scaffold_module("orders")

        test_file = (module_root / "modules" / "orders" / "tests" / "test_orders.py").read_text()
        assert "class TestOrderSchemas:" in test_file
        assert "class TestOrderService:" in test_file
        assert "class TestOrdersAPI:" in test_file
        assert "class TestOrdersModuleLifecycle:" in test_file


class TestMainCLI:
    """Tests for the main() entry point."""

    def test_main_invokes_full_pipeline(
        self, module_root: Path, monkeypatch: pytest.MonkeyPatch
    ):
        # Provide host/pyproject.toml and root pyproject.toml so updates succeed
        (module_root / "host").mkdir()
        (module_root / "host" / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n    "sm-products",\n]\n\n'
            "[tool.uv.sources]\nsm-products = { workspace = true }\n"
        )
        (module_root / "pyproject.toml").write_text(
            "[tool.ty.environment]\nextra-paths = [\n    \"modules/products\",\n]\n\n"
            "[tool.pytest.ini_options]\ntestpaths = [\"modules/products/tests\"]\n"
        )

        monkeypatch.setattr(sys, "argv", ["new_module.py", "orders"])
        main()

        assert (module_root / "modules" / "orders" / "pyproject.toml").exists()
        assert (
            module_root / "modules" / "orders" / "sm_orders" / "module.py"
        ).exists()
        host_content = (module_root / "host" / "pyproject.toml").read_text()
        assert '"sm-orders"' in host_content

    def test_main_exits_on_invalid_name(self, monkeypatch: pytest.MonkeyPatch):
        monkeypatch.setattr(sys, "argv", ["new_module.py", "Invalid-Name"])
        with pytest.raises(SystemExit):
            main()


class TestCLIAsSubprocess:
    """Run the actual script as a subprocess (end-to-end smoke test)."""

    def test_script_runs_successfully(self, tmp_path: Path):
        """Invoke the script in isolation — verifies it's directly executable."""
        # Set up a minimal workspace
        (tmp_path / "modules").mkdir()
        (tmp_path / "host").mkdir()
        (tmp_path / "host" / "pyproject.toml").write_text(
            '[project]\ndependencies = [\n    "sm-products",\n]\n\n'
            "[tool.uv.sources]\nsm-products = { workspace = true }\n"
        )
        (tmp_path / "pyproject.toml").write_text(
            "[tool.ty.environment]\nextra-paths = [\n    \"modules/products\",\n]\n\n"
            "[tool.pytest.ini_options]\ntestpaths = [\"modules/products/tests\"]\n"
        )

        # Run script with ROOT monkey-patched via an env variable trick — instead,
        # invoke via python -c with sys.path manipulation and direct function call
        scripts_dir = Path(__file__).resolve().parent.parent
        cmd = [
            sys.executable,
            "-c",
            (
                f"import sys; sys.path.insert(0, {str(scripts_dir)!r}); "
                f"import new_module; new_module.ROOT = {str(tmp_path)!r}; "
                "new_module.ROOT = __import__('pathlib').Path(new_module.ROOT); "
                "sys.argv = ['new_module.py', 'orders']; new_module.main()"
            ),
        ]
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        assert result.returncode == 0, f"stderr: {result.stderr}"
        assert "Scaffolding module 'orders'" in result.stdout
        assert (tmp_path / "modules" / "orders" / "sm_orders" / "module.py").exists()
