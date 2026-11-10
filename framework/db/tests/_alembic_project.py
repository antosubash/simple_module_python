"""A throwaway Alembic project and SQLite database for the migration-state tests."""

from pathlib import Path

import sqlalchemy as sa

_REVISION = """revision = "{rev}"
down_revision = {down}
branch_labels = None
depends_on = None


def upgrade():
    pass


def downgrade():
    pass
"""


def write_alembic_project(root: Path, chain: list[str]) -> Path:
    """An ``alembic.ini`` over the ``"rev:down_revision"`` entries in *chain*.

    ``down_revision`` is empty for a root, so a test can build several heads
    without a real ``env.py``.
    """
    versions = root / "migrations" / "versions"
    versions.mkdir(parents=True)
    for entry in chain:
        rev, _, down = entry.partition(":")
        (versions / f"{rev}.py").write_text(
            _REVISION.format(rev=rev, down=repr(down) if down else "None")
        )
    ini = root / "alembic.ini"
    ini.write_text("[alembic]\nscript_location = %(here)s/migrations\n")
    return ini


def sqlite_database(path: Path, *statements: str) -> str:
    engine = sa.create_engine(f"sqlite:///{path}")
    with engine.begin() as conn:
        for statement in statements:
            conn.execute(sa.text(statement))
    engine.dispose()
    return f"sqlite+aiosqlite:///{path}"
