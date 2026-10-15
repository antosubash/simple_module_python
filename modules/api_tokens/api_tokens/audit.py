"""How an api_tokens row is named, and reached, from the audit log.

Create and revoke are recorded by ``AuditMixin`` (the hash and
``last_used_at`` are excluded on the model). A token is named by its own
name and display prefix — never by anything secret.
"""

from __future__ import annotations

import uuid

from simple_module_core.audit_links import AuditLink
from simple_module_db import ALL_TENANTS_OPTION
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api_tokens.constants import ADMIN_URL, AUDIT_LINK_LABEL, AUDIT_LINK_LABEL_KEY, QP_TOKEN
from api_tokens.models import ApiToken


async def resolve_token_labels(db: AsyncSession, ids: list[str]) -> dict[str, str]:
    """Map token id -> ``name (prefix…)`` for every id that still resolves.

    Read across tenants like the rest of the audit log: the audit screen is a
    platform view, and the label carries nothing the row itself does not.
    """
    parsed: dict[uuid.UUID, str] = {}
    for raw in ids:
        try:
            parsed[uuid.UUID(raw)] = raw
        except (ValueError, AttributeError, TypeError):
            continue
    if not parsed:
        return {}
    stmt = (
        select(ApiToken.id, ApiToken.name, ApiToken.prefix)
        .where(ApiToken.id.in_(list(parsed)))
        .execution_options(**{ALL_TENANTS_OPTION: True})
    )
    rows = (await db.execute(stmt)).all()
    return {parsed.get(tid, str(tid)): f"{name} ({prefix}…)" for tid, name, prefix in rows}


def build_token_audit_link() -> AuditLink:
    return AuditLink(
        entity_type=ApiToken.__name__,
        url_template=f"{ADMIN_URL}?{QP_TOKEN}={{id}}",
        label=AUDIT_LINK_LABEL,
        label_key=AUDIT_LINK_LABEL_KEY,
        table_name=ApiToken.__tablename__,
        label_resolver=resolve_token_labels,
    )
