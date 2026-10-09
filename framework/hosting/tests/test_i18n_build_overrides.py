"""build_i18n_registry registers host/locales/overrides (#415)."""

from __future__ import annotations

import json

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_hosting.i18n_manifest import build_i18n_registry
from simple_module_hosting.settings import Settings


class _Users(ModuleBase):
    meta = ModuleMeta(name="users")

    def __init__(self, locales):
        self._locales = locales

    def locale_dirs(self):
        return {"users": self._locales}


def test_build_applies_host_overrides_and_not_as_host_namespace(tmp_path):
    mod_dir = tmp_path / "mod"
    mod_dir.mkdir()
    (mod_dir / "en.json").write_text(json.dumps({"login": {"aside_heading": "Old"}}))
    ov = tmp_path / "host" / "locales" / "overrides"
    ov.mkdir(parents=True)
    (ov / "en.json").write_text(json.dumps({"users.login.aside_heading": "New"}))
    (tmp_path / "host" / "locales" / "en.json").write_text(json.dumps({"x": "y"}))

    settings = Settings(database_url="sqlite+aiosqlite:///:memory:")
    registry, _ = build_i18n_registry(settings, [_Users(mod_dir)], tmp_path)
    msgs = registry.messages("en")
    assert msgs["users.login.aside_heading"] == "New"
    assert msgs["host.x"] == "y"
    assert not any(k.startswith("host.users") for k in msgs)
