"""Seed a load-test admin and mint a forged session cookie.

Runs migrations-independent (assumes ``make migrate`` already ran), creates
an idempotent admin user, then prints a shell-exportable env var carrying a
signed Starlette session cookie. Source the output before launching locust:

    eval "$(uv run python scripts/loadtest_seed.py)"

The cookie bypasses the real login flow so the load-test profile reflects
steady-state authenticated traffic — not login/bootstrap overhead, and not
the login rate limiter (which would trip under 100 concurrent users).
"""

from __future__ import annotations

import asyncio

from simple_module_db.session import init_db
from simple_module_hosting.settings import Settings
from simple_module_testing import forge_session_cookie
from users.bootstrap import create_admin

LOAD_EMAIL = "loadtest@example.com"
LOAD_PASSWORD = "loadtest-password-x!1"


async def _main() -> None:
    settings = Settings()
    db_state = init_db(settings.database_url)
    try:
        async with db_state.session_factory() as session:
            result = await create_admin(
                session,
                email=LOAD_EMAIL,
                password=LOAD_PASSWORD,
                full_name="Load Test",
            )
            user_id = str(result.user.id)
    finally:
        await db_state.engine.dispose()

    cookie = forge_session_cookie(settings.secret_key, {"user_id": user_id})
    # Shell-sourceable output — quote for safety; itsdangerous cookies can
    # contain dots and hyphens but no spaces.
    print(f"export SM_LOADTEST_COOKIE='{cookie}'")


if __name__ == "__main__":
    asyncio.run(_main())
