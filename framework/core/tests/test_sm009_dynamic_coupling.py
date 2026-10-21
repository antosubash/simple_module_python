"""SM009 detects literal dynamic imports without executing framework code."""

from pathlib import Path

import pytest
from simple_module_core.diagnostics import _coupling
from simple_module_core.diagnostics._types import DiagnosticLevel
from simple_module_core.module import ModuleBase, ModuleMeta


class _Plugin(ModuleBase):
    __module__ = "sample_plugin.module"
    meta = ModuleMeta(name="SamplePlugin")


@pytest.fixture
def framework_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(
        _coupling,
        "_find_package_dir",
        lambda package: tmp_path if package == "simple_module_core" else None,
    )
    return tmp_path / "loader.py"


@pytest.mark.parametrize(
    "source",
    [
        "import importlib\nimportlib.import_module('sample_plugin.service')",
        "import importlib as il\nil.import_module('sample_plugin')",
        "from importlib import import_module\nimport_module('sample_plugin.service')",
        "from importlib import import_module as im\nim('sample_plugin.service')",
        "# builtin\n__import__('sample_plugin.service')",
        "import importlib.util\nimportlib.util.find_spec('sample_plugin.service')",
        "import importlib as il\nil.util.find_spec('sample_plugin.service')",
        "import importlib\nimportlib.import_module(name='sample_plugin.service')",
        "# builtin keyword\n__import__(name='sample_plugin')",
        "import importlib.util\nimportlib.util.find_spec(name='sample_plugin')",
        'import importlib\nimportlib.import_module(f"sample_plugin.{suffix}")',
        'from importlib import import_module as im\nim(name=f"sample_plugin.api.{suffix}")',
        "# static regression\nimport sample_plugin.service",
        "# static regression\nfrom sample_plugin import service",
    ],
)
def test_sm009_flags_plugin_import(framework_file: Path, source: str) -> None:
    framework_file.write_text(source)
    results = _coupling.check_framework_module_coupling([_Plugin()])
    assert len(results) == 1
    diagnostic = results[0]
    assert diagnostic.code == "SM009"
    assert diagnostic.level == DiagnosticLevel.ERROR
    assert diagnostic.module_name == "SamplePlugin"
    assert diagnostic.file == f"{framework_file}:2"
    assert "sample_plugin" in diagnostic.message


@pytest.mark.parametrize(
    "call",
    [
        "importlib.import_module('simple_module_core.module')",
        "importlib.import_module('json')",
        "importlib.util.find_spec('pathlib')",
        "__import__('json')",
        "importlib.import_module('sample_plugin_extra.service')",
        "importlib.import_module(module_name)",
        "importlib.import_module('sample_plugin.' + suffix)",
        'importlib.import_module(f"{package}.service")',
        'importlib.import_module(f"sample_plugin{suffix}.service")',
        "importlib.import_module()",
        "importlib.import_module(123)",
        "other.import_module('sample_plugin.service')",
        "import_module('sample_plugin.service')",
    ],
)
def test_sm009_ignores_harmless_or_computed_imports(framework_file: Path, call: str) -> None:
    framework_file.write_text(f"import importlib.util\n{call}\n")
    assert _coupling.check_framework_module_coupling([_Plugin()]) == []


def test_sm009_skips_templates(framework_file: Path) -> None:
    templates = framework_file.parent / "templates"
    templates.mkdir()
    (templates / "loader.py").write_text("__import__('sample_plugin')")
    assert _coupling.check_framework_module_coupling([_Plugin()]) == []
