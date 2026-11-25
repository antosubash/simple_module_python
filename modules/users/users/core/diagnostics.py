"""Doctor checks for account email configuration."""

import asyncio

from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_core.settings.settings_hydrate import build_settings
from simple_module_core.settings.stored_settings import construct_leniently
from simple_module_db.engine.session import init_db
from simple_module_db.queries.stored_settings import get_overrides, settings_table_exists
from simple_module_db.schema.migration_state import database_exists
from simple_module_hosting.config._preapp_config import apply_host_overrides
from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.pipeline.public_urls import public_origin
from sqlalchemy.exc import SQLAlchemyError

from users.core.settings import UsersSettings


async def _stored_origins(
    database_url: str,
) -> tuple[dict[str, tuple[str, str]], dict[str, tuple[str, str]]]:
    if not database_exists(database_url):
        return {}, {}
    db = init_db(database_url, sqlite_wal=False)
    try:
        async with db.session_factory() as session:
            if await settings_table_exists(session):
                return await get_overrides(session, "host"), await get_overrides(session, "users")
            return {}, {}
    finally:
        await db.engine.dispose()


def account_email_diagnostics(database_url: str, module_name: str) -> list[Diagnostic]:
    try:
        host_rows, users_rows = asyncio.run(_stored_origins(database_url))
    except (SQLAlchemyError, OSError, ValueError):
        # The database checks report connectivity separately; the origin is unknown.
        return []
    # Lenient like boot: a stale stored row is dropped, not fatal to Doctor.
    host = construct_leniently(HostSettings, apply_host_overrides(host_rows))
    users = build_settings(UsersSettings, users_rows, lenient=True)
    if public_origin(host, users.base_url) or host.forwarded_host_allowlist:
        return []
    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM035",
            module_name=module_name,
            message="Account emails have no configured origin or request host allowlist.",
            suggestion=(
                "Set users.base_url or host.public_base_url, or configure "
                "host.forwarded_host_allowlist."
            ),
        )
    ]
