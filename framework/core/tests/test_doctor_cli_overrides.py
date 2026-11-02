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


def _run_doctor(tmp_path, monkeypatch, overrides: dict | str) -> int:
    """Run the doctor CLI over one ``users`` module plus ``overrides`` as ``en.json``.

    A ``str`` is written verbatim, for malformed JSON.
    """
    mod_dir = tmp_path / "mod"
    mod_dir.mkdir()
    (mod_dir / "en.json").write_text(json.dumps({"login": {"aside_heading": "X"}}))
    ov = tmp_path / "host" / "locales" / "overrides"
    ov.mkdir(parents=True)
    (ov / "en.json").write_text(overrides if isinstance(overrides, str) else json.dumps(overrides))
    mod = _Mod(mod_dir)
    monkeypatch.setattr(doctor, "discover_modules", lambda strict=True: [mod])
    monkeypatch.setattr(doctor, "find_env_file", lambda: tmp_path / ".env")
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.delenv("SM_I18N_SUPPORTED_LOCALES", raising=False)
    return doctor.main()


def test_doctor_cli_reports_unknown_override_key(tmp_path, monkeypatch, capsys):
    overrides = {"users.login.aside_heading": "ok", "users.login.typo": "bad"}
    assert _run_doctor(tmp_path, monkeypatch, overrides) == 0
    err = capsys.readouterr().err
    assert "SM027" in err
    assert "users.login.typo" in err
    assert "aside_heading" not in err.split("SM027", 1)[1]


def test_doctor_cli_accepts_hosting_overrides(tmp_path, monkeypatch, capsys):
    """The setup wizard's ``hosting.*`` keys are real: only the typo is SM027.

    The app's registry always loads the ``hosting`` catalog; doctor must too.
    """
    overrides = {"hosting.setup.title": "Welcome", "hosting.setup.titel": "typo"}
    _run_doctor(tmp_path, monkeypatch, overrides)
    err = capsys.readouterr().err
    assert "SM027" in err
    reported = err.split("(skipped):", 1)[1].splitlines()[0]
    assert [k.strip() for k in reported.split(",")] == ["hosting.setup.titel"]


def test_doctor_cli_reports_malformed_overrides(tmp_path, monkeypatch, capsys):
    """Malformed overrides JSON is an SM016 finding, not a traceback."""
    assert _run_doctor(tmp_path, monkeypatch, '{"users.login.aside_heading": ') == 1
    err = capsys.readouterr().err
    assert "SM016" in err
    assert str(tmp_path / "host" / "locales" / "overrides" / "en.json") in err
    assert "Traceback" not in err


def test_doctor_cli_reports_non_object_overrides(tmp_path, monkeypatch, capsys):
    assert _run_doctor(tmp_path, monkeypatch, "[]") == 1
    assert "SM016" in capsys.readouterr().err
