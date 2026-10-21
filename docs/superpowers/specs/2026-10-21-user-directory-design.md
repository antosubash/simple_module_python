# User directory protocol (#501)

Approved 2026-10-21.

## Problem

`audit_log`, `dashboard`, `file_storage`, `permissions`, `api_tokens` and `auth`
import `users.models` directly, so on a Keycloak install (where
`select_auth_provider` drops `Users`) they silently query empty or stale
`users_*` tables. `users` ↔ `audit_log` import each other (cycle).
`topological_sort` only warns on a missing `depends_on` target. No module has a
foreign key to `users_user`; the only thing that genuinely needs the users
schema is the `Role` table (permissions role pages, `/roles/{role_id}`).

## Design

### Core: `simple_module_core/user_directory.py`

```python
@dataclass(frozen=True)
class DirectoryUser:
    id: str
    email: str
    full_name: str | None = None
    is_active: bool = True
    roles: tuple[str, ...] | None = None  # None = provider doesn't know

    @property
    def label(self) -> str:  # the one naming rule
        return self.full_name or self.email


@dataclass(frozen=True)
class DirectoryStats:
    total: int | None
    active_since: int | None  # last login within the window
    created_this_month: int | None


class UserDirectory(Protocol):
    entity_type: str | None  # audit-link key ("User"); None = unlinked

    async def get_many(
        self, db, ids: Collection[str], *, with_roles: bool = False
    ) -> dict[str, DirectoryUser]: ...
    async def search(self, db, term: str | None, *, limit: int) -> list[DirectoryUser]: ...
    def match_ids(self, term: str) -> Any | None: ...  # SELECT of text ids, or None
    async def stats(self, db, *, active_window: timedelta) -> DirectoryStats: ...
```

- `get_many`: keyed by the caller's id strings; non-UUID or unknown ids are
  omitted, never raise; implementations chunk (≤500 ids per query).
- Registration: `set_user_directory(app, d)` / `get_user_directory(app)` on
  `app.state`. The active auth provider registers it in `register_settings`.
  No provider → `NullUserDirectory` (empty results, `None` stats, `match_ids`
  → `None`); callers fall back to raw ids.
- `db` typed `Any` (core has no SQLAlchemy dependency).

### Activity feed (breaks the users ↔ audit_log cycle)

Core `ActivityFeed` protocol: `async recent_for_actor(db, actor_id, *, limit,
permissions) -> list[ActivityItem]` (`at`, `action`, `entity_type`,
`entity_id`, `entity_label | None`); `set_activity_feed` / `get_activity_feed`
on `app.state`. `audit_log` registers it (reusing `AuditLogService` and
`resolve_entity_labels` with its permission gating unchanged, GH #300).
`users/admin/recent_activity.py` drops its lazy `audit_log` imports and module
name check; a missing feed returns `None` (keeps "no card" vs "no activity").

### Implementations

- `users/directory.py`; `users/audit.py`'s `resolve_user_labels` delegates to it.
- `keycloak`: over `KeycloakUserCache` (users who have signed in at least
  once); roles `None`; `created_this_month` `None`.

### Ports

- `audit_log`: `resolve_actors`, `actor_filter` (stays an unbounded subquery via
  `match_ids`; `None` → exact id match only), `USER_ENTITY_TYPE` from the
  directory; drop `depends_on=[Users]`.
- `dashboard`: tiles from `stats()`, a `None` tile is hidden; drop `Users` dep.
- `file_storage`: delete `resolve.py`'s copy, use the directory.
- `api_tokens`: owner existence/active and emails via `get_many`; PAT
  resolution via `get_many(with_roles=True)`. Personal tokens stay refused
  when roles are unknown (Keycloak). Keeps `depends_on=[Users]`.
- `permissions`: user side (`get_many(with_roles=True)`, `search`); role pages
  keep `Users` (import `users.contracts`, not `users.models`); `ADMIN_ROLE`
  from core instead of `users.constants`.
- `auth`: structural `Protocol` replaces the `users.User` type hint.
- `background_tasks`: drop the unused `depends_on=[Users]` (test that ordering
  doesn't matter).

### Strict discovery (last commit)

`topological_sort(modules, *, strict=False)` collects all missing pairs; strict
raises one `MissingDependencyError(InvalidModuleError)` naming each.
`app_builder` passes `strict=not is_development`; doctor reports a new SM
diagnostic; the outbox worker stays lenient.

## Not in scope

Role pages / personal API tokens for Keycloak (follow-up: key roles by name).
`framework/testing` importing `users.bootstrap`. No migrations.
