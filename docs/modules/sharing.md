# sharing

Optional generic share table for [resource-scoped access](/framework/resource-access).
A module whose rows are owned by a user can let the owner share one row with
another user (a declared role, optionally until a date) without shipping its
own share model. Nothing depends on it: the framework only sees the
`share_exists` factory a module passes to its `OwnedResourcePolicy`.

## ModuleMeta

| Field | Value |
|---|---|
| `name` | `Sharing` |
| `route_prefix` | `/api/sharing` |
| `view_prefix` | `/admin/sharing` |
| `depends_on` | — |

## Wiring a resource type

```python
from simple_module_core.resources import ResourceType
from simple_module_db.resource_policy import OwnedResourcePolicy, select_by_id
from sharing.core.policy import share_exists_for

NOTE_TYPE = "notes.note"
NOTE_POLICY = OwnedResourcePolicy(
    Note.owner_id,
    bypass_perm=PERM_NOTES_MANAGE,
    share_exists=share_exists_for(NOTE_TYPE, Note.id),
)


class NotesModule(ModuleBase):
    def register_resource_types(self, registry):
        registry.register(
            ResourceType(name=NOTE_TYPE, policy=NOTE_POLICY, select_by_id=select_by_id(Note))
        )
```

A module that uses `sharing.core.policy` must list `Sharing` in `depends_on`.

By default, `ROLE_IMPLIES` supplies two roles: `view` grants view; `edit` grants
view and edit. Set the keyword-only `ResourceType.share_roles` to a mapping of
role ids to tuples of implied actions. Pass **the same mapping** to
`share_exists_for(..., roles=...)` so grant validation and SQL access agree.
Removing a role from the mapping later revokes the access of every share
stored with that role (the rows stay, but no longer match):

```python
from simple_module_core.resources import ACTION_EDIT, ACTION_SHARE, ACTION_VIEW

NOTE_SHARE_ROLES = {
    "viewer": (ACTION_VIEW,),
    "contributor": (ACTION_VIEW, ACTION_EDIT),
    "manager": (ACTION_VIEW, ACTION_EDIT, ACTION_SHARE),
}
NOTE_POLICY = OwnedResourcePolicy(
    Note.owner_id,
    bypass_perm=PERM_NOTES_MANAGE,
    share_exists=share_exists_for(NOTE_TYPE, Note.id, roles=NOTE_SHARE_ROLES),
)
NOTE_RESOURCE = ResourceType(
    name=NOTE_TYPE,
    policy=NOTE_POLICY,
    select_by_id=select_by_id(Note),
    share_roles=NOTE_SHARE_ROLES,
)
```

Register `NOTE_RESOURCE` in `register_resource_types`. Every declared role must
include `ACTION_VIEW`; registration rejects a role without it. `None` uses the
default mapping; an empty mapping permits no share roles. Role ids must match `[a-z][a-z0-9_]{0,31}` (checked at registration) and are stored
and shown as-is on the admin page. `roles_granting(action, roles=...)` returns
the role ids implying that action; custom actions work the same way as built-ins.

The owner, a holder of the policy's bypass permission, or a grantee whose role
implies `ACTION_SHARE` may list, grant and revoke shares on that resource.
There is no role ranking: such a grantee may grant **any** declared role,
including another manager. The API still requires `sharing.share`. Expired
shares and shares from other tenants grant no access.

Use `ResourceType.share_roles` and pass the same mapping to the SQL factory.
For a view-only subset use `{"view": (ACTION_VIEW,)}`; edit implies view through
`{"edit": (ACTION_VIEW, ACTION_EDIT)}`. No database migration is needed.

## Routes

| Method | Path | Permission | Notes |
|---|---|---|---|
| `POST` | `/api/sharing/shares` | `sharing.share` | Grant or update. 422 for an unknown type, role or grantee, or a past `expires_at`; 404 when the granter cannot see the row; 403 when they can see it but may not share it. |
| `GET` | `/api/sharing/shares?resource_type=&resource_id=` | `sharing.share` | Every share on one row (expired included, flagged), for whoever may share it. |
| `GET` | `/api/sharing/candidates?resource_type=&resource_id=&q=` | `sharing.share` | Requires `ACTION_SHARE` on the resource. Active users only, excluding the owner and caller; tenant members only in multi-tenant mode. |
| `DELETE` | `/api/sharing/shares/{id}` | `sharing.share` | Hard delete. Allowed for whoever may share the row, the grantee (leaving the share), or `sharing.manage`. |
| `GET` | `/admin/sharing/` | `sharing.view` | Admin page: every share in the active tenant, paginated, with user labels. |
| `POST` | `/admin/sharing/{id}/revoke` | `sharing.manage` | Revoke from the admin page. |

`sharing.share` is mapped to the `user` role and every tenant role; the row's
policy still decides each request. API tokens need `sharing.share` in their
scopes.

## Shared dialog and hook

