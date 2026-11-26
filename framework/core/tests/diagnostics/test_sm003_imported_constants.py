"""Imported render targets must not cause false SM003 warnings (#1219)."""

from pathlib import Path

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics import ModuleDiagnostics
from simple_module_core.diagnostics._types import DiagnosticLevel


class _Module(ModuleBase):
    __module__ = "pkg.module"
    meta = ModuleMeta(name="Example")


def _diagnostics(root: Path):
    scanner = ModuleDiagnostics()
    scanner._find_source_dir = lambda mod: root
    return [d for d in scanner.run([_Module()]) if d.code in {"SM003", "SM004"}]


def _source(root: Path, relative: str, source: str):
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(source)


@pytest.mark.parametrize(
    ("statement", "target"),
    [
        ("from pkg.core.constants import PAGE", "PAGE"),
        ("from pkg.core.constants import PAGE as dashboard", "dashboard"),
        ("import pkg.core.constants as c", "c.PAGE"),
        ("from pkg.core import constants as c", "c.PAGE"),
        ("from .core.constants import PAGE", "PAGE"),
        ("from .core import constants as c", "c.PAGE"),
        ("import pkg.core.constants", "pkg.core.constants.PAGE"),
    ],
)
@pytest.mark.parametrize(
    "assignment", ['PAGE = "Example/Dashboard"', 'PAGE: str = "Example/Dashboard"']
)
def test_resolves_imported_page_without_hiding_unused_page(tmp_path, statement, target, assignment):
    _source(tmp_path, "pages/Dashboard.tsx", "export default function Dashboard() {}")
    _source(tmp_path, "pages/Unused.tsx", "export default function Unused() {}")
    _source(tmp_path, "core/constants.py", assignment + '\nraise RuntimeError("never import me")\n')
    _source(
        tmp_path,
        "module.py",
        f"{statement}\ndef view(inertia):\n    inertia.render({target}, {{}})\n",
    )

    results = _diagnostics(tmp_path)

    assert len(results) == 1
    assert results[0].code == "SM003"
    assert results[0].level == DiagnosticLevel.WARNING
    assert "Unused.tsx" in results[0].message


@pytest.mark.parametrize("endpoint", ["web/views.py", "web/__init__.py"])
def test_resolves_parent_relative_import(tmp_path, endpoint):
    _source(tmp_path, "pages/Dashboard.tsx", "export default function Dashboard() {}")
    _source(tmp_path, "core/constants.py", 'PAGE = "Example/Dashboard"\n')
    _source(
        tmp_path,
        endpoint,
        "from ..core import constants as c\ndef view(inertia):\n    inertia.render(c.PAGE, {})\n",
    )

    assert _diagnostics(tmp_path) == []


@pytest.mark.parametrize(
    "source",
    [
        "inertia.render(UNKNOWN, {})",
        "from missing import PAGE\ninertia.render(PAGE, {})",
        "from missing import constants as c\ninertia.render(c.PAGE, {})",
        'inertia.render(f"Example/{dynamic()}", {})',
    ],
)
def test_unresolved_target_downgrades_only_sm003(tmp_path, source):
    _source(tmp_path, "pages/Dashboard.tsx", "export default function Dashboard() {}")
    _source(tmp_path, "module.py", source + '\ninertia.render("Example/Missing", {})\n')

    results = {d.code: d for d in _diagnostics(tmp_path)}

    assert results["SM003"].level == DiagnosticLevel.INFO
    assert results["SM004"].level == DiagnosticLevel.WARNING


def test_import_aliases_use_their_own_constants(tmp_path):
    for name in ("First", "Second", "Unused"):
        _source(tmp_path, f"pages/{name}.tsx", "export default function Page() {}")
    for name in ("First", "Second"):
        _source(tmp_path, f"core/{name.lower()}.py", f'PAGE = "Example/{name}"\n')
        _source(
            tmp_path,
            f"web/{name.lower()}.py",
            f"from pkg.core.{name.lower()} import PAGE as target\ninertia.render(target, {{}})\n",
        )

    results = _diagnostics(tmp_path)

    assert len(results) == 1
    assert results[0].level == DiagnosticLevel.WARNING
    assert "Unused.tsx" in results[0].message


def test_external_import_is_not_resolved_from_same_named_local_constant(tmp_path):
    root = tmp_path / "pkg"
    _source(tmp_path, "outside.py", 'PAGE = "Example/Missing"\n')
    _source(root, "core/constants.py", 'PAGE = "Example/Missing"\n')
    _source(root, "pages/Dashboard.tsx", "export default function Dashboard() {}")
    _source(root, "module.py", "from outside import PAGE\ninertia.render(PAGE, {})\n")

    results = _diagnostics(root)

    assert [(d.code, d.level) for d in results] == [("SM003", DiagnosticLevel.INFO)]
