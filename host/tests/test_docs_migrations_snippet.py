"""The documented Alembic roundtrip must use its temporary database."""

import ast
import sqlite3
from pathlib import Path

from alembic import command
from alembic.config import Config
from alembic.script import ScriptDirectory

ROOT = Path(__file__).resolve().parents[2]


def test_documented_roundtrip_preserves_the_original_database(tmp_path, monkeypatch):
    sentinel = tmp_path / "sentinel.db"
    with sqlite3.connect(sentinel) as connection:
        connection.execute("CREATE TABLE sentinel (value TEXT)")
        connection.execute("INSERT INTO sentinel VALUES ('preserve me')")
    original = sentinel.read_bytes()
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{sentinel}")
    monkeypatch.chdir(ROOT)
    documentation = (ROOT / "docs/database/migrations.md").read_text()
    snippet = (
        documentation.split("## Testing migrations", 1)[1]
        .split("```python\n", 1)[1]
        .split("```", 1)[0]
    )
    tree = ast.parse(snippet)
    function = tree.body[0]
    assert isinstance(function, ast.FunctionDef), "Alembic's synchronous API needs a sync test"
    namespace = {}
    exec(compile(tree, "docs/database/migrations.md", "exec"), namespace)
    namespace["test_migration_up_then_down"](tmp_path, monkeypatch)

    target = tmp_path / "migrate_test.db"
    assert target.is_file()
    with sqlite3.connect(target) as connection:
        assert connection.execute("SELECT * FROM alembic_version").fetchall() == []
        assert (
            connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table' AND name NOT IN "
                "('alembic_version', 'sqlite_sequence')"
            ).fetchall()
            == []
        )
    assert sentinel.read_bytes() == original


def test_config_url_alone_is_overridden_by_environment(tmp_path, monkeypatch):
    environment_db = tmp_path / "environment.db"
    config_db = tmp_path / "config.db"
    monkeypatch.setenv("SM_DATABASE_URL", f"sqlite:///{environment_db}")
    monkeypatch.chdir(ROOT)
    cfg = Config("host/alembic.ini")
    cfg.set_main_option("sqlalchemy.url", f"sqlite:///{config_db}")
    command.upgrade(cfg, "heads")

    assert not config_db.exists()
    with sqlite3.connect(environment_db) as connection:
        heads = {row[0] for row in connection.execute("SELECT version_num FROM alembic_version")}
    assert heads == set(ScriptDirectory.from_config(cfg).get_heads())
