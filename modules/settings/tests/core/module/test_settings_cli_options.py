"""Importer filters, validation and production CLI contracts without a database."""

from __future__ import annotations

from contextlib import asynccontextmanager
from types import SimpleNamespace

import pytest
import typer
from fastapi import FastAPI
from pydantic import Field, field_validator, model_validator
from settings.cli import app, import_from_env_impl
from simple_module_core.settings.module_settings import module_settings_registry
from simple_module_core.settings.settings_base import DbBackedSettings
from typer.testing import CliRunner
from users.core.settings import UsersSettings


class StorageSettings(DbBackedSettings):
    bucket: str = ""
    limit: int = Field(default=10, ge=1)
    tags: list[str] = Field(default_factory=list)
    minimum: int = 1
    maximum: int = 10

    @field_validator("bucket")
    @classmethod
    def check_bucket(cls, value: str) -> str:
        if value.startswith("bad"):
            raise ValueError(f"Invalid bucket {value.title()!r}")
        return value

    @model_validator(mode="after")
    def check_limits(self):
        if self.minimum > self.maximum:
            raise ValueError("minimum must not exceed maximum")
        return self


class MemoryStore:
    def __init__(self):
        self.rows = {}
        self.committed = False

    async def get_overrides(self, package):
        return {name: row for (pkg, name), row in self.rows.items() if pkg == package}

    async def set_override(self, package, field, raw, vtype):
        self.rows[package, field] = (raw, vtype)

    async def commit(self):
        self.committed = True


@pytest.fixture
def importer(monkeypatch, tmp_path):
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    api = FastAPI()
    registry = module_settings_registry(api)
    registry.register("file_storage", StorageSettings)
    registry.register("users", UsersSettings)
    registry.register("background_tasks", StorageSettings)
    return api, MemoryStore()


@pytest.mark.parametrize(
    ("options", "expected"),
    [
        ({}, {"file_storage", "users", "background_tasks"}),
        ({"only": ["FiLe_StOrAgE"]}, {"file_storage"}),
        ({"only": ["users", "background_tasks"]}, {"users", "background_tasks"}),
        ({"prefixes": ["sm_file_storage_"]}, {"file_storage"}),
        ({"prefixes": ["SM_USERS_", "SM_BG_TASKS_"]}, {"users", "background_tasks"}),
        ({"prefixes": ["sm_"]}, {"file_storage", "users", "background_tasks"}),
        ({"only": ["users"], "prefixes": ["SM_FILE_STORAGE_"]}, {"users", "file_storage"}),
    ],
)
async def test_filters_select_only_matching_variables(importer, options, expected):
    api, store = importer
    count = await import_from_env_impl(
        api,
        store,
        environ={
            "SM_FILE_STORAGE_BUCKET": "storage-value",
            "SM_USERS_BASE_URL": "https://users.example",
            "SM_BG_TASKS_BUCKET": "bg-value",
        },
        **options,
    )
    assert {package for package, _ in store.rows} == expected
    assert count == len(expected)


def test_unknown_module_lists_known_names_before_writes(cli_importer):
    result = CliRunner().invoke(app, ["import-from-env", "--only", "typo"])
    assert result.exit_code == 2
    for name in ("typo", "file_storage", "users", "background_tasks"):
        assert name in result.output
    assert cli_importer.rows == {}
    assert not cli_importer.committed


async def test_prints_setting_names_never_values(importer, capsys):
    api, store = importer
    await import_from_env_impl(api, store, environ={"SM_FILE_STORAGE_BUCKET": "private-value"})
    output = capsys.readouterr().out
    assert "file_storage.bucket" in output
    assert "private-value" not in output


@pytest.mark.parametrize(
    "environ, name, message",
    [
        ({"SM_USERS_SIGNUP_DEFAULT_ROLE": "ADMIN"}, "SM_USERS_SIGNUP_DEFAULT_ROLE", "value_error"),
        ({"SM_FILE_STORAGE_LIMIT": "-17"}, "SM_FILE_STORAGE_LIMIT", "greater_than_equal"),
        ({"SM_FILE_STORAGE_LIMIT": "not-an-int"}, "SM_FILE_STORAGE_LIMIT", "int"),
        ({"SM_USERS_ALLOW_SIGNUP": "not-a-bool"}, "SM_USERS_ALLOW_SIGNUP", "bool"),
        ({"SM_FILE_STORAGE_TAGS": "not-json"}, "SM_FILE_STORAGE_TAGS", "json"),
        ({"SM_FILE_STORAGE_BUCKET": "bad-private"}, "SM_FILE_STORAGE_BUCKET", "value_error"),
        ({"SM_FILE_STORAGE_BUCKET": "x" * 4001}, "SM_FILE_STORAGE_BUCKET", "string_too_long"),
        (
            {"SM_FILE_STORAGE_MINIMUM": "24", "SM_FILE_STORAGE_MAXIMUM": "18"},
            "SM_FILE_STORAGE_MINIMUM",
            "value_error",
        ),
    ],
)
async def test_invalid_batch_writes_nothing(importer, capsys, environ, name, message):
    api, store = importer
    # Also catches writing valid variables before discovering a later invalid one.
    environ = {
        "SM_BG_TASKS_BUCKET": "valid-private-bucket",
        "SM_USERS_BASE_URL": "https://private.example",
        **environ,
    }
    with pytest.raises(typer.Exit) as exc:
        await import_from_env_impl(api, store, environ=environ)
    assert exc.value.exit_code != 0
    assert store.rows == {}
    output = capsys.readouterr().err
    assert name in output
    assert message in output
    for value in environ.values():
        assert value not in output
        assert value.upper() not in output
        assert value.title() not in output


