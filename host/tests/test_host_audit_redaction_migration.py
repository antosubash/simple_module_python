"""Historical audit hardening keeps the trail and removes credential values."""

import importlib.util
from pathlib import Path

import sqlalchemy as sa
from alembic.migration import MigrationContext
from alembic.operations import Operations


def test_upgrade_scrubs_credentials_and_preserves_other_changes():
    path = (
        Path(__file__).parents[1] / "migrations/versions/b8d4f2a6c901_redact_audit_credentials.py"
    )
    spec = importlib.util.spec_from_file_location("audit_hardening_revision", path)
    revision = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(revision)
    engine = sa.create_engine("sqlite://")
    metadata = sa.MetaData()
    audit = sa.Table(
        "audit_log_audit_entry",
        metadata,
        sa.Column("id", sa.String, primary_key=True),
        sa.Column("entity_type", sa.String),
        sa.Column("entity_id", sa.String),
        sa.Column("changes", sa.JSON),
    )
    metadata.create_all(engine)
    cases = [
        ("Setting", "1", "value"),
        ("LeaseRow", "lease", "holder"),
        ("User", "2", "hashed_password"),
        ("OAuthAccount", "3", "access_token"),
        ("OAuthAccount", "4", "refresh_token"),
        ("Invitation", "5", "token_hash"),
        ("RefreshOutcome", "private-id", "session"),
        ("UserAccessToken", "private-id", "token"),
        ("RefreshToken", "private-id", "token"),
        ("ApiToken", "9", "token_hash"),
    ]
    with engine.begin() as conn:
        for i, (entity, identity, field) in enumerate(cases):
            conn.execute(
                audit.insert().values(
                    id=str(i),
                    entity_type=entity,
                    entity_id=identity,
                    changes=[
                        {"field": field, "old": "old-private", "new": "private"},
                        {"field": "label", "new": "visible"},
                    ],
                )
            )
        conn.execute(
            audit.insert().values(
                id="ordinary",
                entity_type="User",
                entity_id="10",
                changes=[{"field": "email", "new": "visible"}],
            )
        )
        conn.execute(
            audit.insert(),
            [
                {
                    "id": f"batch-{i:04}",
                    "entity_type": "Setting",
                    "entity_id": str(i),
                    "changes": [{"field": "value", "new": "private"}],
                }
                for i in range(501)
            ],
        )
        conn.execute(
            audit.insert().values(
                id="legacy",
                entity_type="User",
                entity_id="11",
                changes={"hashed_password": {"old": "private"}, "label": "visible"},
            )
        )
        conn.execute(
            audit.insert().values(
                id="sparse",
                entity_type="User",
                entity_id="12",
                changes=[{"field": "hashed_password"}, "note"],
            )
        )
        conn.execute(
            audit.insert().values(id="empty", entity_type="User", entity_id="13", changes=None)
        )
        with Operations.context(MigrationContext.configure(conn)):
            revision.upgrade()
            revision.upgrade()  # idempotent data rewrite
            revision.downgrade()
        rows = conn.execute(sa.select(audit).order_by(audit.c.id)).mappings().all()
        assert len(rows) == len(cases) + 505
        for row in rows:
            if row["id"].startswith("batch-"):
                assert row["changes"] == [{"field": "value", "new": "[redacted]"}]
                continue
            if row["id"] == "legacy":
                assert row["changes"] == {"hashed_password": "[redacted]", "label": "visible"}
                continue
            if row["id"] == "sparse":
                assert row["changes"] == [{"field": "hashed_password"}, "note"]
                continue
            if row["id"] == "empty":
                assert row["changes"] is None
                continue
            if row["id"] == "ordinary":
                assert row["changes"] == [{"field": "email", "new": "visible"}]
                continue
            assert row["changes"][0]["old"] == "[redacted]"
            assert row["changes"][0]["new"] == "[redacted]"
            assert row["changes"][1] == {"field": "label", "new": "visible"}
            if row["entity_type"] in {"UserAccessToken", "RefreshToken", "RefreshOutcome"}:
                assert row["entity_id"] == "[redacted]"
    engine.dispose()
