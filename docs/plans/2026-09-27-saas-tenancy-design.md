# SaaS tenancy — design

Status: in progress (framework hardening + `tenants` module). Billing is
deliberately out of scope; this doc fixes the seams it will plug into.

## Decisions

| Question | Decision | Consequence |
|---|---|---|
| Isolation model | One schema, row-level `tenant_id` (`MultiTenantMixin`) | Works with per-module `MetaData` and host-owned Alembic history. No schema-per-tenant. |
| Users ↔ tenants | Many-to-many via `tenants_membership` | `users_user.tenant_id` and the `tenant_id` token claim are superseded; the *active* tenant is per session. |
| Missing tenant context | **Fail closed** when `multi_tenant` is on | Tenant-scoped SELECT/UPDATE/DELETE/INSERT without a tenant raises `TenantIsolationError`. Cross-tenant code opts out explicitly. |
| Billing | Not built. `tenants` exposes status, events and an entitlements seam | A `billing` module (smpy_modules) can be added without changing `tenants` or any consumer. |

## Framework changes (`simple_module_db`, `simple_module_hosting`)

1. **Strict isolation.** `DatabaseState.tenant_strict`, set from
   `Settings.multi_tenant`. With it on and no `current_tenant_id`, the query
   filter raises instead of leaving the statement unscoped. Opt-outs:
   `stmt.execution_options(all_tenants=True)` for one statement,
   `with all_tenants():` for a block. `with tenant_context(id):` runs code as a
   tenant outside a request (jobs, CLI, tests).
2. **Bulk UPDATE/DELETE are scoped.** Tenant criteria were attached to SELECT
   only, so `update(Model)` rewrote every tenant's rows.
3. **Tenant resolver seam.** `TenantMiddleware` consults
   `app.state.tenant_resolver` (`async (Request) -> str | None`) when a module
   registers one; its answer is final. Without one, the legacy claim path.
4. **Header hardening.** The `X-Tenant-ID` header is honoured for anonymous
   requests only on the legacy path. An authenticated user with no tenant
   could previously name any tenant with it.
5. **Background jobs carry their tenant.** Captured at enqueue, restored in the
   worker; `all_tenants()` for platform jobs.
6. **`SM024` doctor check.** A unique constraint on a `MultiTenantMixin`
   table that does not include `tenant_id` — two tenants could not both own
   the value.

## `tenants` module

- `tenants_tenant` — id, slug, name, `status` (`active` / `suspended`).
- `tenants_membership` — `(tenant_id, user_id)` unique, `role`
  (`owner` / `admin` / `member`). `user_id` is a string with no FK so external
  identity providers (keycloak) work.
- `tenants_invitation` — email, role, hashed token, expiry. Accepting while
  signed in as that email creates the membership. Delivery is an event, so
  the module does not depend on a mailer.
- **Resolver**: active tenant from the session, validated against a
  membership (per-process TTL cache, dropped through `InvalidationBus` on
  membership change); falls back to the user's first active membership. Suspended
  tenants resolve to nothing.
- **Effective roles**: the membership role is added to the request's
  principal as `tenant:<role>` for the active tenant only, and the module maps
  those roles onto its own permissions. A tenant `admin` is never the
  platform `admin`.
- **No-tenant handling**: `TenantIsolationError` raised during a request is
  turned into a redirect to `/tenants` (pages) or a 403 (API) — the user needs
  to pick or create an organisation, not see a 500.
- **Screens**: `/tenants` (my organisations, create, switch),
  `/tenants/members` (members, invitations), `/admin/tenants` (platform list,
  suspend/reactivate).

## Billing seams (what `billing` will use)

- **Entitlements.** `EntitlementProvider` protocol on
  `app.state.tenants.entitlements` — `limit(tenant_id, key) -> int | None`
  and `has_feature(tenant_id, key) -> bool`. The default provider is
  unlimited. `tenants` itself enforces the `tenants.seats` limit on new
  members and invitations, so the seam is exercised, not theoretical.
- **Lifecycle.** `TenantService.suspend/reactivate` — billing calls these on
  failed payment / recovery.
- **Events.** `TenantCreated`, `TenantStatusChanged`, `MembershipAdded`,
  `MembershipRemoved`, `InvitationCreated` — billing creates the customer on
  `TenantCreated` and syncs seat counts on membership changes.
- Billing owns its own tables (customer, subscription, webhook-event log)
  keyed by `tenant_id`. Nothing billing-specific goes on `tenants_tenant`.

## Module adoption (tracked as issues, not in this change)

Each module that stores per-customer data adopts `MultiTenantMixin`, widens
its unique constraints to include `tenant_id`, and adds cross-tenant tests.
Candidates: `file_storage`, `audit_log`, `background_tasks` (job rows),
`settings` (TENANT scope → real tenant ids), `feature_flags` (tenant overrides
UI), `branding` (per-tenant theme), and in smpy_modules `pagebuilder`, `news`,
`ai`, `canopy_atlas`. Public sites (pagebuilder) additionally need a
subdomain/domain resolver for anonymous requests.

## Non-goals

Schema-per-tenant, per-tenant databases, billing, tenant data export/delete
(GDPR) — the last is a follow-up once modules have adopted the mixin.
