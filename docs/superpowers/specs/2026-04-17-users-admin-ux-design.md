# Users Module — Admin UX (Sub-project 2 of 4)

**Date:** 2026-04-17
**Status:** Design draft.
**Scope:** Make the admin list and detail pages useful for managing many users.

Second of four sub-projects. Sub-project 1 (quality pass) has shipped; this builds on a clean `UserService` / `api_admin.py` split. Sub-projects 3 (self-service) and 4 (security) come after.

## Goal

Extend admin pages with filtering, sorting, confirmation prompts for destructive actions, and a richer detail page. Keep public-contract changes additive: existing requests continue to return the same shapes.

When this ships:

- Admins can filter the list by status (active/disabled), role, and verified state, and sort by email, last-login, or created date.
- Destructive single-user actions (disable, reset-password link) show confirmation dialogs before firing.
- The detail page shows who/when (`created_at`, `last_login_at`, `disabled_at`) and supports marking a user verified.

## Non-goals

- **No bulk actions.** Explicitly dropped during scoping — selection UI, bulk endpoints, partial-success reporting are all deferred.
- No activity log / audit trail (requires event persistence — future).
- No session management (sub-project 4).
- No user impersonation, CSV export, or advanced search operators.

## Scope (3 slices)

### 1. List filtering + sorting

**New query params** on `GET /users/admin` (Inertia view) and `GET /api/users/admin` (JSON):

| Param | Type | Default | Meaning |
|---|---|---|---|
| `status` | `active` \| `disabled` \| `all` | `all` | filter on `is_active` |
| `role` | string (role name) | none | include only users who have this role |
| `verified` | `yes` \| `no` \| `all` | `all` | filter on `is_verified` |
| `sort` | `email` \| `last_login_at` \| `created_at` | `email` | sort column |
| `order` | `asc` \| `desc` | `asc` | direction |

`q` (search), `page`, `per_page` stay as-is. Unknown values for the enum params fall back to the default (no 422 — matches existing behavior where `q=""` is fine).

