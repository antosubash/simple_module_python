"""Prepared revisions belong to the host and execute without module imports (#711)."""

import importlib.util

import pytest
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
from alembic.script import ScriptDirectory
from simple_module_cli.cli import app
from typer.testing import CliRunner


def _host(tmp_path, monkeypatch):
    monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
    host = tmp_path / "host"
    versions = host / "migrations/versions"
    versions.mkdir(parents=True)
    (host / "alembic.ini").write_text("[alembic]\nscript_location = %(here)s/migrations\n")
    (versions / "local.py").write_text(
        "revision = 'local'\ndown_revision = None\nbranch_labels = None\n"
    )
    monkeypatch.chdir(tmp_path)
    return host, versions


def _prepare(tmp_path, monkeypatch, upgrade):
    host, versions = _host(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["migrations", "prepare", upgrade, "--head", "local"])
    assert result.exit_code == 0, result.output
    generated = [p for p in versions.glob("*.py") if p.name != "local.py"]
    assert len(generated) == 1
    spec = importlib.util.spec_from_file_location("prepared_revision", generated[0])
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    from alembic.config import Config

    script = ScriptDirectory.from_config(Config(str(host / "alembic.ini")))
    assert script.get_revision(revision.revision).down_revision == "local"
    return revision


def test_cli_prepared_mail_revision_target_wins_and_roundtrips(tmp_path, monkeypatch):
    revision = _prepare(tmp_path, monkeypatch, "mail.settings_namespace_v1")
    assert revision.branch_labels == ("mail",)
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(
                sa.text(
                    "CREATE TABLE settings_setting "
                    "(scope TEXT, scope_id TEXT, key TEXT, value TEXT)"
                )
            )
            rows = [
                ("system", "", "users.mailer", "smtp"),
                ("system", "", "users.smtp_host", "old"),
                ("system", "", "mail.smtp_host", "new"),
                ("tenant", "one", "users.mailer", "untouched"),
            ]
            for scope, scope_id, key, value in rows:
                conn.execute(
                    sa.text("INSERT INTO settings_setting VALUES (:s, :i, :k, :v)"),
                    {"s": scope, "i": scope_id, "k": key, "v": value},
                )
            with Operations.context(MigrationContext.configure(conn)):
                revision.upgrade()
                revision.upgrade()
                assert conn.execute(
                    sa.text("SELECT key, value FROM settings_setting ORDER BY key")
                ).all() == [
                    ("mail.backend", "smtp"),
                    ("mail.smtp_host", "new"),
                    ("users.mailer", "untouched"),
                ]
                revision.downgrade()
                assert (
                    conn.execute(
                        sa.text("SELECT value FROM settings_setting WHERE key='users.smtp_host'")
                    ).scalar()
                    == "new"
                )
    finally:
        engine.dispose()


def test_cli_prepared_token_revision_invalidates_before_altering(tmp_path, monkeypatch):
    revision = _prepare(tmp_path, monkeypatch, "users.hashed_bearer_tokens_v1")
    assert revision.branch_labels == ("users",)
    engine = sa.create_engine("sqlite://")
    try:
        with engine.begin() as conn:
            conn.execute(sa.text("CREATE TABLE users_refresh_token (token CHAR(32) PRIMARY KEY)"))
            conn.execute(sa.text("CREATE TABLE users_access_token (token VARCHAR(43) PRIMARY KEY)"))
            for name in ["refresh", "access"]:
                conn.execute(sa.text(f"INSERT INTO users_{name}_token VALUES ('plaintext')"))
            with Operations.context(MigrationContext.configure(conn)):
                revision.upgrade()
                for name in ["refresh", "access"]:
                    table = f"users_{name}_token"
                    assert conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
                    assert sa.inspect(conn).get_columns(table)[0]["type"].length == 64
                    conn.execute(sa.text(f"INSERT INTO {table} VALUES ('{'a' * 64}')"))
                revision.downgrade()
                for name, length in [("refresh", 32), ("access", 43)]:
                    table = f"users_{name}_token"
                    assert conn.scalar(sa.text(f"SELECT count(*) FROM {table}")) == 0
                    assert sa.inspect(conn).get_columns(table)[0]["type"].length == length
    finally:
        engine.dispose()


