"""Package conventions must work without hook boilerplate (GH #980)."""

from __future__ import annotations

import importlib
import sys
from pathlib import Path

import pytest
from fastapi import FastAPI
from httpx import ASGITransport, AsyncClient
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting._module_routes import wire_module_routes


@pytest.fixture
def package(tmp_path, monkeypatch):
    root = tmp_path / "convention_sample"
    root.mkdir()
    (root / "__init__.py").write_text("")
    monkeypatch.syspath_prepend(str(tmp_path))
    yield root
    for name in list(sys.modules):
        if name == root.name or name.startswith(f"{root.name}."):
            sys.modules.pop(name, None)


def module_class(package: Path, **overrides):
    return type(
        "ExampleModule",
        (ModuleBase,),
        {
            "__module__": f"{package.name}.module",
            "meta": ModuleMeta(name="DifferentName", **overrides),
        },
    )


def write_endpoint(package, name, body):
    endpoints = package / "web" / "endpoints"
    endpoints.mkdir(parents=True, exist_ok=True)
    for directory in (endpoints.parent, endpoints):
        (directory / "__init__.py").write_text("")
    (endpoints / f"{name}.py").write_text(body)
    importlib.invalidate_caches()


def test_locales_discovered_using_package_namespace(package):
    locales = package / "locales"
    locales.mkdir()
    assert module_class(package)().locale_dirs() == {"convention_sample": locales}


def test_absent_locales(package):
    assert module_class(package)().locale_dirs() == {}


def test_package_prefix_defaults(package):
    meta = module_class(package).meta
    assert meta.route_prefix == "/api/convention_sample"
    assert meta.view_prefix == "/convention-sample"
    assert meta.name == "DifferentName"


@pytest.mark.parametrize("prefix", ["", "/custom"])
def test_explicit_prefixes_and_version_win(package, prefix):
    meta = module_class(package, route_prefix=prefix, view_prefix=prefix, version="2.3.4").meta
    assert meta.route_prefix == prefix
    assert meta.view_prefix == prefix
    assert meta.version == "2.3.4"


@pytest.mark.parametrize("endpoints", [("api",), ("views",), ("api", "views")])
async def test_conventional_router_mounted_once_with_host_tags(package, endpoints):
    for endpoint in endpoints:
        write_endpoint(
            package,
            endpoint,
            "from fastapi import APIRouter\nrouter = APIRouter()\n"
            '@router.get("/hello")\nasync def hello(): return {"hello": "world"}\n',
        )
    app = FastAPI()
    wire_module_routes(app, module_class(package)())
    async with AsyncClient(transport=ASGITransport(app), base_url="http://test") as client:
        for endpoint in endpoints:
            prefix = "/api/convention_sample" if endpoint == "api" else "/convention-sample"
            assert (await client.get(f"{prefix}/hello")).json() == {"hello": "world"}
            paths = app.openapi()["paths"]
            if endpoint == "api":
                assert paths[f"{prefix}/hello"]["get"]["tags"] == ["DifferentName"]
            else:
                assert f"{prefix}/hello" not in paths


@pytest.mark.parametrize("layout", ["none", "web", "endpoints"])
def test_absent_conventional_routers(package, layout):
    if layout != "none":
        web = package / "web"
        web.mkdir()
        (web / "__init__.py").write_text("")
        if layout == "endpoints":
            (web / "endpoints").mkdir()
            (web / "endpoints" / "__init__.py").write_text("")
    app = FastAPI()
    assert wire_module_routes(app, module_class(package)()) is False
    assert app.openapi()["paths"] == {}


@pytest.mark.parametrize("endpoint", ["api", "views"])
@pytest.mark.parametrize(
    "body", ['raise ImportError("broken endpoint")', "import missing_dependency_980"]
)
def test_broken_conventional_router_fails_boot(package, endpoint, body):
    write_endpoint(package, endpoint, body)
    with pytest.raises(ImportError):
        wire_module_routes(FastAPI(), module_class(package)())


def test_broken_parent_package_fails_boot(package):
    write_endpoint(package, "api", "")
    (package / "web" / "__init__.py").write_text("import missing_dependency_980")
    with pytest.raises(ModuleNotFoundError, match="missing_dependency_980"):
        wire_module_routes(FastAPI(), module_class(package)())


def test_explicit_hooks_win(package):
    write_endpoint(package, "api", 'raise ImportError("must not import")')

    class Custom(module_class(package)):
        __module__ = f"{package.name}.module"

        def register_routes(self, api_router, view_router):
            pass

        def locale_dirs(self):
            return {"custom_namespace": package}

    assert wire_module_routes(FastAPI(), Custom()) is False
    assert Custom().locale_dirs() == {"custom_namespace": package}


@pytest.mark.parametrize("with_entry_point", [False, True])
def test_version_from_owning_distribution(package, with_entry_point):
    dist = package.parent / "unrelated_distribution-9.8.7.dist-info"
    dist.mkdir()
    (dist / "METADATA").write_text("Name: unrelated-distribution\nVersion: 9.8.7\n")
    if with_entry_point:
        (dist / "entry_points.txt").write_text(
            f"[simple_module]\nexample = {package.name}.module:ExampleModule\n"
        )
    else:
        (dist / "top_level.txt").write_text(f"{package.name}\n")
    assert module_class(package).meta.version == "9.8.7"
    assert module_class(package, version="3.2.1").meta.version == "3.2.1"


def test_uninstalled_module_version_fallback(package):
    assert module_class(package).meta.version == "1.0.0"


def test_diagnostics_recognize_conventional_views(package):
    from simple_module_core.diagnostics import ModuleDiagnostics

    write_endpoint(package, "views", "")
    mod = module_class(package)()
    diagnostics = ModuleDiagnostics()
    assert diagnostics._check_empty_modules([mod]) == []
    assert [d.code for d in diagnostics._check_views_without_menu([mod])] == ["SM019"]


def test_diagnostics_recognize_conventional_locales(package):
    from simple_module_core.diagnostics import ModuleDiagnostics

    (package / "locales").mkdir()
    assert ModuleDiagnostics()._check_empty_modules([module_class(package)()]) == []
