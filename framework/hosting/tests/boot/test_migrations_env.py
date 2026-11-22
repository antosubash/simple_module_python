"""Public Alembic runner, including SQL-only execution and autogenerate hooks."""

from contextlib import nullcontext
from io import StringIO
from unittest.mock import Mock

import pytest
from alembic import command
from alembic.config import Config
from sqlalchemy import Column, Integer, MetaData, Table


@pytest.mark.parametrize("offline", [True, False], ids=["offline", "online"])
@pytest.mark.parametrize("locked", [True, False], ids=["wizard", "cli"])
def test_runner_uses_target_url_and_shared_hooks(tmp_path, monkeypatch, offline, locked):
    from simple_module_hosting.boot import migrations_env
    from simple_module_hosting.boot.migrations import ALEMBIC_DATABASE_URL_ATTRIBUTE

    scripts = tmp_path / "migrations"
    (scripts / "versions").mkdir(parents=True)
    (scripts / "env.py").write_text(
        "from alembic import context\n"
        "from simple_module_hosting.boot.migrations_env import run_migrations\n"
        "run_migrations(context)\n"
    )
    (scripts / "versions/initial.py").write_text(
        "from alembic import op\nimport sqlalchemy as sa\n"
        "revision = 'initial'\ndown_revision = None\n"
        "def upgrade():\n    op.create_table('marker', sa.Column('id', sa.Integer))\n"
    )
    metadata = MetaData()
    Table("marker", metadata, Column("id", Integer))
    monkeypatch.setattr(migrations_env, "build_module_metadata", lambda: metadata)
    extensions = Mock()
    monkeypatch.setattr(migrations_env, "ensure_db_extensions", extensions)
    modules = []
    monkeypatch.setattr(migrations_env, "discover_modules", lambda: modules)
    output = StringIO()
    config = Config(output_buffer=output)
    config.set_main_option("script_location", str(scripts))
    database = tmp_path / "target.db"
    url = f"sqlite+aiosqlite:///{database}"
    if locked:
        config.attributes[ALEMBIC_DATABASE_URL_ATTRIBUTE] = url
    monkeypatch.setenv("SM_DATABASE_URL", "invalid://must-not-be-used" if locked else url)
    monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
    command.upgrade(config, "heads", sql=offline)
    if offline:
        assert "CREATE TABLE marker" in output.getvalue()
        assert not database.exists()
        extensions.assert_called_once_with(None, modules)
    else:
        assert database.exists()
        assert extensions.call_args.args[0].dialect.name == "sqlite"
        assert extensions.call_args.args[1] is modules
        command.check(config)


def test_runner_configures_autogenerate_hooks(monkeypatch):
    from simple_module_hosting.boot import migrations_env

    metadata = MetaData()
    Table("owned", metadata, Column("id", Integer))
    monkeypatch.setattr(migrations_env, "build_module_metadata", lambda: metadata)
    monkeypatch.setattr(migrations_env, "ensure_db_extensions", Mock())
    monkeypatch.setattr(migrations_env, "discover_modules", list)
    context = Mock()
    context.config = Config()
    from simple_module_hosting.boot.migrations import ALEMBIC_DATABASE_URL_ATTRIBUTE

    context.config.attributes[ALEMBIC_DATABASE_URL_ATTRIBUTE] = "sqlite+aiosqlite:///:memory:"
    context.is_offline_mode.return_value = True
    context.begin_transaction.return_value = nullcontext()
    migrations_env.run_migrations(context)
    options = context.configure.call_args.kwargs
    assert options["target_metadata"] is metadata
    assert options["include_object"](metadata.tables["owned"], "owned", "table", False, None)
    assert not options["include_object"](None, "unowned", "table", True, None)
    assert options["render_item"] is migrations_env.render_item
    assert callable(options["process_revision_directives"])


@pytest.mark.parametrize("offline", [True, False], ids=["offline", "online"])
def test_runner_rejects_unsupported_dialect_without_credentials(monkeypatch, offline):
    from simple_module_hosting.boot import migrations_env
    from simple_module_hosting.boot.migrations import ALEMBIC_DATABASE_URL_ATTRIBUTE

    monkeypatch.setattr(migrations_env, "build_module_metadata", MetaData)
    context = Mock()
    context.config = Config()
    context.config.attributes[ALEMBIC_DATABASE_URL_ATTRIBUTE] = (
        "mysql+aiomysql://user:hidden-password@host/db"
    )
    context.is_offline_mode.return_value = offline
    with pytest.raises(ValueError, match="mysql") as error:
        migrations_env.run_migrations(context)
    assert "hidden-password" not in str(error.value)
