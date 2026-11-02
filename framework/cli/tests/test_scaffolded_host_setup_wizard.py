"""A freshly scaffolded host gets a working /setup with no files of its own.

GH #351: ``SetupMiddleware`` redirected every request to ``/setup`` while the
route and page lived only in the framework repo's unpublished host, so a host
made by ``smpy create-host`` answered ``/`` → ``/setup`` → 404. The wizard now
ships with ``simple_module_hosting``: ``create_app`` mounts the route and
``gen-pages`` registers the page, so the scaffold must stay free of both.
"""

from __future__ import annotations

import json
import re

import pytest
from simple_module_hosting.manifest import write_module_pages_manifest
from simple_module_hosting.setup_wizard import PAGES_NAME, pages_dir

pytestmark = pytest.mark.anyio


async def test_scaffold_carries_no_setup_code_and_resolves_the_wizard(tmp_path) -> None:
    from simple_module_cli.scaffolding import create_host

    dest = tmp_path / "demo"
    create_host(dest, name="demo-host", modules=[])
    client_app = dest / "client_app"

    # Nothing host-side: no route module, no page.
    assert not (dest / "routes_setup.py").exists()
    assert not list((client_app / "pages").rglob("Setup*"))
    assert "setup" not in (dest / "main.py").read_text(encoding="utf-8").replace(
        "setup_logging", ""
    )

    # What `smpy gen-pages` writes for this host, with no modules installed.
    write_module_pages_manifest([], client_app, repo_root=dest)

    manifest = json.loads((client_app / "modules.manifest.json").read_text(encoding="utf-8"))
    assert manifest[PAGES_NAME] == pages_dir().as_posix()
    assert (pages_dir() / "Wizard.tsx").is_file()

    generated = (client_app / "modules.generated.ts").read_text(encoding="utf-8")
    assert f'"{PAGES_NAME}": import.meta.glob' in generated

    # The scaffold's resolver keys a module glob entry as `<name>/<path under pages/>`,
    # which is how `inertia.render("Setup/Wizard")` finds the page.
    pages_ts = (client_app / "pages.ts").read_text(encoding="utf-8")
    assert "pages[`${moduleName}/${match[1]}`]" in pages_ts
    match = re.search(r"/pages/(.+)\.tsx$", (pages_dir() / "Wizard.tsx").as_posix())
    assert match and f"{PAGES_NAME}/{match.group(1)}" == "Setup/Wizard"

    # Tailwind must scan the wheel's wizard, and Vite must be allowed to serve it.
    css = (client_app / "modules.generated.css").read_text(encoding="utf-8")
    assert f'@source "{pages_dir().as_posix()}/**/*.{{ts,tsx}}";' in css
    assets = json.loads((client_app / "modules.assets.json").read_text(encoding="utf-8"))
    assert assets[PAGES_NAME]["pages"] == pages_dir().as_posix()
