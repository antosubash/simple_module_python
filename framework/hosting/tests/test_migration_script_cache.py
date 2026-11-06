"""``script_directory`` reuses the loaded revision map until a revision file changes."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest
from simple_module_hosting import migrations
from simple_module_hosting.migrations import resolve_head_revisions, script_directory

_INI = """\
[alembic]
script_location = %(here)s/migrations
"""

_REVISION = """\
revision = "{rev}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
"""


@pytest.fixture
def project(tmp_path: Path, monkeypatch) -> Path:
    monkeypatch.setattr(migrations, "_SCRIPTS", {})
    (tmp_path / "migrations" / "versions").mkdir(parents=True)
    repo_migrations = Path(__file__).resolve().parents[3] / "host" / "migrations"
    shutil.copy(repo_migrations / "script.py.mako", tmp_path / "migrations")
    (tmp_path / "alembic.ini").write_text(_INI)
    _write(tmp_path, "a1", None)
    return tmp_path


def _write(project: Path, rev: str, down: str | None) -> Path:
    path = project / "migrations" / "versions" / f"{rev}_rev.py"
    path.write_text(_REVISION.format(rev=rev, down=repr(down)))
    return path


def test_an_unchanged_history_reuses_the_loaded_script(project: Path) -> None:
    ini = str(project / "alembic.ini")
    assert script_directory(ini) is script_directory(ini)


def test_a_new_revision_is_seen(project: Path) -> None:
    ini = str(project / "alembic.ini")
    assert resolve_head_revisions(ini) == ("a1",)

    _write(project, "b2", "a1")

    assert resolve_head_revisions(ini) == ("b2",)


def test_an_edited_revision_is_seen(project: Path) -> None:
    ini = str(project / "alembic.ini")
    first = script_directory(ini)
    path = _write(project, "a1", None)
    stat = path.stat()
    os.utime(path, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000))

    assert script_directory(ini) is not first


def test_a_removed_revision_is_seen(project: Path) -> None:
    ini = str(project / "alembic.ini")
    second = _write(project, "b2", "a1")
    assert resolve_head_revisions(ini) == ("b2",)

    second.unlink()

    assert resolve_head_revisions(ini) == ("a1",)
