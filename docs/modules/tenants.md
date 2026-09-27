# tenants

Organisations for [simple_module](https://github.com/antosubash/simple_module_python)
SaaS installs: tenants, many-to-many memberships with per-tenant roles,
email-bound invitations, and the tenant resolver that scopes every request.

## Install

```bash
pip install simple_module_tenants
```

Add `simple_module_tenants` to your host's dependencies, then turn on
`multi_tenant` (Settings screen, or `SM_MULTI_TENANT=true`) and restart.
Without `multi_tenant` the module manages organisations but requests are not
scoped to them.

## What it does

- **Resolution.** Registers `app.state.tenant_resolver`. The session stores
  the user's chosen tenant; every request re-validates it against a
  membership (cached per process, dropped across workers through
  `InvalidationBus`). Suspended tenants resolve to nothing.
- **Per-tenant roles.** A membership role (`owner`, `admin`, `member`) is added
  to the principal as `tenant:<role>` for the active tenant only, so tenant
  roles never reach platform permissions.
- **Fail-closed handling.** With `multi_tenant` on, a tenant-scoped query
  with no tenant raises `TenantIsolationError`; this module turns that into a
  redirect to `/tenants` (pages) or a `403 tenant_required` (API).

## Usage

| Route | Permission | Purpose |
|---|---|---|
| `GET /tenants/` | signed in | My organisations: switch, create |
| `GET /tenants/members` | `tenants.members.view` | Members and invitations of the active tenant |
| `GET /tenants/invitations/accept?token=` | signed in | Accept an invitation |
| `GET /admin/tenants/` | `tenants.platform.view` | Platform list of all tenants |
| `GET/POST /api/tenants/` | signed in | List mine / create |
| `POST /api/tenants/{id}/switch` | member of `{id}` | Change the active tenant |
| `/api/tenants/current/members[/{user_id}]` | `tenants.members.view` / `.manage` | List, change role, remove |
| `DELETE /api/tenants/current/membership` | member | Leave (not the last owner) |
| `/api/tenants/current/invitations[/{id}]` | `tenants.members.manage` | List, invite, revoke |
| `POST /api/tenants/invitations/accept` | signed in as the invited email | Join |
| `POST /api/tenants/admin/{id}/suspend` · `/reactivate` | `tenants.platform.manage` | Lifecycle |

Tenant-level routes act on the *active* tenant (`/current`), never on an id
from the URL.

## Configuration

DB-backed (Settings screen):

- `allow_self_service` (default on) — any signed-in user may create an
  organisation.
- `invitation_ttl_hours` (default 72).
- `public_base_url` (default empty) — origin invitation links are built on.
  Empty makes them root-relative: they are never built from the request's
  `Host` header, because the same link travels in `InvitationCreated` for a
  mailer to send.

Management routes need both the permission and an owner/admin role *in the
active tenant*: a platform-wide grant does not make a plain member of a tenant
its manager (`403 tenant_manager_required`).

## Billing seams

The module ships no billing, but a billing module needs nothing more from it:

- `app.state.tenants.entitlements` — replace the default `UnlimitedEntitlements`
  with an `EntitlementProvider` (`limit(tenant_id, key)`,
  `has_feature(tenant_id, key)`). The module enforces `tenants.seats` on new
  members and invitations; `EntitlementExceededError` maps to HTTP 402.
- `TenantService.set_status(tenant_id, TenantStatus.SUSPENDED | ACTIVE)` for
  dunning.
- Events, published after commit: `TenantCreated`, `TenantStatusChanged`,
  `MembershipAdded`, `MembershipRemoved`, `InvitationCreated` (also the hook a
  mailer uses to deliver the invitation link).

## Models

`tenants_tenant` (id = the value stored in every `tenant_id`, slug, name,
status), `tenants_membership` (unique `(tenant_id, user_id)`, role, email
snapshot), `tenants_invitation` (email, role, SHA-256 of the token, expiry).
None use `MultiTenantMixin`: they are the registry, and are scoped by hand in
`TenantService`.

See also [the design doc](https://github.com/antosubash/simple_module_python/blob/main/docs/plans/2026-09-27-saas-tenancy-design.md).
