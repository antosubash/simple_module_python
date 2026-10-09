"""``python -m simple_module_core`` reports SM027 for unknown host overrides (#415)."""

from __future__ import annotations

import json

from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core import __main__ as doctor


class _Mod(ModuleBase):
    meta = ModuleMeta(name="users")

    def __init__(self, locales):
        self._locales = locales

    def locale_dirs(self):
        return {"users": self._locales}


def test_doctor_cli_reports_unknown_override_key(tmp_path, monkeypatch, capsys):
    mod_dir = tmp_path / "mod"
    mod_dir.mkdir()
    (mod_dir / "en.json").write_text(json.dumps({"login": {"aside_heading": "X"}}))
    ov = tmp_path / "host" / "locales" / "overrides"
    ov.mkdir(parents=True)
    (ov / "en.json").write_text(
        json.dumps({"users.login.aside_heading": "ok", "users.login.typo": "bad"})
    )
    mod = _Mod(mod_dir)
    monkeypatch.setattr(doctor, "discover_modules", lambda strict=True: [mod])
    monkeypatch.setattr(doctor, "find_env_file", lambda: tmp_path / ".env")
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.delenv("SM_I18N_SUPPORTED_LOCALES", raising=False)

    assert doctor.main() == 0
    err = capsys.readouterr().err
    assert "SM027" in err
    assert "users.login.typo" in err
    assert "aside_heading" not in err.split("SM027", 1)[1]
