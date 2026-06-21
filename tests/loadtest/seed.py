"""Seed realistic bulk data (faker) into the load-test database.

Bulk-inserts many users (with role assignments) and audit entries so the
list/search/pagination endpoints are exercised against real data volumes —
single-row tables hide the N+1s, missing indexes and serialization costs that
matter under load.

This seeds *data only*. The authenticated load-test user (and its forged
session cookie) is created separately by ``scripts/loadtest_seed.py``, which is
run automatically by ``make loadtest-memray``.

Run from the repo root against a THROWAWAY database (never your dev DB):

    SM_DATABASE_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/smpy_loadtest \\
      uv run python tests/loadtest/seed.py [n_users] [n_audit] [--force]

Or via ``make loadtest-seed``. Defaults: 10000 users, 100000 audit entries.
Idempotent — skips if the marker user already exists; ``--force`` wipes prior
load-test rows and re-seeds.
"""

from __future__ import annotations

import asyncio
import os
import sys
import uuid
from datetime import UTC, datetime, timedelta

from audit_log.models import AuditEntry
from faker import Faker
from fastapi_users.password import PasswordHelper
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import create_async_engine
from users.models import Role, User, UserRole

USER_PASSWORD = "loadtest-password-123"
MARKER_EMAIL = "loadtest+0@example.com"
ROLE_NAMES = ("admin", "editor", "author", "viewer", "moderator", "support")
NOW = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)

fake = Faker()
Faker.seed(42)


def _audit_arg(idx: int, default: int) -> int:
    args = [a for a in sys.argv[1:] if a.isdigit()]
    return int(args[idx]) if len(args) > idx else default


async def main() -> None:
    db_url = os.environ.get("SM_DATABASE_URL")
    if not db_url:
        raise SystemExit("set SM_DATABASE_URL to your throwaway load-test database first")
    n_users = _audit_arg(0, 10_000)
    n_audit = _audit_arg(1, 100_000)
    force = "--force" in sys.argv

    pw_helper = PasswordHelper()
    user_pw = pw_helper.hash(USER_PASSWORD)
    engine = create_async_engine(db_url, pool_size=5, max_overflow=10)

    async with engine.begin() as conn:
        marker = (await conn.execute(select(User.id).where(User.email == MARKER_EMAIL))).first()
        if marker and not force:
            total = (await conn.execute(select(func.count()).select_from(User))).scalar()
            audit = (await conn.execute(select(func.count()).select_from(AuditEntry))).scalar()
            print(f"already seeded (users={total}, audit={audit}); pass --force to re-seed")
            await engine.dispose()
            return
        if force:
            await conn.execute(delete(UserRole))
            await conn.execute(delete(User).where(User.email.like("loadtest+%@example.com")))
            await conn.execute(delete(AuditEntry).where(AuditEntry.correlation_id == "seed"))

        have_roles = {r for (r,) in (await conn.execute(select(Role.name))).all()}
        new_roles = [
            {
                "id": uuid.uuid4(),
                "name": n,
                "description": f"{n} role",
                "created_at": NOW,
                "updated_at": None,
                "created_by": None,
                "updated_by": None,
            }
            for n in ROLE_NAMES
            if n not in have_roles
        ]
        if new_roles:
            await conn.execute(Role.__table__.insert(), new_roles)
        role_ids = [r for (r,) in (await conn.execute(select(Role.id))).all()]

        print(f"seeding {n_users} users ...")
        user_ids: list[uuid.UUID] = []
        batch: list[dict] = []
        for i in range(n_users):
            uid = uuid.uuid4()
            user_ids.append(uid)
            disabled = i % 17 == 0
            batch.append(
                {
                    "id": uid,
                    "email": f"loadtest+{i}@example.com",
                    "hashed_password": user_pw,
                    "is_active": not disabled,
                    "is_superuser": False,
                    "is_verified": i % 3 != 0,
                    "full_name": fake.name(),
                    "tenant_id": None,
                    "disabled_at": NOW if disabled else None,
                    "last_login_at": NOW - timedelta(days=i % 90) if i % 4 else None,
                    "created_at": NOW - timedelta(days=i % 365),
                    "updated_at": None,
                    "created_by": None,
                    "updated_by": None,
                }
            )
            if len(batch) >= 2000:
                await conn.execute(User.__table__.insert(), batch)
                batch.clear()
        if batch:
            await conn.execute(User.__table__.insert(), batch)

        ur_rows: list[dict] = []
        for idx, uid in enumerate(user_ids):
            if idx % 10 < 7:
                r1 = role_ids[idx % len(role_ids)]
                ur_rows.append(
                    {"user_id": uid, "role_id": r1, "assigned_at": NOW, "assigned_by": None}
                )
                r2 = role_ids[(idx + 1) % len(role_ids)]
                if idx % 5 == 0 and r2 != r1:
                    ur_rows.append(
                        {"user_id": uid, "role_id": r2, "assigned_at": NOW, "assigned_by": None}
                    )
        for j in range(0, len(ur_rows), 5000):
            await conn.execute(UserRole.__table__.insert(), ur_rows[j : j + 5000])
        print(f"user_roles: {len(ur_rows)} assignments")

        print(f"seeding {n_audit} audit entries ...")
        actions = ("create", "update", "delete")
        entities = ("User", "Role", "Setting", "FeatureFlag", "File", "AuditEntry")
        abatch: list[dict] = []
        for i in range(n_audit):
            abatch.append(
                {
                    "id": uuid.uuid4(),
                    "entity_type": entities[i % len(entities)],
                    "entity_id": str(user_ids[i % len(user_ids)]),
                    "action": actions[i % len(actions)],
                    "changes": [{"field": "name", "old": fake.word(), "new": fake.word()}],
                    "user_id": str(user_ids[i % len(user_ids)]),
                    "correlation_id": "seed",
                    "created_at": NOW - timedelta(minutes=i),
                }
            )
            if len(abatch) >= 5000:
                await conn.execute(AuditEntry.__table__.insert(), abatch)
                abatch.clear()
        if abatch:
            await conn.execute(AuditEntry.__table__.insert(), abatch)

        users_n = (await conn.execute(select(func.count()).select_from(User))).scalar()
        audit_n = (await conn.execute(select(func.count()).select_from(AuditEntry))).scalar()
        print(f"DONE — users={users_n}, audit={audit_n}")
    await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
