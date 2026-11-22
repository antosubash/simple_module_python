"""Package discovery handles namespaces and optional endpoint layouts (GH #980)."""

import importlib
import sys
from types import ModuleType

import pytest
from fastapi import APIRouter, FastAPI
from simple_module_core import ModuleBase, ModuleMeta, get_module_package_name
from simple_module_core.diagnostics import ModuleDiagnostics


@pytest.fixture
def namespaced_package(tmp_path, monkeypatch):
    root = tmp_path / "acme" / "billing"
    root.mkdir(parents=True)
    (root / "__init__.py").write_text("")
    (root / "module.py").write_text(
        "from simple_module_core import ModuleBase, ModuleMeta\n"
        "class Billing(ModuleBase):\n"
        "    meta = ModuleMeta(name='Billing', view_prefix='/billing')\n"
    )
    monkeypatch.syspath_prepend(str(tmp_path))
    yield root
    for name in list(sys.modules):
        if name == "acme" or name.startswith("acme."):
            sys.modules.pop(name, None)


def test_namespaced_routes_locales_and_diagnostics(namespaced_package):
    root = namespaced_package
    endpoints = root / "web" / "endpoints"
    endpoints.mkdir(parents=True)
    (endpoints.parent / "__init__.py").write_text("")
    (endpoints / "__init__.py").write_text("")
    for endpoint in ("api", "views"):
        (endpoints / f"{endpoint}.py").write_text(
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            f"@router.get('/{endpoint}')\ndef hello(): return {{}}\n"
        )
    locales = root / "locales"
    locales.mkdir()
    mod = importlib.import_module("acme.billing.module").Billing()
    assert get_module_package_name(mod) == "acme.billing"
    api, views = APIRouter(), APIRouter()
    mod.register_routes(api, views)
    for router, path in ((api, "/api"), (views, "/views")):
        app = FastAPI()
        app.include_router(router)
        assert set(app.openapi()["paths"]) == {path}
    assert mod.locale_dirs() == {"billing": locales}
    diagnostics = ModuleDiagnostics()
    assert diagnostics._find_source_dir(mod) == root
    assert diagnostics._check_empty_modules([mod]) == []
    assert [d.code for d in diagnostics._check_views_without_menu([mod])] == ["SM019"]


@pytest.mark.parametrize("module_name", ["__main__", "inline_980", "inline_980.module"])
def test_specless_modules_have_no_conventional_contributions(monkeypatch, module_name):
    package = module_name.split(".")[0]
    monkeypatch.setitem(sys.modules, package, ModuleType(package))
    cls = type(
        "Inline", (ModuleBase,), {"__module__": module_name, "meta": ModuleMeta(name="Inline")}
    )
    mod = cls()
    assert get_module_package_name(mod) == module_name.split(".")[0]
    assert mod.locale_dirs() == {}
    api, views = APIRouter(), APIRouter()
    mod.register_routes(api, views)
    assert api.routes == views.routes == []
    assert ModuleDiagnostics()._find_source_dir(mod) is None
    assert [d.code for d in ModuleDiagnostics()._check_empty_modules([mod])] == ["SM007"]


def test_plain_endpoints_module_has_no_conventional_routers(namespaced_package):
    web = namespaced_package / "web"
    web.mkdir()
    (web / "__init__.py").write_text("")
    (web / "endpoints.py").write_text("")
    mod = importlib.import_module("acme.billing.module").Billing()
    api, views = APIRouter(), APIRouter()
    mod.register_routes(api, views)
    assert api.routes == views.routes == []


@pytest.mark.parametrize("parent", ["web", "web/endpoints"])
def test_existing_parent_import_error_naming_target_propagates(namespaced_package, parent):
    web = namespaced_package / "web"
    web.mkdir()
    (web / "__init__.py").write_text("")
    directory = namespaced_package / parent
    directory.mkdir(exist_ok=True)
    (directory / "__init__.py").write_text(
        "raise ModuleNotFoundError('broken parent', name='acme.billing.web.endpoints.api')\n"
    )
    mod = importlib.import_module("acme.billing.module").Billing()
    with pytest.raises(ModuleNotFoundError, match="broken parent"):
        mod.register_routes(APIRouter(), APIRouter())
