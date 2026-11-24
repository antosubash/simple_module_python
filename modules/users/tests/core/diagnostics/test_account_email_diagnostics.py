"""Doctor warns when no configured origin or request allowlist can supply links."""

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core import __main__ as doctor
from simple_module_core.diagnostics import DiagnosticLevel
from users.core.diagnostics import account_email_diagnostics


@pytest.mark.parametrize(
    ("environment", "stored_host", "stored_users", "warns"),
    [
        ({}, {}, {}, True),
        ({"SM_PUBLIC_BASE_URL": "https://env.example"}, {}, {}, False),
        ({}, {"public_base_url": ("https://host.example", "string")}, {}, False),
        ({}, {}, {"base_url": ("https://users.example", "string")}, False),
        ({}, {"forwarded_host_allowlist": ('["*.example"]', "json")}, {}, False),
        (
            {"SM_PUBLIC_BASE_URL": ""},
            {"public_base_url": ("https://host.example", "string")},
            {},
            True,
        ),
    ],
)
def test_account_email_origin_warning(monkeypatch, environment, stored_host, stored_users, warns):
    async def stored_origins(_database_url):
        return stored_host, stored_users

    for key in ("SM_PUBLIC_BASE_URL", "SM_FORWARDED_HOST_ALLOWLIST"):
        monkeypatch.delenv(key, raising=False)
    for key, value in environment.items():
        monkeypatch.setenv(key, value)
    monkeypatch.setattr("users.core.diagnostics._stored_origins", stored_origins)

    findings = account_email_diagnostics("sqlite+aiosqlite:///:memory:", "Users")
    if warns:
        (finding,) = findings
        assert finding.code == "SM035"
        assert finding.level == DiagnosticLevel.WARNING
    else:
        assert not findings


@pytest.mark.parametrize("invalid_result", [False, True])
def test_doctor_reports_module_hook_failure_and_continues(
    monkeypatch, capsys, tmp_path, invalid_result
):
    from users.module import UsersModule

    class BrokenModule(ModuleBase):
        meta = ModuleMeta(name="BrokenModule")

        def doctor_diagnostics(self, database_url):
            if invalid_result:
                return ["sensitive database connection details"]
            raise ValueError("sensitive database connection details")

    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{tmp_path / 'absent.db'}")
    monkeypatch.setenv("SM_PUBLIC_BASE_URL", "")
    monkeypatch.setenv("SM_FORWARDED_HOST_ALLOWLIST", "[]")
    monkeypatch.setattr(doctor, "parse_dotenv", dict)
    monkeypatch.setattr(doctor, "discover_modules", lambda strict: [BrokenModule(), UsersModule()])
    monkeypatch.setattr(doctor, "run_diagnostics", lambda *args, **kwargs: [])

    assert doctor.main() == 1
    output = capsys.readouterr().err
    assert "SM036 [ERROR] BrokenModule" in output
    assert "SM035 [WARNING] Users" in output
    assert "sensitive database connection details" not in output
    assert not (tmp_path / "absent.db").exists()
