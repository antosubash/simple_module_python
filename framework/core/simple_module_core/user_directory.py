"""The user directory: how modules read *about* users without owning them.

Which module holds the user records depends on the auth provider: ``users``
keeps them in its own tables, ``keycloak`` keeps a cache of everyone who has
signed in. Code that only needs to *name* a user, list a few, or count them
(the audit log, the dashboard, file storage, API tokens, permissions) asks
through this protocol instead of importing either module's models, so it keeps
working whichever provider is installed (GH #501).

The active auth provider registers its directory with
:func:`set_user_directory` in ``register_settings``. With none registered
:func:`get_user_directory` returns :class:`NullUserDirectory`, which knows
nobody: callers fall back to the raw id, which is still the truthful record.

The ``db`` arguments are typed ``Any`` because ``simple_module_core`` must not
depend on SQLAlchemy; in practice it is the request's ``AsyncSession``.
"""

from __future__ import annotations

import uuid
from collections.abc import Collection, Iterable, Iterator, Sequence
from dataclasses import dataclass
from datetime import timedelta
from typing import Any, Protocol, runtime_checkable

USER_DIRECTORY_STATE_ATTR = "user_directory"
"""``app.state`` attribute holding the active :class:`UserDirectory`."""

GET_MANY_CHUNK = 500
"""Most ids an implementation puts in one ``IN`` list.

A page of audit rows is far below it; an export or a bulk lookup is not, and
Postgres caps bind parameters per statement, so implementations chunk."""


@dataclass(frozen=True)
class DirectoryUser:
    """One user, as much as the directory knows about them."""

    id: str
    email: str
    full_name: str | None = None
    is_active: bool = True
    #: Role names, or ``None`` when the provider does not know them (Keycloak
    #: keeps roles in the IdP). Only filled when ``with_roles=True`` was asked.
    roles: tuple[str, ...] | None = None

    @property
    def label(self) -> str:
        """The one naming rule: the full name, else the email.

        An invited account has no name until it is accepted, so the email is
        what identifies it until then. Every screen that names a user uses
        this, so one row is never called two things on one page.
        """
        return self.full_name or self.email


@dataclass(frozen=True)
class DirectoryStats:
    """Headline counts. ``None`` means the provider cannot say, not zero."""

    total: int | None
    #: Users whose last sign-in falls inside the requested window.
    active_since: int | None
    created_this_month: int | None


@runtime_checkable
class UserDirectory(Protocol):
    #: The audit-link key user rows are recorded under (``"User"``), or
    #: ``None`` when the provider's users have no audited model to link to.
    entity_type: str | None

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        """Map each known id to its user.

        Keyed by the caller's own id strings. Ids that are not uuids, or name
        nobody, are absent from the result — never an error.
        """
        ...

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        """Users whose name or email contains *term* (all users when empty)."""
        ...

    def match_ids(self, term: str) -> Any | None:
        """A SQL ``SELECT`` of the text ids whose name or email contains *term*.

        Returned unexecuted so a caller can embed it as a subquery with no
        ceiling on how many ids match. ``None`` when the provider cannot express
        the match in SQL; the caller then matches the term as an id.
        """
        ...

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        """Headline counts for the dashboard."""
        ...


class NullUserDirectory:
    """The directory when no auth provider registered one: it knows nobody."""

    entity_type: str | None = None

    async def get_many(
        self, db: Any, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]:
        return {}

    async def search(self, db: Any, term: str | None, *, limit: int) -> list[DirectoryUser]:
        return []

    def match_ids(self, term: str) -> Any | None:
        return None

    async def stats(self, db: Any, *, active_window: timedelta) -> DirectoryStats:
        return DirectoryStats(total=None, active_since=None, created_this_month=None)


_NULL_DIRECTORY = NullUserDirectory()


def set_user_directory(app: Any, directory: UserDirectory) -> None:
    """Install *directory* as the app's user directory (the auth provider does)."""
    setattr(app.state, USER_DIRECTORY_STATE_ATTR, directory)


def get_user_directory(app: Any) -> UserDirectory:
    """The app's user directory, or a :class:`NullUserDirectory`."""
    directory = getattr(app.state, USER_DIRECTORY_STATE_ATTR, None)
    return directory if directory is not None else _NULL_DIRECTORY


def parse_user_ids(ids: Collection[str]) -> dict[uuid.UUID, list[str]]:
    """Map each id that parses as a uuid to every caller spelling of it.

    Implementations key their answer by the caller's strings, so an uppercase
    or unhyphenated id still finds its row, and two spellings of one id each
    get an entry. Anything else (a worker name, an ``svc:`` principal,
    ``None``) belongs to another id space and is dropped.
    """
    parsed: dict[uuid.UUID, list[str]] = {}
    for raw in ids:
        try:
            keys = parsed.setdefault(uuid.UUID(raw), [])
        except (ValueError, AttributeError, TypeError):
            continue
        if raw not in keys:
            keys.append(raw)
    return parsed


def chunked[T](items: Sequence[T], size: int = GET_MANY_CHUNK) -> Iterator[Sequence[T]]:
    """*items* in slices of at most *size*, for bounded ``IN`` lists."""
    for start in range(0, len(items), size):
        yield items[start : start + size]


async def resolve_user_labels(
    directory: UserDirectory, db: Any, ids: Iterable[str | None]
) -> dict[str, str]:
    """Map id -> :attr:`DirectoryUser.label` for every id the directory knows.

    Empty and ``None`` ids (a row with no recorded user) are skipped; ids the
    directory cannot name (or names with an empty label, e.g. a cached account
    with neither a name nor an email) are absent, and callers show the stored
    id instead.
    """
    wanted = {uid for uid in ids if uid}
    if not wanted:
        return {}
    found = await directory.get_many(db, wanted)
    return {uid: user.label for uid, user in found.items() if user.label}


__all__ = [
    "GET_MANY_CHUNK",
    "USER_DIRECTORY_STATE_ATTR",
    "DirectoryStats",
    "DirectoryUser",
    "NullUserDirectory",
    "UserDirectory",
    "chunked",
    "get_user_directory",
    "parse_user_ids",
    "resolve_user_labels",
    "set_user_directory",
]
