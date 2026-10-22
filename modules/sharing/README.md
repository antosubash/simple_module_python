# simple_module_sharing

A generic share table for
[simple_module](https://github.com/antosubash/simple_module_python) apps:
give one user `view` or `edit` access to one row of another module, with an
optional expiry, without that module shipping a bespoke share model. It plugs
into the framework's resource-scoped access (`ResourcePolicy`,
`OwnedResourcePolicy`, `RequiresResource`), so detail routes, lists and counts
all honour a share in SQL.

## Install

```bash
pip install simple_module_sharing
```

Add `simple_module_sharing` to your host's dependencies; the
`[project.entry-points.simple_module]` entry point is discovered automatically
at boot. Run `alembic upgrade heads` to create `sharing_resource_share`.

## Usage

Declare the resource type in the owning module and hand the policy a
`share_exists` factory:

```python
from sharing.policy import share_exists_for

NOTE_POLICY = OwnedResourcePolicy(
    Note.owner_id,
    bypass_perm=PERM_NOTES_MANAGE,
    share_exists=share_exists_for("notes.note", Note.id),
)


def register_resource_types(self, registry):
    registry.register(
        ResourceType(name="notes.note", policy=NOTE_POLICY, select_by_id=select_by_id(Note))
    )
```

| Route | Purpose | Permission |
|---|---|---|
| `POST /api/sharing/shares` | Grant or update a share | `sharing.share` + policy `can("share")` |
| `GET /api/sharing/shares?resource_type=&resource_id=` | Shares on one row | `sharing.share` + policy `can("share")` |
| `DELETE /api/sharing/shares/{id}` | Revoke (hard delete) | `sharing.share`; granter, grantee or `sharing.manage` |
| `GET /admin/sharing/` | Admin list of every share in the tenant | `sharing.view` |

Shares are tenant-scoped, expired shares never match, and grantees are
validated through the user directory. See `docs/modules/sharing.md`.

## License

MIT
