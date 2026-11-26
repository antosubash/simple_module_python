"""Compile registry-declared user ownership into a database filter."""

import uuid
from contextlib import suppress
from typing import Any

from pydantic import TypeAdapter
from simple_module_core.access.user_directory import UserDirectory
from simple_module_core.web.audit_links import AuditLinkRegistry
from simple_module_db.models.mixins import MultiTenantMixin
from sqlalchemy import (
    JSON,
    String,
    and_,
    case,
    cast,
    column,
    false,
    func,
    inspect,
    literal,
    or_,
    select,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import aliased
from sqlmodel import col

from audit_log.models import AuditEntry


def target_user_filter(
    registry: AuditLinkRegistry, directory: UserDirectory, term: str, dialect: str
) -> Any | None:
    """Match the user itself and linked entities, including deleted ones.

    Ownership recorded on creation survives a later deletion's empty diff.
    Live lookups also cover rows that predate audit capture. No owner is guessed
    from an arbitrary ``user_id`` column: the owning module declares it.
    """
    term = term.strip()
    if not term:
        return None
    with suppress(ValueError):
        term = str(uuid.UUID(term))
    matches: list[Any] = []
    if directory.entity_type:
        matches.append(
            and_(
                col(AuditEntry.entity_type) == directory.entity_type,
                col(AuditEntry.entity_id) == term,
            )
        )
    for link in registry.all_links.values():
        if not link.user_id_field or link.model is None:
            continue
        mapper = inspect(link.model)
        owner = mapper.columns[link.user_id_field]
        try:
            user_id = TypeAdapter(
                link.model.model_fields[link.user_id_field].annotation
            ).validate_python(term)
        except (ValueError, TypeError):
            continue
        ownership: list[Any] = []
        if any(pk is owner for pk in mapper.primary_key):
            # Audit capture formats composite keys with repr(), including UUID().
            if len(mapper.primary_key) == 1:
                ownership.append(col(AuditEntry.entity_id) == str(user_id))
            else:
                escaped = (
                    repr(user_id).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
                )
                pattern = (
                    "("
                    + ", ".join(escaped if pk is owner else "%" for pk in mapper.primary_key)
                    + ")"
                )
                ownership.append(AuditEntry.entity_id.like(pattern, escape="\\"))
        elif len(mapper.primary_key) == 1:
            pk = mapper.primary_key[0]
            # SQLite GUID columns cast to hex; audit ids are hyphenated strings.
            stored_id = cast(pk, String)
            audit_id = AuditEntry.entity_id
            if link.model.model_fields[pk.key].annotation is uuid.UUID:
                stored_id = func.replace(stored_id, "-", "")
                audit_id = func.replace(audit_id, "-", "")
            live = (
                select(link.model)
                .where(
                    owner == user_id,
                    stored_id == audit_id,
                )
                .correlate(AuditEntry)
            )
            ownership.append(live.exists())

        history = aliased(AuditEntry)
        if dialect == "postgresql":
            data = cast(history.changes, JSONB)
            array = case((func.jsonb_typeof(data) == "array", data), else_=literal([], type_=JSONB))
            changes = func.jsonb_array_elements(array).table_valued(column("value", JSONB))
        else:
            array = case((func.json_type(history.changes) == "array", history.changes), else_="[]")
            changes = func.json_each(array).table_valued(column("value", JSON))
        value = changes.c.value
        recorded_owner = (
            select(1)
            .select_from(changes)
            .where(
                value["field"].as_string() == link.user_id_field,
                or_(
                    value["new"].as_string() == str(user_id),
                    value["old"].as_string() == str(user_id),
                ),
            )
            .correlate(history)
            .exists()
        )
        recorded = (
            select(1)
            .select_from(history)
            .where(
                col(history.entity_type) == link.entity_type,
                col(history.entity_id) == AuditEntry.entity_id,
                recorded_owner,
            )
        )
        if issubclass(link.model, MultiTenantMixin):
            recorded = recorded.where(history.tenant_id.is_not_distinct_from(AuditEntry.tenant_id))
        ownership.append(recorded.correlate(AuditEntry).exists())
        matches.append(and_(col(AuditEntry.entity_type) == link.entity_type, or_(*ownership)))
    return or_(*matches) if matches else false()