@pytest.mark.parametrize(
    "args",
    [
        ["unknown", "--head", "local"],
        ["mail.settings_namespace_v1"],
        ["mail.settings_namespace_v1", "--head", "missing"],
    ],
)
def test_cli_prepare_rejects_invalid_input_without_writing(tmp_path, monkeypatch, args):
    _, versions = _host(tmp_path, monkeypatch)
    result = CliRunner().invoke(app, ["migrations", "prepare", *args])
    assert result.exit_code != 0
    assert [p.name for p in versions.glob("*.py")] == ["local.py"]


def test_cli_prepare_flat_host_reuses_label_and_attaches_explicit_head(tmp_path, monkeypatch):
    host, versions = _host(tmp_path, monkeypatch)
    (versions / "local.py").write_text(
        "revision = 'local'\ndown_revision = None\nbranch_labels = ('mail',)\n"
    )
    monkeypatch.chdir(host)
    result = CliRunner().invoke(
        app, ["migrations", "prepare", "mail.settings_namespace_v1", "--head", "mail@head"]
    )
    assert result.exit_code == 0, result.output
    from alembic.config import Config

    script = ScriptDirectory.from_config(Config(str(host / "alembic.ini")))
    head = script.get_revision("mail@head")
    assert head.down_revision == "local"
    assert head.module.branch_labels is None
    assert not list(tmp_path.rglob("*.db"))


def test_cli_prepare_rejects_ambiguous_heads_and_non_heads(tmp_path, monkeypatch):
    _, versions = _host(tmp_path, monkeypatch)
    (versions / "second.py").write_text(
        "revision = 'second'\ndown_revision = 'local'\nbranch_labels = None\n"
    )
    (versions / "third.py").write_text(
        "revision = 'third'\ndown_revision = None\nbranch_labels = None\n"
    )
    for head in ["heads", "head", "base", "local"]:
        result = CliRunner().invoke(
            app, ["migrations", "prepare", "mail.settings_namespace_v1", "--head", head]
        )
        assert result.exit_code != 0, result.output
    assert len(list(versions.glob("*.py"))) == 3


@pytest.mark.parametrize(
    "upgrade_id", ["mail.settings_namespace_v1", "users.hashed_bearer_tokens_v1"]
)
def test_cli_prepared_recipe_runs_with_framework_imports_blocked(tmp_path, monkeypatch, upgrade_id):
    import subprocess
    import sys

    _prepare(tmp_path, monkeypatch, upgrade_id)
    generated = next(
        (tmp_path / "host/migrations/versions").glob(f"*_{upgrade_id.replace('.', '_')}.py")
    )
    code = """
import importlib.abc
import runpy
import sys
class BlockFramework(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.startswith(('simple_module_', 'mail', 'users')):
            raise ImportError(fullname)
sys.meta_path.insert(0, BlockFramework())
namespace = runpy.run_path(sys.argv[1])
import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations
with sa.create_engine('sqlite://').begin() as conn:
    conn.execute(sa.text('CREATE TABLE settings_setting (scope TEXT, scope_id TEXT, key TEXT)'))
    conn.execute(sa.text('CREATE TABLE users_refresh_token (token CHAR(32) PRIMARY KEY)'))
    conn.execute(sa.text('CREATE TABLE users_access_token (token VARCHAR(43) PRIMARY KEY)'))
    with Operations.context(MigrationContext.configure(conn)):
        namespace['upgrade']()
        namespace['downgrade']()
"""
    subprocess.run([sys.executable, "-I", "-c", code, str(generated)], check=True, timeout=15)