**Service change:** `UserService.list_users` grows keyword args `status`, `role_name`, `verified`, `sort`, `order`. Implementation uses SQL predicates, not post-filtering (scales with pagination). Sorting by `last_login_at` nulls-last regardless of direction (an admin sorting by recency doesn't want never-logged-in users on top when they pick "desc").

**UI (`pages/Users/Index.tsx`):**
- Status filter: segmented control (All / Active / Disabled).
- Role filter: select dropdown populated from the existing `roles` prop.
- Verified filter: segmented control (All / Verified / Unverified).
- Sort: clickable table headers on Email, Last login. (Created date is a new column, also sortable.)
- All filter + sort state is URL-synced (same pattern as `q`): pushing to `router.get('/users/admin', ...)` with `preserveState`.

**`UserListItem` gets `created_at: datetime`** sourced from `AuditMixin.created_at`. That's additive — existing clients ignore extra fields.

### 2. Confirmation flows

Frontend-only. Use shadcn `AlertDialog` (already vendored under `packages/ui/src/components/ui/`).

**Confirm prompts for:**
- **Disable user** (single) — "Disable `<email>`? They won't be able to sign in until re-enabled."
- **Copy reset-password link** — "Generate a reset link for `<email>`? The link will be copied to your clipboard and is valid for a limited time."

**No confirmation for:**
- Enable user (non-destructive)
- Save roles (user explicitly clicked "Save roles" — that is the confirmation)
- Mark verified (non-destructive; see slice 3)

Confirmation dialog contents are static per action. No "are you sure?" checkbox — a single Confirm button is enough friction.

### 3. Expanded detail page

**`UserListItem`** already carries `is_active`, `is_verified`, `disabled_at`, `last_login_at`. Add `created_at`.

**`pages/Users/Edit.tsx` gains a "Metadata" card** rendered above the existing Status + Roles cards:

```
Metadata
  Created:       2026-03-12 14:22 UTC
  Last login:    2026-04-10 08:15 UTC    ← or "Never"
  Disabled at:   —                        ← or timestamp
  Verified:      ✅ yes                   ← or "No" + [Mark verified] button
```

**New endpoint:** `PATCH /api/users/admin/{user_id}/verify` — sets `is_verified=True`. Idempotent (verifying an already-verified user is a 200 no-op). Same `UserNotFoundError → 404` translation as the other admin endpoints. No event published (consistent with current enable/disable pattern — only UserDisabled is emitted).

**No "mark unverified" action** — that's a foot-gun with no clear use case; revisit if someone asks.

## Out of contract-change scope

- HTTP status codes and response shapes for existing endpoints are preserved.
- Inertia page names (`Users/Users/Index`, `Users/Users/Edit`) are preserved.
- Event publication is unchanged (still UserInvited / UserDisabled / RoleAssigned, same payloads, same timing).
- Email / mailer side-effects unchanged.
- No DB migration required (all needed columns exist; `created_at` comes from `AuditMixin`).

## Architecture notes

- Filter/sort logic lives in `UserService.list_users`. Endpoint handlers stay thin; they parse query params, hand them off, and shape the response.
- Unknown enum values coerced to default at the endpoint boundary (not inside service) so the service signature stays honest.
- New `verify` endpoint parallels `disable` / `enable` — thin handler, translates `UserNotFoundError` to `HTTPException(404)`.
- Frontend: the Index page's URL-sync pattern already exists for `q` + `page`. Extending to more params keeps a single source of truth (the URL). No local-only state for filters.

## Testing (TDD)

Same discipline as sub-project 1: red test first, minimal green, refactor only when green.

### New backend tests

1. **Service filter tests** (`test_service.py` or new `test_service_filters.py`):
   - `list_users(status="disabled")` returns only disabled users.
   - `list_users(role_name="admin")` returns only users with that role.
   - `list_users(verified="no")` returns only unverified.
   - `list_users(sort="last_login_at", order="desc")` orders correctly with NULLs last.
   - Filters compose: `status="active" + role_name="admin"` intersects.
2. **Endpoint filter tests** (`test_api_admin.py`):
   - `GET /api/users/admin?status=disabled` returns filtered list.
   - Unknown `status=foo` returns the full list (coerced to default, 200).
   - `GET /api/users/admin?sort=last_login_at&order=desc` returns sorted.
3. **View filter tests** (`test_views.py`):
   - `GET /users/admin?status=disabled` renders with filtered users + echoes params.
4. **Verify endpoint tests** (`test_api_admin.py`):
   - `PATCH /api/users/admin/{id}/verify` on unverified user → 200, user now verified.
   - Same on already-verified user → 200, idempotent.
   - Unknown UUID → 404.
5. **`UserListItem` serialization** (`test_schemas.py` if it exists, else colocate):
   - `created_at` present and ISO-formatted.

### New frontend tests

Frontend tests in this repo are thin (vitest). We'll:
- Snapshot the Edit page's Metadata section with fixture data.
- Test the Index filter-URL-sync: toggling a filter updates the query string.
- Skip E2E — the Playwright smoke set already covers the admin happy path.

### Regression guard

- `make test-py` on `modules/users/tests/` — all existing tests pass unchanged.
- `make lint` — 300-line cap, ruff, ty, biome, tsc.
- `make doctor` — no new diagnostics.

## Build sequence

Each step is independently shippable. `make test` and `make lint` green between.

1. **Schema + service filters (backend).**
   - 1a: Add `created_at` to `UserListItem` + `to_list_item`. Red test → green.
   - 1b: Extend `list_users` signature with `status`, `role_name`, `verified`, `sort`, `order`. Red tests → green.
2. **Filter endpoints.**
   - 2a: Add query params to `admin_list_users` (JSON). Red tests → green.
   - 2b: Add query params to `admin_index` view. Red test → green; props echo the new params.
3. **Verify endpoint.**
   - 3a: Red test `PATCH /admin/{id}/verify`.
   - 3b: Service method `UserService.mark_verified`. Endpoint wrapper. Green.
4. **Frontend filter UI.**
   - 4a: Add filter controls to `Index.tsx`; wire URL sync.
   - 4b: Add sortable column headers.
   - 4c: Render new Created column.
5. **Frontend confirmation dialogs.**
   - 5a: Wrap Disable action in `AlertDialog`.
   - 5b: Wrap Copy-reset-link action in `AlertDialog`.
6. **Frontend detail-page Metadata card.**
   - 6a: Render Metadata card with `created_at`, `last_login_at`, `disabled_at`, verified state.
   - 6b: Add [Mark verified] button wired to the new endpoint.

## Risks

- **Filter combinatorics.** Unlikely to hit performance issues at realistic admin-list sizes; if a tenant grows huge, paging + indexed predicates cover it. `lower(email)` already has a functional index; `last_login_at` is indexed. `is_active` / `is_verified` are low-cardinality booleans — fine as full scans within already-paginated queries.
- **URL-state complexity on the frontend.** Five query params + debounce on `q` can cause race conditions if a user types + clicks a filter quickly. Mitigation: debounce only search input; filters fire immediately. The existing `preserveState` pattern handles staleness.
- **`AlertDialog` import footprint.** Already vendored; no new dependency.

## Acceptance criteria

- All three slices implemented per spec.
- Full repo test suite green.
- `make lint` + `make doctor` clean.
- No public-contract *removal*: every existing query param, response field, and status code continues to work exactly as before.
- `UserListItem` gains `created_at`; no other schema changes.
- New `PATCH /admin/{id}/verify` endpoint exists, idempotent, 404s on unknown UUID.
- Disable + reset-link actions require confirmation on the admin detail page.
