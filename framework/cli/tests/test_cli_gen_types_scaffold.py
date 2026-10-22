"""The scaffold's shipped ``api.generated.ts`` is what gen-types emits for it (#504).

A new module's pages import its generated types before anyone has run
``smpy openapi gen-types``, so the template copy must match the real output
for the sample CRUD routes; a DTO or route change in the template that is not
regenerated here would hand every new module stale types.
"""

from __future__ import annotations

import importlib
import inspect
import sys
from pathlib import Path

import pytest
from simple_module_cli import openapi_types as ot
from simple_module_cli.scaffolding import create_module

REPO = Path(__file__).resolve().parents[3]
LOCAL_TOOL = REPO / "packages" / "ui" / "node_modules" / ".bin" / "openapi-typescript"
NAME = "drift_posts"


@pytest.mark.skipif(not LOCAL_TOOL.is_file(), reason="needs `npm install` (openapi-typescript)")
def test_template_types_match_generated(tmp_path: Path, monkeypatch) -> None:
    import simple_module_hosting.app_builder as app_builder
    from simple_module_core import ModuleBase
    from simple_module_hosting import create_app, merge_host_settings

    dest = tmp_path / NAME
    create_module(dest, name=NAME, framework_version="*", standalone=False)
    pages = dest / NAME / "pages"
    shipped = (pages / ot.GENERATED_FILENAME).read_text()

    monkeypatch.syspath_prepend(str(dest))
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'x.db'}")
    # A development boot would write the sample's i18n keys into the repo.
    monkeypatch.setenv("SM_ENVIRONMENT", "testing")
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    module = importlib.import_module(f"{NAME}.module")
    cls = next(
        c
        for _, c in inspect.getmembers(module, inspect.isclass)
        if issubclass(c, ModuleBase) and c is not ModuleBase
    )
    discover = app_builder.discover_modules
    monkeypatch.setattr(
        app_builder, "discover_modules", lambda *a, **k: [*discover(*a, **k), cls()]
    )
    try:
        schema = create_app(merge_host_settings(strict=False)).openapi()
    finally:
        for key in [k for k in sys.modules if k == NAME or k.startswith(f"{NAME}.")]:
            del sys.modules[key]

    (pages / ot.GENERATED_FILENAME).unlink()
    target = ot.Target(name=cls.meta.name, package=NAME, pages_dir=pages)
    (bin_dir := tmp_path / "node_modules" / ".bin").mkdir(parents=True)
    (bin_dir / "openapi-typescript").symlink_to(LOCAL_TOOL.resolve())
    ot.generate(schema, [target], tmp_path)
    assert target.output.read_text() == shipped, (
        "templates/module/__PACKAGE__/pages/api.generated.ts.tpl is stale: regenerate it from "
        "a scaffolded module and re-template the names"
    )
