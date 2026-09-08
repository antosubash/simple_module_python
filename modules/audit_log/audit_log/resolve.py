"""Turn the raw ids in an audit entry into something a reader can act on.

An entry stores ``user_id`` and ``entity_id`` as bare primary keys. That is
correct for a permanent record — display names change, ids do not — but it
leaves the screen showing two uuids per row and no route to either record.

This module resolves both at render time:

* ``resolve_actors`` batches one query for every user id on the page.
* ``resolve_entity_labels`` asks each owning module what its rows are *called*,
  one batched call per entity type on the page.
* ``entity_link`` consults the host's :class:`AuditLinkRegistry`, which each
  module populates with the URL template and table name for its own tables.

None of it is stored. The audit row keeps the ids it recorded.
"""

from __future__ import annotations

import logging
import re
import uuid
from collections.abc import Callable, Collection, Iterable
from typing import Any

from simple_module_core.audit_links import AuditLinkRegistry
from simple_module_core.permissions import grants
from simple_module_db import LIKE_ESCAPE_CHAR, like_contains_pattern
from sqlalchemy import String, cast, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from users.audit import resolve_user_labels
from users.models import User

from audit_log.models import AuditEntry

logger = logging.getLogger(__name__)


async def resolve_actors(db: AsyncSession, user_ids: list[str | None]) -> dict[str, str]:
    """Map user id -> display label for every id on the page.

    One query for the whole page rather than one per row: an audit page is 50
    entries and the same handful of admins tend to appear on all of them.

    Delegates the naming rule itself to ``users.audit`` — the actor column and
    the entity column both point at user rows, and two copies of "full_name or
    email" is two chances for the same row to be called two things on one
    screen. Ids that no longer resolve (deleted accounts) or never named an
    account at all are simply absent from the result — the caller falls back to
    showing the raw id, which is still the truthful record of who acted.

    Deliberately **not** gated on ``users.manage`` the way the entity column is
    (``resolve_entity_labels``). The two columns disclose the same field and
    answer different questions: the entity column names people who were merely
    *edited*, which an auditor does not need in order to review the trail,
    while the actor column names the person who *acted*, which is the trail.
    ``audit_log.view`` therefore does imply "may see who acted"; that is stated
    in docs/modules/audit_log.md so it is granted knowingly. See GH #300.
    """
    wanted = sorted({uid for uid in user_ids if uid})
    if not wanted:
        return {}
    return await resolve_user_labels(db, wanted)


def actor_filter(term: str) -> Any | None:
    """A predicate selecting the audit rows an Actor search should show.

    A uuid means that account and only that account — an id is unambiguous, and
    putting it through a name search could only widen it. Anything else is a
    substring of a name or an email, which is what someone investigating an
    incident actually has to hand.

    The name case is a **subquery**, not a list of ids resolved in Python
    first. Materialising the matches means choosing a ceiling: without one, a
    common substring on a large install builds an ``IN`` list with more bind
    parameters than Postgres accepts; with one, the same search silently
    returns an arbitrary slice of the matching accounts, on the page *and* in
    the CSV, with nothing to say so. An audit log that quietly answers a
    different question than the one asked is worse than one that is slow, so
    the match stays in the database where it has no ceiling.

    ``None`` means the box was empty. It never means "nobody is called that" —
    that answer is a subquery matching no rows, which is not the same thing.

    ``user_id`` is text and ``User.id`` is a uuid, which is why the ids were
    materialised in the first place; ``CAST`` bridges it. Both dialects render
    the canonical lowercase, hyphenated form the audit trail stored (Postgres
    from its native ``uuid``, SQLite from the ``CHAR(36)`` the GUID type
    writes).

    Typed ``Any`` because SQLModel declares columns with their plain Python
    types, so a comparison reads statically as ``bool`` while being a SQL
    expression at runtime — the same reason ``EntryFilters.conditions`` does.
    """
    term = term.strip()
    if not term:
        return None
    try:
        return AuditEntry.user_id == str(uuid.UUID(term))
    except (ValueError, AttributeError, TypeError):
        pass

    pattern = like_contains_pattern(term)
    return AuditEntry.user_id.in_(
        select(cast(User.id, String)).where(
            or_(
                User.full_name.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
                User.email.ilike(pattern, escape=LIKE_ESCAPE_CHAR),
            )
        )
    )


