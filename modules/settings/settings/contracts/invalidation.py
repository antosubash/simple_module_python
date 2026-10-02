"""Per-(tenant, key) invalidation notices for settings writes (#382).

``settings`` keeps no cache of its own, but consumers resolving a value per
tenant do (branding's per-tenant theme). Every SYSTEM / TENANT write publishes
on :data:`INVALIDATION_CHANNEL` after commit, with the key built here:

* ``"<tenant_id>|<key>"`` — one tenant's override of ``key`` changed;
* ``"|<key>"`` — the system value changed, so every tenant's view of ``key``
  may have (tenants without an override inherit it).

``|`` cannot appear in a tenant id (``simple_module_db.TENANT_ID_PATTERN``), so
the first one always separates the two halves. Handlers may only forget.
"""

from __future__ import annotations

from settings.constants import INVALIDATION_CHANNEL

_SEP = "|"


def invalidation_key(tenant_id: str | None, key: str) -> str:
    """The wire key for a write of ``key`` at ``tenant_id`` (``None`` = system)."""
    return f"{tenant_id or ''}{_SEP}{key}"


def parse_invalidation_key(raw: str | None) -> tuple[str | None, str | None]:
    """``(tenant_id, key)``; ``tenant_id`` is ``None`` for a system write.

    ``(None, None)`` for a whole-channel clear (``raw is None``) or a key this
    module did not build — both mean "forget everything".
    """
    if raw is None or _SEP not in raw:
        return None, None
    tenant_id, _, key = raw.partition(_SEP)
    return (tenant_id or None), key


__all__ = ["INVALIDATION_CHANNEL", "invalidation_key", "parse_invalidation_key"]
