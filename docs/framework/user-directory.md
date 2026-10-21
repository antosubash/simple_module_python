# User directory and activity feed

Which module holds the user accounts depends on the auth provider: `users`
keeps them in `users_user`, `keycloak` keeps a cache of everyone who has signed
in. A module that only needs to *name* a user, look a few up, search them or
count them reads them through the **user directory**, a protocol in
`simple_module_core.user_directory`, and never imports `users.models`. That
keeps it working under either provider instead of silently querying an empty
table on a Keycloak install (GH #501).

## Reading users

```python
from simple_module_core.user_directory import get_user_directory

directory = get_user_directory(request.app)
found = await directory.get_many(db, ["3f0c…", "celery-worker"])  # {id: DirectoryUser}
```

| Member | Returns |
|---|---|
| `get_many(db, ids, *, with_roles=False)` | `{id: DirectoryUser}` keyed by **your** id strings. Ids that are not uuids or name nobody are absent, never an error. Implementations chunk (`GET_MANY_CHUNK`, 500 ids per query). |
| `search(db, term, *, limit)` | Users whose name or email contains `term`, ordered by email; everyone up to `limit` when `term` is empty. |
| `match_ids(term)` | An **unexecuted** `SELECT` of the matching text ids, for use as an unbounded subquery (the audit log's Actor filter). `None` when the provider cannot express it. |
| `stats(db, *, active_window)` | `DirectoryStats(total, active_since, created_this_month)`; a `None` field means "cannot say", not zero. |
| `entity_type` | The audit-link key user rows are recorded under (`"User"`), or `None` when they have no audited model to link to. |

`DirectoryUser` carries `id`, `email`, `full_name`, `is_active` (false for a
disabled account too) and `roles`: a tuple of role names when `with_roles=True`
and the provider knows them, otherwise `None`. **`None` means unknown, not "no
roles"**: Keycloak keeps roles in the IdP, so code that would act on them
(personal API tokens) must refuse rather than treat the user as role-less.

Name a user with `DirectoryUser.label` (the full name, else the email). It is
the one naming rule, so a row is never called two things on one screen.
`resolve_user_labels(directory, db, ids)` maps a page of ids to labels in one
call; `parse_user_ids` and `chunked` help an implementation key and bound its
queries. `get_many` is keyed by the caller's strings: `parse_user_ids` maps each
uuid to every spelling the caller passed (`ABC…`, `abc…`, unhyphenated), and an
implementation returns an entry under each one.

## Providers

The active auth provider installs its directory in `register_settings` with
`set_user_directory(app, directory)`:

| Provider | Directory | Knows |
|---|---|---|
| `users` | `users.directory.UsersDirectory` | every local account, roles via `users_user_role`, all three stats |
| `keycloak` | `keycloak.directory.KeycloakDirectory` | users who have signed in at least once (`keycloak_user_cache`); roles `None`; `created_this_month` `None`; `entity_type` `None` |
| none | `NullUserDirectory` | nobody; every stat `None`; `match_ids` `None` |

A new provider implements the four methods and `entity_type`, and registers
it. Ids must come back in the canonical hyphenated text form the rest of the
app stores (`str(uuid)`); `KeycloakDirectory` shows how to render that on
SQLite, where SQLAlchemy's `Uuid` is 32 bare hex characters.

## Who uses it

| Module | Reads |
|---|---|
| `audit_log` | actor names (`resolve_actors`), the Actor search (`actor_filter`, a subquery via `match_ids`, an exact id match without one) and actor links (keyed by `entity_type`) |
| `dashboard` | the user tiles from `stats()`; a `None` tile is hidden |
| `file_storage` | uploader names |
| `api_tokens` | owner checks and emails; personal-token resolution via `get_many(with_roles=True)` |
| `permissions` | the user side of the grants screens (`get_many(with_roles=True)`, `search`) |

`permissions` role pages still depend on `Users`: roles have no directory
protocol yet (the `Role` table is read from `users.contracts.roles`).
`api_tokens` lists `Users` in `optional_depends_on` only: a personal token
needs the owner's roles, so under Keycloak it is refused while service keys
keep working.

## Activity feed

The users edit page shows what an account did lately. That comes from the
audit log, but `users` and `audit_log` must not import each other (each is
optional to the other, and importing both ways was a cycle). So
`simple_module_core.activity_feed` defines an `ActivityFeed` protocol:

```python
from simple_module_core.activity_feed import get_activity_feed

feed = get_activity_feed(request.app)  # None: nothing records activity
items = await feed.recent_for_actor(db, user_id, limit=6, permissions=granted)
```

Each `ActivityItem` has `at`, `action`, `entity_type`, `entity_id`,
`entity_label` (or `None` when the owner cannot name the row, or the reader
lacks its `AuditLink.label_permission`) and the raw `changes`. `audit_log`
installs the feed in `register_settings`; `set_activity_feed(app, None)`
removes it. A missing feed renders no card, which is a different claim from
an empty one.
