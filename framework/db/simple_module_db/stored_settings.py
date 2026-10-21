"""The ``settings_setting`` table and its read-only override queries.

Owned by the framework (#500) because the hosting layer reads this table on
every boot — host overrides before the app is built, the session-signing key,
and each registered module's settings in the lifespan — whether or not the
``settings`` plugin is enabled. The plugin keeps the write path and the admin
UI; ``settings.models.Setting`` is this same class, re-exported.

The table keeps ``create_module_base("settings")`` as its metadata owner, so
its name, columns and constraints are exactly what the migrations created.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Final

from pydantic_settings import BaseSettings
from simple_module_core.settings_hydrate import build_settings
from sqlalchemy import Select, UniqueConstraint, inspect, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.sql.expression import TableClause, column, table
from sqlmodel import Field

from simple_module_db.base import create_module_base
from simple_module_db.mixins import AuditMixin

# ── Table identity ───────────────────────────────────────────────────
SETTINGS_METADATA_NAME: Final = "settings"
TABLE_SETTING: Final = "settings_setting"
UQ_SCOPE_KEY: Final = "uq_settings_setting_scope_scope_id_key"
COL_SCOPE: Final = "scope"
COL_SCOPE_ID: Final = "scope_id"
COL_KEY: Final = "key"
COL_VALUE: Final = "value"
COL_VALUE_TYPE: Final = "value_type"

# ── Scopes ───────────────────────────────────────────────────────────
# Precedence high → low when resolving a key: USER > TENANT > SYSTEM.
SCOPE_SYSTEM: Final = "system"
SCOPE_TENANT: Final = "tenant"
SCOPE_USER: Final = "user"
# Empty string (not NULL) for SYSTEM so the composite unique key works the
# same on SQLite and PostgreSQL (NULL breaks uniqueness on PG).
SYSTEM_SCOPE_ID: Final = ""

# ── Value types ──────────────────────────────────────────────────────
# Values are always stored as strings; ``value_type`` says how to read them.
VALUE_TYPE_STRING: Final = "string"
VALUE_TYPE_BOOL: Final = "bool"
VALUE_TYPE_INT: Final = "int"
VALUE_TYPE_FLOAT: Final = "float"
VALUE_TYPE_JSON: Final = "json"
ALL_VALUE_TYPES: Final = (
    VALUE_TYPE_STRING,
    VALUE_TYPE_BOOL,
    VALUE_TYPE_INT,
    VALUE_TYPE_FLOAT,
    VALUE_TYPE_JSON,
)

# ── Field limits ─────────────────────────────────────────────────────
KEY_MAX_LENGTH: Final = 200
VALUE_MAX_LENGTH: Final = 4000
DESCRIPTION_MAX_LENGTH: Final = 2000
SCOPE_MAX_LENGTH: Final = 10
SCOPE_ID_MAX_LENGTH: Final = 255
VALUE_TYPE_MAX_LENGTH: Final = 10

Base = create_module_base(SETTINGS_METADATA_NAME)


class Setting(Base, AuditMixin, table=True):  # ty: ignore[unsupported-base]
    """A typed key/value configuration entry scoped to system, tenant, or user.

    Resolution precedence when a consumer asks for a key: USER > TENANT >
    SYSTEM. Uniqueness is enforced across the (scope, scope_id, key) tuple
    so the same key can live at different scopes without collision.

    ``value`` is always stored as a string. ``value_type`` advertises how
    the bytes should be interpreted ("string", "bool", "int", "float",
    "json") so UIs pick the right input control and pydantic can reject
    inputs that don't parse.
    """

    __tablename__ = TABLE_SETTING
    __table_args__ = (UniqueConstraint(COL_SCOPE, COL_SCOPE_ID, COL_KEY, name=UQ_SCOPE_KEY),)

    id: int | None = Field(default=None, primary_key=True)
    scope: str = Field(default=SCOPE_SYSTEM, max_length=SCOPE_MAX_LENGTH, index=True)
    scope_id: str = Field(default=SYSTEM_SCOPE_ID, max_length=SCOPE_ID_MAX_LENGTH, index=True)
    key: str = Field(max_length=KEY_MAX_LENGTH, index=True)
    value: str = Field(max_length=VALUE_MAX_LENGTH)
    value_type: str = Field(default=VALUE_TYPE_STRING, max_length=VALUE_TYPE_MAX_LENGTH)
    description: str | None = Field(default=None, max_length=DESCRIPTION_MAX_LENGTH)


def settings_table_clause() -> TableClause:
    """A bare ``settings_setting`` clause for code that runs before any ORM setup.

    The pre-app host read and the secret-key bootstrap use their own
    short-lived engines; a lightweight clause keeps their SQL to exactly the
    columns they touch, with the names taken from the constants above.
    """
    return table(
        TABLE_SETTING,
        column(COL_SCOPE),
        column(COL_SCOPE_ID),
        column(COL_KEY),
        column(COL_VALUE),
        column(COL_VALUE_TYPE),
    )


def package_overrides(
    rows: Iterable[tuple[str, str, str]], package: str
) -> dict[str, tuple[str, str]]:
    """Map ``(key, value, value_type)`` rows to ``{field_name: (raw, value_type)}``.

    The one place the ``<package>.<field>`` key format is interpreted. Nested
    keys (``pkg.a.b``) belong to a sub-object, not a top-level field.
    """
    prefix = f"{package}."
    out: dict[str, tuple[str, str]] = {}
    for key, value, value_type in rows:
        if not key.startswith(prefix):
            continue
        field_name = key[len(prefix) :]
        if "." in field_name:
            continue
        out[field_name] = (value, value_type)
    return out


def _overrides_stmt(package: str) -> Select:
    return select(Setting.key, Setting.value, Setting.value_type).where(
        Setting.scope == SCOPE_SYSTEM,
        Setting.scope_id == SYSTEM_SCOPE_ID,
        Setting.key.startswith(f"{package}.", autoescape=True),
    )


def get_overrides_sync(session: Session, package: str) -> dict[str, tuple[str, str]]:
    """SYSTEM-scope overrides for ``package`` through a plain sync ``Session``.

    Unmasked: this feeds live settings objects, not a screen.
    """
    return package_overrides(session.execute(_overrides_stmt(package)).tuples(), package)


async def get_overrides(session: AsyncSession, package: str) -> dict[str, tuple[str, str]]:
    """Async twin of :func:`get_overrides_sync`."""
    return package_overrides((await session.execute(_overrides_stmt(package))).tuples(), package)


async def settings_table_exists(session: AsyncSession) -> bool:
    """Whether the settings table has been created (false on a fresh install)."""
    conn = await session.connection()
    return await conn.run_sync(lambda sync: inspect(sync).has_table(TABLE_SETTING))


class SessionOverrideSource:
    """An ``OverrideSource`` reading straight from the settings table.

    What the hosting lifespan hydrates through, so boot-time hydration needs
    no plugin. The ``settings`` plugin's ``SettingsStore`` satisfies the same
    protocol for its own reload path.
    """

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_overrides(self, package: str) -> dict[str, tuple[str, str]]:
        return await get_overrides(self._session, package)


def hydrate_settings_sync[T: BaseSettings](
    cls: type[T], session: Session, package: str, *, lenient: bool = False
) -> T:
    """Sync ``hydrate_settings`` for Celery workers and other non-async code.

    Workers never run the hosting lifespan, so a bare ``cls()`` there returns
    pydantic defaults (``DbBackedSettings`` ignores the environment on purpose).
    Takes a plain sync ``Session`` and applies the same SYSTEM-scope overrides
    with the same ``value_type`` parsing as the web process.
    """
    return build_settings(cls, get_overrides_sync(session, package), lenient=lenient)