Consumers that depend on `Sharing` can import its frontend UI through the host's
module alias (#990):

```tsx
import { ShareDialog } from '@simple-module-py/sharing/ui';

<ShareDialog resourceType="notes.note" resourceId={note.id} />;
```

Render the trigger only when the caller may share the resource. Every list,
search, grant and revoke request is checked again on the server. The dialog
loads only when opened, searches after a 250 ms debounce, and uses the generated
typed API client (including shared CSRF handling). All built-in text is translated.

The default roles are `view` and `edit`. For a resource with custom
`share_roles`, pass `roles={[{ value: 'reviewer', label: t(keys.notes.reviewer) }]}`
with labels translated by the consumer. Pass only roles declared on that
resource type; the server remains the authority. An empty list disables grants.
Expired shares remain visible and can be renewed by adding the person again.

For a custom presentation, import `useShares` from the same UI entry point and
call `useShares(resourceType, resourceId, open)`. It exposes `shares`, `query`,
`setQuery`, `candidates`, `tooShort`, `loading`, `searching`, `pending`, `error`,
`grant(candidate, role)` and `revoke(share)`. Mutations update the list on success;
failures leave it unchanged and set a translated error. Duplicate mutations are
blocked while a request is pending. Close, Escape and outside dismissal are disabled
during mutations. If a custom consumer closes and reopens while a write is
pending, the hook refreshes after that write settles.

Candidate queries under three trimmed characters return an empty list without
searching the directory, after resource authorization. Searches are limited to
60 per minute and 500 per day per signed-in user, using the host's shared rate
limit store (Redis across workers, otherwise per process). At most 20 eligible
people are returned. Activity, owner/caller exclusions and tenant membership
are filtered inside directory search **before** the limit.

In multi-tenant mode, substring/name searches are restricted to members of the
caller's active tenant, even for directory administrators. In single-tenant
mode, substring/name searches require `sharing.directory_search`; ordinary
sharers must enter an exact email address (case insensitive). This permission
is registered but is not granted to ordinary user or tenant roles.

Every candidate email is masked, for example `a•••@example.com`. Labels that
fall back to an email, or contain an email, use the masked form too. No raw email
is returned by the candidates route.

Ownership comes from `OwnedResourcePolicy.owner_col`, or `owner_id` on rows using a custom policy. Missing membership information fails closed on a
multi-tenant host. Custom policies with a different ownership shape must expose
an `owner_col` with its mapped column key to exclude their owner.

`POST /api/sharing/shares` accepts only `subject_type: "user"` (also the default
when omitted). Unsupported subject types and inactive users return 422 (#991).

## Tenancy

On a multi-tenant app a grantee must be a member of the active tenant. A
non-member gets the same `422 Unknown user` as an id that names nobody, so the
API cannot be used to probe other tenants' accounts. User labels (subject and
granter) are only filled in for members of the active tenant; anyone else is
shown by raw id. Membership is read through
`simple_module_core.tenancy.tenant_member_ids`, which the `tenants` module
publishes as `app.state.tenant_members`. With no active tenant or no
membership store, nobody qualifies. Single-tenant apps have no such check.

## Model

`sharing_resource_share` (`ResourceShare`, `MultiTenantMixin` + `AuditMixin`):
`resource_type`, `resource_id` (canonical text: a UUID's 32-digit hex, an int's
decimal), `subject_type` (`user`), `subject_id`, `role`, `granted_by`,
`expires_at`. Unique on `(tenant_id, resource_type, resource_id, subject_type,
subject_id)`, so re-granting updates the role and expiry in place. Shares are
tenant-scoped: a share made in one tenant never applies in another. An expired
share stays in the table (and on the admin page) but never matches the policy;
the comparison is done in SQL against the current time. Revoking deletes the
row.

Audit entries link to `/admin/sharing/?share={id}` (`AuditLink.for_model`).

## Cleanup

Durable `UserDeleted` cleanup removes shares addressed to the deleted user
across tenants; durable `TenantDeleted` cleanup removes the deleted tenant's
shares. Neither detects deletion of an arbitrary shared resource.

Resource owners must call the public
`sharing.contracts.forget_resource(db, resource_type, resource_id)` when purging
a resource (#683). Pass one canonical text id (UUID hex, decimal integer, or the
resource's natural key), or an iterable of those ids for a batch. The function
deletes every matching share, including expired shares, under the caller's
bound tenant using the caller's transaction. Other tenants and resource types
are unaffected. Repeated calls and empty batches are safe.

```python
from sharing.contracts import forget_resource

with tenant_context(tenant_id):
    await forget_resource(db, NOTE_TYPE, note.id.hex)
    await db.delete(note)
    await db.flush()
```

This is a trusted cleanup API for the owning module: it performs no authorization
or resource-existence check and does not commit. Bind the resource's tenant;
strict tenancy fails closed without one. Declare `Sharing` in `depends_on` when
using this contract. Clean up in the same transaction as the purge so a rollback
restores both the resource and its shares. Existing orphan rows are not swept
automatically.

## Migration

`f733c7938fd1` creates the table. It is its own root and head
(`branch_labels = ("sharing",)`), so `alembic downgrade sharing@base` drops
only this table.

## Publishing

`simple_module_sharing` is a new PyPI name: register a pending publisher for it
before the first release that includes it, or that release leg fails with 403.
