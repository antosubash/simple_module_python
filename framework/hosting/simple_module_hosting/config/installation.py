"""Stable installation identity, independent of root-secret rotations (#986).

The existing system settings table owns ``host.installation_id``. It is internal
metadata, not an editable setting or an environment variable. Copies of a database
share its identity; separate installations should use separate databases.
"""

import asyncio
from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from simple_module_db.queries.stored_settings import INSTALLATION_ID_KEY

from simple_module_hosting.config._stored_identity import ensure_stored_identity


async def ensure_installation_id(database_url: str) -> str | None:
    """Read or provision the winning ID; return None only before migrations.

    Do not invent an ephemeral ID: replicas would silently stop hearing each
    other. Database errors propagate so callers can report degraded fan-out.
    """
    return await ensure_stored_identity(database_url, INSTALLATION_ID_KEY, lambda: uuid4().hex)


def load_installation_id(database_url: str) -> str | None:
    """Synchronous worker bootstrap, safe even when called from an event loop."""
    with ThreadPoolExecutor(max_workers=1) as pool:
        return pool.submit(lambda: asyncio.run(ensure_installation_id(database_url))).result()
