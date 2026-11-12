"""A freshly scaffolded host serves ``/admin`` with no files of its own.

GH #914: the sidebar's "Administration" link and the AdminLayout badge point
at ``/admin``, but the route and page lived only in this repository's host, so
an app made by ``smpy new`` answered 404. The overview now ships with
``simple_module_hosting`` like the setup wizard: ``create_app`` mounts the
route and ``gen-pages`` registers the page.
"""

from __future__ import annotations

import json

from simple_module_hosting.admin_overview import PAGE_OVERVIEW, PAGES_NAME, pages_dir
from simple_module_hosting.manifest import write_module_pages_manifest


def test_scaffold_carries_no_admin_code_and_resolves_the_overview(tmp_path) -> None:
    from simple_module_cli.scaffolding import create_host

    dest = tmp_path / "demo"
    create_host(dest, name="demo-host", modules=[])
    client_app = dest / "client_app"

    assert "/admin" not in (dest / "routes.py").read_text(encoding="utf-8")
    assert not list((client_app / "pages").rglob("Admin*"))

    write_module_pages_manifest([], client_app, repo_root=dest)

    manifest = json.loads((client_app / "modules.manifest.json").read_text(encoding="utf-8"))
    assert manifest[PAGES_NAME] == pages_dir().as_posix()
    assert (pages_dir() / "Overview.tsx").is_file()
    assert f"{PAGES_NAME}/Overview" == PAGE_OVERVIEW

    generated = (client_app / "modules.generated.ts").read_text(encoding="utf-8")
    assert f'"{PAGES_NAME}": import.meta.glob' in generated
    css = (client_app / "modules.generated.css").read_text(encoding="utf-8")
    assert f'@source "{pages_dir().as_posix()}/**/*.{{ts,tsx}}";' in css
