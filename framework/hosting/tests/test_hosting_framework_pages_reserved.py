"""The framework's own page names cannot be taken by a module.

``gen-pages`` registers the setup wizard and the admin overview next to the
modules' pages, keyed by name. A module named ``Admin`` or ``Setup`` would
otherwise have its entry overwritten and its pages stop resolving, silently.
"""

from __future__ import annotations

import pytest
from simple_module_hosting import manifest
from simple_module_hosting.admin_overview import PAGES_NAME


def test_a_module_named_like_framework_pages_is_refused(tmp_path, monkeypatch) -> None:
    pages = tmp_path / "pages"
    pages.mkdir()
    monkeypatch.setattr(manifest, "compute_module_pages", lambda modules: {PAGES_NAME: pages})

    with pytest.raises(ValueError, match="reserved"):
        manifest.write_module_pages_manifest([], tmp_path / "client_app", repo_root=tmp_path)