async def resolve_entity_labels(
    db: AsyncSession,
    registry: AuditLinkRegistry,
    refs: Iterable[tuple[str, str]],
    permissions: Collection[str],
) -> dict[tuple[str, str], str]:
    """Map ``(entity_type, entity_id)`` -> display name for one page of rows.

    Grouped by entity type and dispatched to the owning module's resolver, so
    a page of 50 user edits costs one query and not fifty. Types whose owner
    registered no resolver — or none at all — are absent, and the caller shows
    the id.

    *permissions* is what the **requesting principal** holds, and a type whose
    owner set ``AuditLink.label_permission`` is skipped for a reader who lacks
    it. Naming a row is a second reading of that row: ``users`` names accounts
    by ``full_name or email``, so resolving unconditionally made
    ``audit_log.view`` a way to read the user directory that ``users.manage``
    is supposed to gate — including the email of every account still holding an
    unaccepted invite, where ``full_name`` is null. The entry itself is not
    withheld: the reader still gets the action, the type and the id, which is
    what an audit trail is for. See GH #300.

    Required rather than defaulted, because the safe value is the one the
    caller has to look up: a default of "everything" would silently reopen the
    hole at every new call site, and a default of "nothing" would silently
    blind an admin at the same ones.

    A resolver that raises is logged and skipped rather than allowed to fail
    the render: the audit log's job is to show what happened, and it can still
    do that with an id where a name would have been.
    """
    by_type: dict[str, set[str]] = {}
    for entity_type, entity_id in refs:
        if entity_id:
            by_type.setdefault(entity_type, set()).add(entity_id)

    labels: dict[tuple[str, str], str] = {}
    for entity_type, ids in by_type.items():
        link = registry.get(entity_type)
        if link is None or link.label_resolver is None:
            continue
        if not grants(permissions, link.label_permission):
            continue
        try:
            resolved = await link.label_resolver(db, sorted(ids))
        except Exception:
            logger.exception("Audit label resolver failed for %s", entity_type)
            # A failed statement leaves the session in an aborted transaction
            # on Postgres, where every later query answers "current transaction
            # is aborted" — which would take the rest of the page's names with
            # it, and truncate a streaming export mid-file. Reset so the rest of
            # the work still runs, with ids where names would have been.
            await db.rollback()
            continue
        for entity_id, label in resolved.items():
            if label:
                labels[(entity_type, entity_id)] = label
    return labels


_CAMEL_BOUNDARY = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def table_name_for(entity_type: str) -> str:
    """The muted tag beside a row's name, for a type nothing claims.

    ``UserAccessToken`` becomes ``user_access_token``. Not the real table
    (which carries its module's prefix) but the same vocabulary an operator
    uses at a psql prompt, where the class name is a Python identifier they
    would have to translate first. A module that registers an ``AuditLink``
    states its ``table_name`` outright and never reaches this.
    """
    return _CAMEL_BOUNDARY.sub("_", entity_type).lower()


USER_ENTITY_TYPE = User.__name__
"""The model an audit actor is a row of.

The audit trail records ``type(obj).__name__``, so registry keys are class
names — not ``__tablename__``. Actors are user ids, so their link comes from
the same registry entry as any other reference to that model.

Derived from the class rather than spelled ``"User"``: the users module keys
its own registration off ``User.__name__`` too, so a rename moves both ends
together instead of silently unlinking every actor cell."""


def actor_link(registry: AuditLinkRegistry, user_id: str) -> str | None:
    """URL for the acting user's record, or ``None`` when nothing claims it.

    Deliberately routed through the registry rather than hardcoding the users
    module's route: the users module already declares where its rows live, and
    duplicating that here would 404 the moment it moves its prefix, or silently
    disagree with the entity link rendered in the next column.

    ``None`` when nothing claims the users table — this module depends on
    ``users`` for its models, but not on ``users`` having registered a link.
    """
    link = registry.get(USER_ENTITY_TYPE)
    return link.url_for(user_id) if link else None


def entity_link(
    registry: AuditLinkRegistry,
    entity_type: str,
    entity_id: str,
    translate: Callable[[str], str] | None = None,
    display: str | None = None,
) -> dict[str, Any]:
    """Return ``{"url", "label", "display", "table_name"}`` for one reference.

    ``url`` is ``None`` when no module claims this table — the row still
    renders, just without a link, which is the correct outcome for tables that
    have no screen of their own (join rows, stored files).

    ``display`` is what the cell is titled with: the resolved row name where
    the owner could supply one, and otherwise the stored id, which is never
    wrong even when it is not friendly. ``table_name`` is the muted tag beside
    it; for a type nothing claims it is the class name snake-cased rather than
    left as ``UserAccessToken``, so every tag in the column reads as a table
    name and not one Python class among them.

    ``translate`` resolves the link's ``label_key``; an unresolved key (the
    Translator echoes it back) keeps the literal ``label``. ``label`` names the
    *kind* of row and stays on the payload for callers that summarise rather
    than tabulate.
    """
    link = registry.get(entity_type)
    shown = display or entity_id
    if link is None:
        return {
            "url": None,
            "label": entity_type,
            "display": shown,
            "table_name": table_name_for(entity_type),
        }
    label = link.label or entity_type
    if link.label_key and translate is not None:
        translated = translate(link.label_key)
        if translated != link.label_key:
            label = translated
    return {
        "url": link.url_for(entity_id),
        "label": label,
        "display": shown,
        "table_name": link.table_name or table_name_for(entity_type),
    }
