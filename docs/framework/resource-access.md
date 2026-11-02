# Resource-scoped access

Permissions are global `<module>.<verb>` strings: they say a principal may edit
*notes*, not *this* note. Resource-scoped access answers the object-level
question ("this user may see this note because they own it, it was shared with
them, or it is public") once per resource type, so detail and list endpoints
enforce the same rule and give the same 404/403 answers (GH #526).

## The pieces

| Piece | Package | Role |
|---|---|---|
| `ResourcePolicy` | `simple_module_core.resources` | Protocol: `filter(principal, action, stmt)` and `can(principal, action, obj)` |
| `ResourcePrincipal` | `simple_module_core.resources` | `user_id` + the request's resolved permission set |
| `ResourceType`, `ResourceTypeRegistry` | `simple_module_core.resources` | What `register_resource_types` declares; read at `app.state.sm.resource_types` |
| `OwnedResourcePolicy`, `select_by_id`, `load_authorized` | `simple_module_db.resource_policy` | The stock owner / public / shared policy |
| `RequiresResource`, `resource_principal` | `simple_module_hosting.resource_deps` | FastAPI dependencies |
| `sharing` module (optional) | `modules/sharing` | A generic `sharing_resource_share` table, grant/revoke API, admin page |

Actions are plain strings; `ACTION_VIEW`, `ACTION_EDIT`, `ACTION_DELETE` and
`ACTION_SHARE` are provided. `view` is special: it decides 404 versus 403.

## `filter` is the authority, `can` is a fast path

`filter` narrows a `SELECT` to the rows the principal may act on. It is a
`WHERE` on your own statement, so `paginate()` counts exactly the rows it lists
and tenant / soft-delete filters still apply. `can` decides for one loaded row
from the facts the row carries (owner, visibility, bypass permission). It may
answer `False` where `filter` would admit the row, because a share lives in
another table. Callers that get `False` from `can` fall back to `filter`, never
the other way round.

## Declaring a policy

```python
from simple_module_core.resources import ResourceType
from simple_module_db.resource_policy import OwnedResourcePolicy, select_by_id

NOTE_POLICY = OwnedResourcePolicy(
    Note.owner_id,
    bypass_perm=PERM_NOTES_MANAGE,  # required: None means nobody bypasses
    visibility_col=Note.visibility,  # 'public' rows are viewable by anyone
    share_exists=share_exists_for(NOTE_TYPE, Note.id),  # optional, from `sharing`
)


class NotesModule(ModuleBase):
    def register_resource_types(self, registry):
        registry.register(
            ResourceType(name=NOTE_TYPE, policy=NOTE_POLICY, select_by_id=select_by_id(Note))
        )
```

The predicate is `owner_col == user_id OR visibility_col == 'public' (view only)
OR EXISTS(share granting the action)`. A principal holding `bypass_perm`, or the
admin wildcard when a bypass permission is set, sees every row. `bypass_perm` is
keyword-required so the escape hatch is always written down; pass `None` to say
nobody bypasses ownership, not even an admin.

`share_exists` is injected as a `(principal, action) -> EXISTS(...) | None`
factory. The framework never imports the `sharing` module (SM009). A module can
supply its own bespoke share table the same way. Custom share roles (for
example a `manager` role that may reshare) are declared per type with
`ResourceType.share_roles`; see [sharing](../modules/sharing.md).

## Detail endpoints: `RequiresResource`

```python
def note_stmt(note_id: uuid.UUID):
    return select(Note).where(Note.id == note_id)


@router.patch("/{note_id}")
async def edit(note: Note = Depends(RequiresResource(NOTE_POLICY, ACTION_EDIT, note_stmt))): ...
```

`loader` is an ordinary FastAPI dependency (it may take path and query
parameters) that returns the unfiltered `SELECT`. The row is loaded only through
`policy.filter`, never `session.get` on a raw id:

- not visible (`view`) → **404**, the same answer as a missing row, so ids
  cannot be probed;
- visible but the action is not allowed → **403** `PermissionDenied` with
  `permission == "resource:<action>"`.

**API tokens.** `RequiresResource` counts as a permission gate for the
[token guard](./permissions.md) only when you pass `permission=`. It then also
enforces that permission, capped at the token's scopes, before loading. Without
`permission=`, an API token is refused on the route like on any route that
names no permission. The policy still applies to tokens on top of the
permission.

## List endpoints

```python
@router.get("/")
async def list_notes(
    who: ResourcePrincipal = Depends(resource_principal),
    db=Depends(get_db),
    params: PageParams = Depends(page_params),
):
    stmt = NOTE_POLICY.filter(who, ACTION_VIEW, select(Note).order_by(Note.created_at))
    return await paginate(db, stmt, params)
```

A row the principal may not see never leaves the database, and the count
matches the list.

## The optional `sharing` module

Install `simple_module_sharing` for a generic share table instead of a bespoke
one. Shares are tenant-scoped, hard-deleted on revoke, and an expired share is
ignored in SQL. Granting checks that the resource type is registered, that the
granter passes the owning policy's `share` action, and that the grantee exists
in the [user directory](./user-directory.md). See
[the module page](../modules/sharing.md).
