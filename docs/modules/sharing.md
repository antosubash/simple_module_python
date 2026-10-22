# sharing

Optional generic share table for [resource-scoped access](/framework/resource-access).
A module whose rows are owned by a user can let the owner share one row with
another user (`view` or `edit`, optionally until a date) without shipping its
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
from sharing.policy import share_exists_for

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

A module that uses `sharing.policy` must list `Sharing` in `depends_on`.

Roles are actions: `view` grants view; `edit` grants view and edit. A type
limits what may be granted with `ResourceType.shareable_actions` (default
`("view", "edit")`). Only the owner, or a holder of the policy's bypass
permission, passes `can("share")` and may grant.

## Routes

| Method | Path | Permission | Notes |
|---|---|---|---|
| `POST` | `/api/sharing/shares` | `sharing.share` | Grant or update. 422 for an unknown type, role or grantee, or a past `expires_at`; 404 when the granter cannot see the row; 403 when they can see it but may not share it. |
| `GET` | `/api/sharing/shares?resource_type=&resource_id=` | `sharing.share` | Every share on one row (expired included, flagged), for whoever may share it. |
| `DELETE` | `/api/sharing/shares/{id}` | `sharing.share` | Hard delete. Allowed for whoever may share the row, the grantee (leaving the share), or `sharing.manage`. |
| `GET` | `/admin/sharing/` | `sharing.view` | Admin page: every share in the active tenant, paginated, with user labels. |
| `POST` | `/admin/sharing/{id}/revoke` | `sharing.manage` | Revoke from the admin page. |

`sharing.share` is mapped to the `user` role and every tenant role; the row's
policy still decides each request. API tokens need `sharing.share` in their
scopes.

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

## Migration

`f733c7938fd1` creates the table. It is its own root and head
(`branch_labels = ("sharing",)`), so `alembic downgrade sharing@base` drops
only this table.

## Publishing

`simple_module_sharing` is a new PyPI name: register a pending publisher for it
before the first release that includes it, or that release leg fails with 403.
