"""Load-test cookies use the server's persisted key or its explicit override."""

import base64
import json
import shlex
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import pytest
from itsdangerous import TimestampSigner
from simple_module_hosting import _preapp_config

from scripts import loadtest_seed


@pytest.mark.parametrize("env_key", [None, "explicit-loadtest-key"])
async def test_scripts_loadtest_cookie_uses_resolved_host_key(
    tmp_path, monkeypatch, capsys, env_key
):
    db_path = tmp_path / "loadtest.db"
    # Keep real settings resolution and signing; isolate the DB read boundary.
    read_overrides = Mock(return_value={"secret_key": ("stored-loadtest-key", "string")})
    monkeypatch.setattr(_preapp_config, "load_host_overrides", read_overrides)
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite+aiosqlite:///{db_path}")
    monkeypatch.setenv("SM_ENVIRONMENT", "testing")
    monkeypatch.delenv("SM_SECRET_KEY", raising=False)
    if env_key:
        monkeypatch.setenv("SM_SECRET_KEY", env_key)
    create_admin = AsyncMock(return_value=SimpleNamespace(user=SimpleNamespace(id="load-user")))
    monkeypatch.setattr(loadtest_seed, "create_admin", create_admin)

    await loadtest_seed._main()

    command = shlex.split(capsys.readouterr().out)
    assert command[0] == "export"
    variable, cookie = command[1].split("=", 1)
    assert variable == "SM_LOADTEST_COOKIE"
    payload = TimestampSigner(env_key or "stored-loadtest-key").unsign(cookie)
    assert json.loads(base64.b64decode(payload)) == {"user_id": "load-user"}
    create_admin.assert_awaited_once()
    read_overrides.assert_called_once_with(f"sqlite+aiosqlite:///{db_path}", strict=False)
