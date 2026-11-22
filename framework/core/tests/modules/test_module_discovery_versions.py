"""Only discovery knows which distribution owns an entry point (GH #980)."""

import importlib
import sys
from dataclasses import FrozenInstanceError
from importlib import metadata

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.modules.discovery import discover_modules


@pytest.fixture
def installed_modules(tmp_path, monkeypatch):
    monkeypatch.syspath_prepend(str(tmp_path))
    distributions = []

    def install(package, version, *, explicit_version=None, reexport=False):
        root = tmp_path.joinpath(*package.split("."))
        root.mkdir(parents=True)
        (root / "__init__.py").write_text("")
        version_arg = "" if explicit_version is None else f", version={explicit_version!r}"
        (root / "module.py").write_text(
            "from simple_module_core import ModuleBase, ModuleMeta\n"
            "class ExampleModule(ModuleBase):\n"
            f"    meta = ModuleMeta(name={package!r}{version_arg})\n"
        )
        target = f"{package}.module:ExampleModule"
        if reexport:
            (tmp_path / "editable_facade.py").write_text(
                f"from {package}.module import ExampleModule\n"
            )
            target = "editable_facade:ExampleModule"
        dist = tmp_path / f"dist_{root.name}-{version}.dist-info"
        dist.mkdir()
        (dist / "METADATA").write_text(f"Name: dist-{root.name}\nVersion: {version}\n")
        (dist / "entry_points.txt").write_text(f"[simple_module]\nexample = {target}\n")
        if reexport:
            (dist / "direct_url.json").write_text(
                '{"url": "file:///editable-source", "dir_info": {"editable": true}}'
            )
        distributions.append(metadata.PathDistribution(dist))
        return importlib.import_module(f"{package}.module").ExampleModule

    monkeypatch.setattr(
        "simple_module_core.modules.discovery.entry_points",
        lambda group: [
            ep for dist in distributions for ep in dist.entry_points if ep.group == group
        ],
    )
    yield install
    for name in list(sys.modules):
        if name == "acme" or name.startswith("acme.") or name == "editable_facade":
            sys.modules.pop(name, None)


def test_namespace_distributions_get_their_own_versions(installed_modules):
    billing = installed_modules("acme.billing", "2.3.4")
    orders = installed_modules("acme.orders", "5.6.7")
    modules = discover_modules(strict=True)
    assert {m.meta.name: m.meta.version for m in modules} == {
        "acme.billing": "2.3.4",
        "acme.orders": "5.6.7",
    }
    assert billing.meta.version == orders.meta.version == "1.0.0"


def test_entry_point_without_distribution_keeps_fallback(installed_modules, monkeypatch):
    cls = installed_modules("acme.billing", "9.8.7")
    ep = metadata.EntryPoint(
        name="example", value=f"{cls.__module__}:ExampleModule", group="simple_module"
    )
    monkeypatch.setattr("simple_module_core.modules.discovery.entry_points", lambda group: [ep])
    (mod,) = discover_modules(strict=True)
    assert mod.meta.version == "1.0.0"
    assert type(mod.meta.version) is str


@pytest.mark.parametrize("explicit_version", [None, "1.0.0", "3.2.1"])
def test_editable_entry_point_version_preserves_class_metadata(installed_modules, explicit_version):
    cls = installed_modules(
        "acme.billing", "9.8.7", explicit_version=explicit_version, reexport=True
    )
    original = cls.meta
    for _ in range(2):
        (mod,) = discover_modules(strict=True)
        assert mod.meta.version == (explicit_version or "9.8.7")
        assert type(mod.meta.version) is str
        assert cls.meta is original
        assert cls().meta.version == (explicit_version or "1.0.0")
        with pytest.raises(FrozenInstanceError):
            mod.meta.version = "changed"


def test_class_definition_does_not_scan_distribution_metadata(monkeypatch):
    def unexpected_scan(*args, **kwargs):
        raise AssertionError("class creation must not scan installed distributions")

    monkeypatch.setattr(metadata, "entry_points", unexpected_scan)
    monkeypatch.setattr(metadata, "packages_distributions", unexpected_scan)

    class AdHoc(ModuleBase):
        meta = ModuleMeta(name="AdHoc")

    assert AdHoc().meta.version == "1.0.0"