async def test_validates_candidates_together_with_existing_overrides(importer):
    api, store = importer
    store.rows["file_storage", "maximum"] = ("30", "int")
    assert (
        await import_from_env_impl(
            api, store, environ={"SM_FILE_STORAGE_MINIMUM": "24", "SM_FILE_STORAGE_TAGS": '["one"]'}
        )
        == 2
    )
    assert store.rows["file_storage", "minimum"] == ("24", "int")
    assert store.rows["file_storage", "tags"] == ('["one"]', "json")


@pytest.mark.parametrize("source", ["process", "dotenv"])
async def test_filtered_batch_cannot_borrow_unselected_environment(
    importer, monkeypatch, tmp_path, source
):
    from simple_module_hosting.config.host_settings import HostSettings

    api, store = importer
    module_settings_registry(api).register("host", HostSettings)
    if source == "process":
        monkeypatch.setenv("SM_I18N_SUPPORTED_LOCALES", '["en", "de"]')
    else:
        (tmp_path / ".env").write_text('SM_I18N_SUPPORTED_LOCALES=["en", "de"]\n')
    with pytest.raises(typer.Exit):
        await import_from_env_impl(
            api, store, environ={"SM_I18N_DEFAULT_LOCALE": "de"}, prefixes=["SM_I18N_DEFAULT_"]
        )
    assert store.rows == {}


async def test_skips_variables_outside_db_settings_registry(importer, capsys):
    from simple_module_hosting.config.host_settings import HostSettings

    api, store = importer
    module_settings_registry(api).register("host", HostSettings)
    names = (
        "SM_USERS_RESET_PASSWORD_TOKEN_SECRET",
        "SM_USERS_VERIFICATION_TOKEN_SECRET",
        "SM_USERS_BOOTSTRAP_PASSWORD",
        "SM_DATABASE_URL",
        "SM_BG_TASKS_UNKNOWN",
        "SM_KEYCLOAK_UNKNOWN",
    )
    count = await import_from_env_impl(api, store, environ=dict.fromkeys(names, "sensitive-value"))
    assert count == 0
    assert store.rows == {}
    output = capsys.readouterr().out
    for name in names:
        assert name in output
    assert "skip" in output.lower()
    assert "DB" in output
    assert "sensitive-value" not in output


@pytest.mark.parametrize(
    "field, raw, vtype",
    [("limit", "private-invalid-int", "int"), ("bucket", "bad-private", "string")],
)
async def test_existing_malformed_override_aborts_without_echoing_value(
    importer, capsys, field, raw, vtype
):
    api, store = importer
    store.rows["file_storage", field] = (raw, vtype)
    with pytest.raises(typer.Exit):
        await import_from_env_impl(api, store, environ={"SM_FILE_STORAGE_MAXIMUM": "20"})
    assert len(store.rows) == 1
    output = capsys.readouterr().err
    assert f"SM_FILE_STORAGE_{field.upper()}" in output
    assert all(value not in output for value in (raw, raw.upper(), raw.title()))


@pytest.fixture
def cli_importer(importer, monkeypatch):
    api, store = importer

    @asynccontextmanager
    async def session_factory():
        yield store

    api.state.sm = SimpleNamespace(db=SimpleNamespace(session_factory=session_factory))
    monkeypatch.setattr("simple_module_hosting.config.settings.Settings", lambda: None)
    monkeypatch.setattr("simple_module_hosting.boot.app_builder.create_app", lambda _: api)
    monkeypatch.setattr("settings.core.service.SettingService", lambda session: session)
    monkeypatch.setattr("settings.cli.SettingsStore", lambda service: service)
    # Supply only this test's env instead of inheriting the workstation environment.
    monkeypatch.setattr("settings.cli.os.environ", {})
    return store


@pytest.mark.parametrize("mounted", [False, True])
def test_typer_subcommand_executes_filters(cli_importer, monkeypatch, mounted):
    monkeypatch.setenv("SM_FILE_STORAGE_BUCKET", "bucket-private")
    monkeypatch.setenv("SM_USERS_BASE_URL", "https://users-private.example")
    monkeypatch.setenv("SM_BG_TASKS_BUCKET", "background-private")
    cli = app
    args = ["import-from-env", "--only", "FILE_STORAGE", "--only", "users"]
    args.extend(["--prefix", "SM_BG_TASKS_"])
    if mounted:
        cli = typer.Typer()
        cli.add_typer(app, name="settings")
        args.insert(0, "settings")
    result = CliRunner().invoke(cli, args)
    assert result.exit_code == 0, result.output
    assert len(cli_importer.rows) == 3
    assert cli_importer.committed
    assert "Imported 3 override(s)" in result.output
    assert "file_storage.bucket" in result.output
    assert "private" not in result.output


def test_cli_invalid_value_exits_without_commit(cli_importer, monkeypatch):
    monkeypatch.setenv("SM_USERS_SIGNUP_DEFAULT_ROLE", "ADMIN")
    result = CliRunner().invoke(app, ["import-from-env"])
    assert result.exit_code == 1
    assert not cli_importer.committed
    assert not cli_importer.rows
    assert "SM_USERS_SIGNUP_DEFAULT_ROLE" in result.output
    assert "ADMIN" not in result.output
    assert "Imported 0 override(s)" in result.output
