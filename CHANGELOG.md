# Changelog

All notable changes to this project are documented in this file. The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and this project adheres to [Semantic Versioning](https://semver.org/) post-1.0.

> **Coverage note.** Between 0.0.1 and 0.0.27 this file carried no per-version
> sections, and several already-released fixes sat under `[Unreleased]` long
> after shipping — which led a downstream app to conclude a fix it depended on
> was still unreleased (GH issue #253). Those entries have been moved to the
> release they actually shipped in, verified with `git tag --contains`.
> Versions not listed below still have no entry; consult the commit log.
>
> 0.0.28 through 0.0.37 were released before the release workflow cut this
> file (#572), so their changes are listed under `[0.0.38]` (#584).

## [Unreleased]

### Added
- Public durable delivery context (`in_delivery()` and `IN_DELIVERY`), inherited
  by handler child tasks and reset after delivery (#682).
- Transactional, tenant-scoped `sharing.contracts.forget_resource` for resource
  owners purging shared resources (#683).
- Public `simple_module_hosting.render_error_page` with standard JSON/Inertia
  negotiation, status and header preservation (#684).
- Public `background_tasks.sync_db.worker_tenancy` and `WorkerTenancy` snapshot,
  distinguishing an unconfigured worker from single-tenant operation (#685).

### Fixed
- Deprecate `auth.deps.require_permission` for removal in 0.1.0; recommend
  `RequiresPermission` and enforce the removal release in the shim ledger (#698).
- **Behaviour change:** gate Files and Branding navigation by their page
  permissions instead of hardcoded roles (#698).
- Clear deleted tenants' feature-flag registry overrides locally and on remote
  tenant-deletion invalidations, preserving other scopes (#639, #698).
- Keep unexpected bulk-invite exception details in logs and return a generic
  failure message instead of exposing SQL and parameters (#698).
- **Behaviour change:** align audit-log JSON list actor search and inclusive
  end-of-day filtering with the browse screen and CSV export (#698).
- Start database lease TTLs after locking each slot on Postgres, and recheck expiry after
  lock waits when refreshing or releasing (#698).
- File storage: cancellation during upload-session lookup prevents transport from
  starting; clearing completed upload rows releases their retained files (#695, #588).
- **Behaviour change:** password resets revoke all browser sessions, access tokens
  and refresh tokens, sharing revocation with password changes and sign-out-everywhere (#686).
- Defer single admin create/invite events and invitation-related emails until the
  request commits; failed commits deliver neither mail nor ordinary events (#692, #627).
- **Behaviour change:** permission managers may only add keys they hold and cannot
  edit stronger users; scoped admin tokens obey their permission ceiling. Both
  API and Inertia writes return a refusal reason (#687, following #624 and #653).
- Permission service user-grant writes now invalidate caches after commit for
  every caller, including cross-worker delivery with an app; deprecate the
  endpoint invalidation helper for removal in 0.1.0 (#687, #621).
- Docker: exclude `.env*` (except `.env.example`), private keys, credentials
  and secrets directories from reference and scaffold image build contexts (#688).
- **Behaviour change:** reference and scaffold images keep default filesystem
  uploads under `/app/data/uploads` on the persistent app volume, including
  Postgres scaffolds and their storage workers. Existing uploads must be copied
  into the volume before replacing old containers (#689).
- Load-test cookie seeding resolves the server's stored session-signing key
  through `merge_host_settings()`, preserving explicit environment overrides (#697).
- DB: stamp tenant destinations in INSERT ... SELECT without appending VALUES;
  validate explicit tenant literals and retain strict isolation and source scoping (#693).
- Inertia: honor custom once-prop keys in client exclusions, skipping loaders
  and values on full and partial requests (#694).
- **Behaviour change:** generic settings API and Browse mutations reject registered
  module keys and point to their validated editor; stop suggesting them (#690).
- Mark storage backend construction fields as requiring coordinated web/worker
  restart; document multipart draining and connection-check behaviour (#691).
- Show Revert immediately after saving a defaulted module field while preserving
  drafts and the saved confirmation (#696).

## [0.0.41] — 2026-10-25

### Fixed
- Users: show password policy reasons on the reset screen instead of suggesting
  that a valid link expired; allow retry with the same token (#667).
- Settings: size module field rows by the editor card width, stack controls in narrow
  cards, and wrap long field/ENV identifiers to prevent collapsed inputs and horizontal
  overflow with two sidebars (#669).
- Restore keyboard focus to the Search command palette's opener after dismissal, including Ctrl/Cmd+K toggles, without stealing focus after command navigation (#668).
- Raise shared muted sidebar text contrast above 4.5:1 on both the default and
  hover backgrounds in light and dark modes, preserving secondary text hierarchy (#670).

## [0.0.40] — 2026-10-24

### Fixed
- **Behaviour change:** evict expired site-lock attempt buckets, paginate personal/admin API token lists
  (default and maximum API page size 100, with `limit`/`offset`), preserve revoke-all
  across pages, and recover concurrent duplicate share grants without a 500 (#640).
- Share UTC timestamp helpers across sharing, tenants, background tasks, API tokens
  and users (#640).
- Background tasks: serialize eager outbox dispatches so chained deliveries do not
  overlap on shared in-memory SQLite connections or trip another handler's commit
  guard during tenant teardown (#655).
- Api tokens: durably purge a deleted user's personal tokens across all tenants
  on `UserDeleted`, preserving service keys and other users' tokens (#657).
- Users: cap refresh-token families at a DB-configurable 90 days, refusing refreshes
  and revoking/pruning aged families while preserving reuse evidence for live families (#656).
- Users admin actions show translated server refusal details instead of generic errors;
  unknown details retain the existing fallback (#653).
- Users: GET and PATCH `/api/users/me` now accept bearer access tokens from
  `/api/users/auth/token` alongside browser sessions (#658).
- Users: redirect refused OAuth/OIDC browser sign-ins to login with translated English
  and German messages; preserve JSON errors for API callers (#654).
- Users: publish deletion, disabling and new role assignments transactionally through
  the durable outbox (inline cleanup without background tasks). Deletion purges tenant
  memberships, shares to the user and direct permission grants; tenants left without
  an owner are suspended. Existing roles no longer emit `RoleAssigned` (#627).
  `UserDeleted` now lives in `simple_module_core.user_events` (still re-exported from
  `users.contracts.events`) so modules can subscribe without depending on `users`.
- Frontend: verification failures show a generic error unless the server reports a bad
  token or an already-verified account; file downloads bypass Inertia so signed-URL
  redirects work; closed mobile sidebars are inert and hidden from assistive technology,
  while desktop sidebars remain accessible (#638).
- Settings: reverting a field preserves other unsaved edits; connection-test results
  stay with their module, and unreadable or empty check responses report failure (#637).
  `@simple-module-py/ui`: `readBody` now rethrows a body-read failure instead of returning
  `null`; `apiFetch` reports it as a network failure (status 0).
- Release tooling converts Python prereleases to npm SemVer and publishes them
  with the `next` tag; metadata checks catch missing/stale npm matrix entries.
  Memray loadtests refuse occupied ports and stop only their own process group (#629).
- Release workflow serializes runs, rejects non-main or stale dispatches before
  publishing, tags the published release commit and merges concurrent main changes
  into it before atomically pushing main and the tag, failing safely on conflicts (#628).
- CLI: `smpy update` selects a tag accepted by every sibling's constraint;
  git sources preserve refs containing `/`, and Python prerelease tags sort before
  their final release (#636).
- Hosting: derive the production Inertia asset version from the Vite manifest hash so
  stale tabs reload after deployment; include CSS from statically imported chunks (#633).
- Hosting: unwind started modules and dispose the database engine after lifecycle failures;
  serialize setup-wizard migrations across workers, including fresh databases (#634).
- Database: discard `on_commit` callbacks registered inside a rolled-back savepoint,
  including released child savepoints, while preserving callbacks from surviving work (#631).
- Role-permission edits, module settings updates/clears and system/tenant feature-flag
  overrides now apply only after commit and reload across workers through the
  invalidation bus. Periodic reloads bound staleness when messages are missed (#621).
- Keycloak user-cache inserts and profile updates now commit in an independent transaction,
  preserving user IDs across logins and bearer requests. Concurrent first logins reuse the
  winning cache row; bearer requests throttle last-login writes to once per five minutes (#618).

### Added
- Weekly Dependabot updates for uv, npm and GitHub Actions (#629).
- `tenants.contracts.UsageMeter`: an implementation-free usage-metering protocol next to
  `EntitlementProvider` (`check`, `consume`, `record`, `refund`, `reserve`/`commit`/`release`,
  `summary`) with `UsageOutcome`/`UsageReservation`/`UsageSummaryRow`, `UsageExceededError`,
  an `UnlimitedUsageMeter` default on `app.state.tenants.usage` and `get_usage_meter(app)` (#616).
- `simple_module_hosting.csrf.rotate_csrf_token(request)` for principal changes that keep the
  session (#615).

### Security
- Remove account-status and superuser fields from the users `UserUpdate` contract;
  self-profile routes already used a narrower input schema (#640).
- Inertia: `Inertia.back()` and the exported validation handler now redirect only to a
  same-site path taken from `Referer`, falling back to `/`; an off-site or malformed
  `Referer` previously produced an open redirect (#635).
- Users: account administration never exceeds the actor's own authority. Outside a full
  admin session, a role can be granted and an account managed (edit, disable, reset link,
  invite) only when its effective permissions (roles plus direct grants) are within the
  actor's: a delegate holding `users.manage`, or an admin's scoped token, cannot grant
  `admin`, cannot reach admin/superuser accounts, and cannot grant a role mapped to
  permissions it lacks. Nobody can disable or demote themselves or the last active
  administrator (#624).
- Users: OAuth sign-in links to an existing account by email, or marks a new account
  verified, only with the provider's proof that the email is verified: OIDC
  `email_verified: true`, Google's People API `metadata.verified` on the primary email,
  a verified GitHub address from `/user/emails`; Microsoft (Entra) email claims are never
  proof. An unverified account (SSO-provisioned ones included, pending invites excepted)
  never absorbs a later OAuth login, closing an account pre-hijacking path (#622).
  **Behaviour change:** a provider without proof cannot sign in to an existing account by
  matching its email alone (`400 OAUTH_USER_ALREADY_EXISTS`); existing subject links still
  sign in.
- Tenants: accepting an invitation requires a verified email (#623). Verification is read
  fresh from the user directory (new `DirectoryUser.email_verified`; `None` when the
  provider doesn't track it, in which case Keycloak's `email_verified` token claim decides),
  so an account verified after signing in can accept without signing in again.
  **Behaviour change:** with `users.require_verification` off, self-registered accounts must
  verify their email (or be marked verified by an admin) before accepting an invitation.
- Users: store access and refresh bearer tokens as SHA-256 digests and prune spent
  credentials in bounded batches on login/refresh, retaining active-family
  reuse evidence (#626). **Behaviour change:** migration `a626b1c8d023` deletes
  existing access/refresh tokens; affected clients must log in once again. Logging out
  (`POST /users/logout`, `POST /api/users/auth/logout`) now deletes the presented access
  token server-side instead of only clearing the cookie.
- Users: atomically consume refresh tokens and revoke their refresh-token family on reuse
  (#625). Migration `a625f0b7c912` adds family tracking; existing tokens start separate families.
- DB: sessions bound to a SQLAlchemy `Connection` now inherit its engine's tenant
  policy and audit configuration, preserving strict tenant isolation and audit callbacks (#630).
- Keycloak JWKS fetches now use a per-cache lock and a 30-second minimum interval
  between attempts, including failures, preventing random-`kid` bearer tokens from
  triggering an outbound request each. Newly rotated keys may take up to 30 seconds
  to be accepted (#620).
- Keycloak sign-in clears prior identity state while preserving registered browser gates and
  the safe post-login redirect; validates the ID token, nonce and matching subject (#619).
  **Behaviour change:** browser sessions renew server-side via refresh token at access-token
  expiry, using validated claims for fresh roles. Demoted or disabled users lose access
  at the next access-token expiry; failed refreshes or expired sessions without a refresh
  token require sign-in. The ID token is no longer stored in the signed cookie to keep
  it below browser size limits; logout uses `client_id` instead of `id_token_hint`.
  Sessions created before this release carry no refresh token, so every Keycloak browser
  session signs in once after upgrading. Realms with "Revoke Refresh Token" enabled should
  allow a refresh-token reuse count of at least 1, or parallel requests at expiry can sign a
  user out.
- Sign-in now rotates the session: users' `on_after_login` (password, OAuth, accept-invite)
  clears it and keeps only the pending post-login redirect, so a CSRF token (or any other
  session state) issued before sign-in no longer survives it. Keycloak sign-in rotates the CSRF
  token (#615). **Behaviour change:** session keys a module stored
  before sign-in are dropped at sign-in.
  `simple_module_hosting.session.preserve_across_sign_in(app, key)` lets a module keep browser-bound
  gate state across it; site_lock uses it so the unlock marker survives sign-in.

## [0.0.39] — 2026-10-24

### Added
- `EventBus.publish_durable_or_inline(event, db)`: enqueue durably when a transport is
  installed, otherwise run the durable handlers inline in `db`'s transaction (#583).

### Changed
- Frontend: every page that posts through the Inertia router now shows a toast on failure (sharing revoke, dashboard Doctor rerun included); `useLeaveGuard` lives in `@simple-module-py/ui`, the background-tasks outbox confirms through the shared dialog instead of `window.confirm`, and `reportClientError()` is the single hook the error boundary reports through (#601).
- Users: lockout, registration and bulk-invite writes that must land before the request ends
  now commit through `simple_module_db.independent_session` (its own short-lived session)
  instead of committing the request session. Failed or unverified password logins now roll
  back the request session before the lockout bookkeeping is checkpointed. Lockout,
  invite and demo code moved into internal subpackages (#592).
- Users login lockout raises `LoginLockedError`, mapped to the same 429 body and `Retry-After`
  by a registered exception handler; settings errors now share a `SettingsError` base (their
  HTTP mapping is unchanged). The convention is in
  `docs/module-authoring.md` and the module scaffold (#595).
- Packaging: **Behaviour change.** Published packages now cap their third-party runtime
  dependencies (next major for 1.x+ libraries, next minor for 0.x ones such as `sqlmodel`), so
  an install can no longer resolve an untested major release (#600).
- `make migration` now requires `LABEL=<branch label>` and autogenerates against
  `<label>@head`, instead of failing with "Multiple heads" (#598).
- Release: a pre-flight job lists any package that is not yet on PyPI (needs a pending
  publisher) before anything is published, and publish legs skip versions that already exist,
  so a half-failed release can be re-run (#599).
- `make test-py` / `make test-py-pg` now default to 4 pytest-xdist workers instead of
  `-n auto`, so concurrent runs on many-core machines don't exhaust memory;
  `PYTEST_WORKERS=auto` restores the old behaviour.
- Hosting: one `simple_module_hosting.public_access.is_public(app, method, path)` answers
  "is this route public?" for `AuthMiddleware`, maintenance mode, rate limiting and the
  `SM031` check, so they can no longer disagree. A legacy auth provider whose deprecated
  `get_public_paths()` raises is now logged everywhere instead of silently treated as not
  public in route access (#593).
- Framework: fail-open error handlers in the setup gate, DB listeners, menu providers, plural
  rules and the invalidation decoder now log a WARNING (once) with the traceback instead of
  failing silently; outcomes are unchanged. The policy is in `docs/framework-conventions.md`.
  The test plugin resets the process-wide mail sender, lease backend and Sentry state per test. The
  `register_event_handlers(app=None)` default and the `requires_framework=None` bypass are
  tracked for removal in 0.1.0 (#594).

### Fixed
- DB audit: persistent rows deleted through the soft-delete listener now emit one
  `soft_deleted` record, including when business fields were edited before deletion (#632).
- Users: read-only demo mode now follows the resolved identity, not only the session cookie. Writes made with a bearer access token or personal API token of a demo account are refused (403 `DEMO_READ_ONLY`, or the Inertia 409 redirect) through the new `AuthState.principal_guards` hook, and demo accounts can no longer mint tokens via `POST /api/users/auth/token` or `/token/refresh` while `demo_read_only` is on (#611).
- Users: the default user role is created at startup when missing, so an app scaffolded with
  `smpy new` (schema baseline, no data migrations) can register users (#600).
- Tenants: deleting a tenant now tears down its data. `TenantDeleted` (now defined in
  `simple_module_core.tenant_events`, still importable from `tenants.contracts.events`) is
  published durably, and file_storage (files, upload sessions, then backend objects after
  commit), api_tokens, sharing, feature_flags and the framework's tenant-scoped settings
  overrides (including branding) purge that tenant's rows; audit history is kept. On multi-tenant
  installs, public files of a deleted tenant answer 404 at once (the existence check is cached
  60 s per worker and evicted on every worker by `TENANT_DELETED_CHANNEL`). Without `background_tasks` the handlers run inline in
  the deleting transaction. Rows orphaned by earlier deletions are not purged retroactively (#583).
- File storage: a file whose `backend` is not the active backend is no longer read or deleted
  through the wrong store: downloads, public reads and thumbnails answer 409 with a translated
  message, and a delete soft-deletes the row but leaves the object alone (logged). Switching
  backends still needs a manual migration; see `docs/modules/file_storage.md` (#589).
- Background tasks: `enqueue_after_commit` is documented as at-most-once (a broker outage after
  commit loses the task; use `publish_durable` for must-run work). file_storage gains an hourly
  `file_storage.reconcile_checksums` beat task that re-enqueues checksums for files left without
  one for 30 minutes, up to 500 per run (#590).

### Removed
- Frontend: `@simple-module-py/ui` no longer depends on `react-hook-form`/`@hookform/resolvers`, and the unused shadcn `form` component is removed; `host/client_app` drops the unused `zod` and `date-fns` (#601). **Behaviour change** for anyone importing `@simple-module-py/ui/components/ui/form`.

## [0.0.38] — 2026-10-23

### Fixed
- Users (security): disabling or enabling an account, or replacing its roles from the admin
  screens, now bumps `session_version` in the same transaction and evicts the cached counter on
  every worker after commit (an atomic SQL increment, so overlapping changes cannot lose one), so
  existing cookie sessions and bearer access tokens are refused on their next request; disabling
  also revokes the account's refresh tokens. Before, a disabled or demoted user kept the roles
  cached in their cookie until the session expired. **Behaviour change:** a role change signs that
  user out of their existing sessions; a remembered sign-in re-authenticates with the new roles
  (#581).
- File storage: **Behaviour change.** `quota_bytes` is now enforced for plain uploads as well as
  resumable ones (stored bytes plus active reservations, serialised per tenant on Postgres); an
  upload that would exceed it answers 413 and its object is removed. Previously only resumable
  sessions were checked, and the setting was described as report-only (#586).
- File storage: `DELETE /api/file_storage/files/{id}` and the bulk delete now drop the stored
  bytes only after the request transaction commits, so a failed commit no longer leaves a live
  row with no bytes. A new hourly `file_storage.reap_objects` beat task (needs
  `background_tasks`) retries objects of soft-deleted rows and removes objects left by uploads
  whose row never committed, after twice the upload-session TTL (#582).
- File storage: cancelling an upload still waiting for a free slot no longer uploads it later in
  the background (#588).
- Tenants: the organisation settings page and its menu item are registered only when the
  `settings` module is enabled; without it `/tenants/settings` used to 500 with an
  `ImportError`. `file_storage` now orders after `background_tasks` when both are installed (#585).
- Docker: **Behaviour change.** With `SM_USERS_BOOTSTRAP_PASSWORD` unset, the entrypoint now
  generates a random first-boot admin password and prints it (the compose file already said so),
  instead of seeding the public `changeme`. An explicit `changeme` is refused when
  `SM_ENVIRONMENT` is `production` (the image default). `docs/release.md`'s local rehearsal now
  runs in a disposable worktree instead of ending with `git reset --hard HEAD~1` (#587).
- Retained logs: a NUL character no longer drops the whole log batch on Postgres.
- Users: after a self-service password change the same browser kept its page session but
  every `/api/users/me*` call (including "Sign out everywhere") answered 401, because the
  change deleted the `sm_auth` access-token row that browser's cookie pointed at.
  `POST /api/users/me/password` now re-issues that cookie under the new `session_version`
  (keeping a remembered sign-in's window); other sessions and bearer tokens are still revoked.
  The profile's password and sessions cards show the translated failure inline.
- Users: the admin "Copy reset link" (and the bulk-invite fallback link) no longer points at
  `http://localhost:8000` on installs that never set `users.base_url`: an explicitly set
  `users.base_url` wins, then `HostSettings.public_base_url`, then the origin the admin is
  browsing. Emailed links are unchanged.
- UX polish (#575): `/tenants/settings` shows translated labels instead of raw keys
  (`SettingDefinition.label_key` / `TenantSettingView.label_key`, set by `branding`; en + de);
  signed-in error pages outside `/admin` (e.g. a 404 for an unknown URL) keep the app layout (sidebar, user menu); the tenant
  invite form shows a translated inline error for an invalid email instead of the browser's
  silent native validation.

### Removed
- Committed QA scratch directories `qa-shots/`, `.qa/` and `.verify/` (159 files); they are now gitignored (`dataset/` stays) (#511).
- Unused `Combobox` shadcn component and the `@base-ui/react` dependency (nothing imported it; Radix has no combobox, use `cmdk` `Command` + `Popover`). **Behaviour change** for anyone importing `@simple-module-py/ui/components/ui/combobox` (#521).
- `host/client_app` no longer re-declares `@simple-module-py/ui`'s runtime dependencies, nor `@base-ui/react`, `@radix-ui/react-slot`, `autoprefixer` or `postcss` (nothing loaded them) (#521).

### Added
- Typed API client (#504). `@simple-module-py/ui` ships `createApi<paths>()` (an
  `openapi-fetch` client with same-origin credentials, `Accept: application/json` and
  the CSRF header), `apiResult()` / `apiFetch()` normalising every call to
  `{ ok, status, data, detail, fieldErrors, error }` (network failure: `status: 0`),
  and `useApiErrorToast(fallbackKey)`. `smpy openapi gen-types [--module X]` writes
  each module's `pages/api.generated.ts` from its routes; `make gen-api-types`
  regenerates them and `make ci-api-types-fresh` (in `make lint` and CI) fails on a
  stale one. `*.generated.ts` is exempt from Biome and the 300-line cap. New modules
  ship `pages/api.ts`, the generated types and a Browse page that deletes through
  the client. `TranslationKey` is exported from `@simple-module-py/i18n`.
- `csrfToken` Inertia shared prop for signed-in sessions (#504), which the API client
  sends as `X-CSRF-Token` to the page's own origin. Anonymous pages never carry it.
- Resource-scoped access (#526): `simple_module_core.resources` (`ResourcePolicy` with `filter`/`can`, `ResourcePrincipal`, `ResourceType`, `ResourceTypeRegistry`) and a new `register_resource_types` hook (read at `app.state.sm.resource_types`); `simple_module_db.resource_policy.OwnedResourcePolicy` (owner OR public-for-view OR an injected `share_exists`, with a keyword-required bypass permission) so lists and `paginate()` counts are filtered in SQL; `simple_module_hosting.resource_deps.RequiresResource(policy, action, loader, permission=None)` loads rows only through the policy: invisible → 404, visible but not allowed → 403, and admits API tokens only when `permission=` is set. See `docs/framework/resource-access.md`.
- New optional `sharing` module (`simple_module_sharing`, #526): tenant-scoped `sharing_resource_share` table (migration `f733c7938fd1`, a new root and head labelled `sharing`), `share_exists_for(...)` for `OwnedResourcePolicy`, grant/revoke/list API under `/api/sharing/shares` (validates the resource type, the granter's `share` right on the row and the grantee via the user directory, which on a multi-tenant app must be a member of the active tenant: same error as an unknown id, and labels only for members; new core seam `simple_module_core.tenancy.tenant_member_ids` / `app.state.tenant_members`, published by `tenants`; expiry checked in SQL; revoke hard-deletes) and an admin page at `/admin/sharing/` (en + de). **Release note:** register a PyPI pending publisher for `simple_module_sharing` before the next release.
- Server-rendered `<head>` for Inertia pages (#535 step 1): `inertia.render(..., head=Head(title, description, canonical, robots, og, twitter, json_ld))` puts the tags in the first response so crawlers and link unfurlers see them without JS; they are also sent as the `_head` prop and re-emitted on client visits via Inertia's `serverHead` (`@simple-module-py/ui/lib/server-head`). URL fields are http(s)-only, JSON-LD cannot close its `<script>`. New `public_base_url` host setting (DB-backed, read per request, no restart) builds canonical / `og:url`; the request `Host` is never used. Both `index.html` templates updated. Body SSR remains open in #535.
- `smpy docker add-worker` generates dedicated Python worker images with validated apt packages, optional extras, queue/module routing, and idempotent Compose includes (#540).
- Statement DML is audited (#557): `simple_module_db.bulk_audit` audits ORM bulk
  `update()` / `delete()` / `insert()` and Core DML on `Model.__table__` through
  the engine's audit sink, one `bulk_updated` / `bulk_deleted` /
  `bulk_soft_deleted` / `bulk_restored` entry per row (ids prefetched with the statement's `WHERE`
  and tenant scope) up to 500 rows, else one `"*"` summary; `bulk_inserted` is one
  summary per statement. `execution_options(sm_audit=False)` opts out;
  `record_bulk_audit(session, Model, action, ids, changes)` records `text()`
  writes; the new `audit_log` setting `refuse_unaudited_dml` (default off) makes
  the opt-out raise `UnauditedWriteError`. No migration.
- Legacy SPA mounts (#541): `ModuleBase.spa_mounts()` returns `SpaMount(prefix, dist_dir, index="index.html", auth="required"|"public")` entries served with an `index.html` deep-link fallback (extension-less paths accepting HTML only; a missing asset stays a 404; hashed assets `immutable`; GET/HEAD only). `auth="public"` exempts GET/HEAD from `AuthMiddleware`. A prefix overlapping a router, static mount or another SPA fails boot (`SM032`). The Inertia client leaves these prefixes to the browser: `startSpaLinkInterception({ exclude })` plus the framework shared prop `nativePrefixes`, which also carries the new DB-backed host setting `native_link_prefixes` (no migration).
- `background_tasks`: opt-in retained logs. With `log_sink_enabled` (default off;
  `log_sink_level` default `INFO`, `log_retention_days` default 7) web and worker
  log lines are kept in the new `background_tasks_log_record` table, batched off
  the logging path by the new `simple_module_hosting.log_sinks` (`LogSink`
  protocol, `QueueSinkHandler`: bounded queue that drops and counts instead of
  blocking, secrets masked before queueing). The task detail page gains a Logs
  tab, `/admin/background-tasks/logs` searches all retained lines, and
  `purge_old_executions` enforces retention. Migration `1f5985daa10b` (#537).
- `background_tasks`: tasks report progress with `heartbeat(progress=(i, n), message=, phase=)`
  (buffered under the existing 30 s throttle, `i == n` writes at once, never
  audited), and `GET /api/background_tasks/tasks/{celery_task_id}/status` lets the user who
  enqueued a task read its status and progress without `background_tasks.view`
  (marked `Authenticated()`; tokens are refused)
  (owner in the active tenant, or `view` holders; anyone else gets 404; never
  returns args, result or traceback). `TaskExecution` gains `progress_*` and an
  indexed `owner_user_id` stamped from the new `sm_owner_id` message header;
  retries keep the original owner. The detail page shows a progress bar.
  Migration `bb906e1a1089` (first revision labelled `background_tasks`) (#536).
- Distributed TTL leases in `simple_module_core.leases`: `lease(name, ttl)` (an
  owner-checked lock with `token`, a strictly increasing `fence`, `refresh()`,
  `release()` and `async with` waiting) and `semaphore(name, slots, ttl)` (at
  most N holders across processes). Backed by Redis when `SM_REDIS_URL` is set,
  else the new framework table `sm_lease` (migration `d263ea727663`, a new root
  labelled `leases`), else in-process; `create_app` and the Celery worker
  bootstrap install it. An expired owner can neither refresh nor release (#539).
- Optional Sentry error reporting: `pip install simple_module_hosting[sentry]` and set `SM_SENTRY_DSN` (plus `SM_SENTRY_ENVIRONMENT`, `SM_SENTRY_TRACES_SAMPLE_RATE`). Web and Celery worker processes tag events with request id, tenant, user id, module and task, and scrub auth headers, cookies, `token`/`code` query values and request bodies. Without a DSN the SDK is never imported (#538).
- Sentry events no longer leak secrets the SDK's exact-name scrubber misses: auth-, session- and token-like headers (`X-Auth-Token`, `Proxy-Authorization`, `X-Forwarded-For`), nested secrets in `extra`/`contexts`, tokens in log and HTTP breadcrumbs, credentials in exception messages, and Celery task args/kwargs are scrubbed for errors and transactions alike (#538).
- In-process durable outbox delivery and lifespan-owned recovery sweeps, automatically enabled in eager mode (#565).
- Sentry scrubbing now covers every event field (tags, `server_name`, top-level stacktraces), camelCase and short key names (`basicAuth`, `pwd`, `otp`), header/query lists of pairs, bytes, quoted and escaped-JSON values, whole `Cookie:` lines, passwords containing `@`, JWTs and bare long tokens; SQL `db.params` are dropped. Behaviour change: a scrubber failure now drops the event instead of letting the SDK decide, and strings over 64 KiB are truncated (the old patterns were quadratic: a 20 KB string stalled `before_send` for over a minute) (#538).
- Per-route rate limits (#529): modules declare `RateLimitRule(rate, key=...)` in the new
  `register_rate_limits(registry)` hook, and handlers use the
  `RateLimit("10/minute", key="user")` dependency. Keys: `user`, `ip`, `user_or_ip`,
  `tenant`; both apply to anonymous and signed-in requests and answer `429` with
  `Retry-After`.
- `forwarded_host_allowlist` host setting (#528): behind a trusted proxy (`SM_TRUSTED_PROXY`),
  `X-Forwarded-Host` replaces the request host (and `scope["server"]`) when it matches an exact host or
  `*.example.com` entry, so `url_for` and subdomain tenancy see the public host. Empty (default) ignores
  the header; tenant subdomains need `*.<subdomain_base>` in the list.
- Configurable CORS (#527). `cors_allow_origins` (plus `cors_allow_credentials`,
  `cors_allow_methods`, `cors_allow_headers`, `cors_expose_headers`, `cors_max_age`;
  restart-required) registers a policy on `/api/`; modules add policies with the new
  `register_cors_policies` hook. The dispatcher runs before `BodyLimit`, so preflights
  never reach auth and a 413 keeps its CORS headers. `file_storage` serves public
  files cross-origin (Range-capable) unless the new `public_files_cors` setting is off.
- PostgreSQL pool, connect, statement and idle-in-transaction timeout settings for web and worker engines, with worker pool and statement overrides (#531).
- The OpenAPI export declares `bearerAuth` and `sessionCookie` security schemes and a
  `security` entry per operation (`[]` for public routes), so generated clients know where
  credentials go (#534). New `Authenticated()` marker dependency
  (`simple_module_hosting.token_guard`) for routes any signed-in user may call, and diagnostic
  `SM031` (WARNING, dev boot) for `/api` routes with no gate and no public match. Marked
  `Authenticated()`: `GET/POST /api/tenants/`, `POST /api/tenants/{tenant_id}/switch`,
  `DELETE /api/tenants/current/membership`, `POST /api/tenants/invitations/accept`,
  `GET/PATCH /api/users/me`, `POST /api/users/me/password`,
  `POST /api/users/me/sessions/revoke-all`. Tokens are still refused on these.
- Release process (#510): `release.yml` runs the whole PR suite (`pr.yml` via
  `workflow_call`) against the dispatched commit and `build` needs it, so nothing
  is built or published from a red commit. The duplicated bump + lockfile steps
  are one composite action (`.github/actions/bump-version`). `finalize` cuts a
  dated CHANGELOG section with `scripts/cut_changelog.py` (renames `[Unreleased]`,
  inserts a fresh one, updates compare links) and the GitHub release notes come
  from that section. `docs/release.md` documents the package-version vs
  `FRAMEWORK_API_VERSION` split; a test pins that the module template's
  `requires_framework` contains `FRAMEWORK_API_VERSION`.
- `simple_module_core.deprecation` (`deprecated`, `deprecated_module`, `deprecate`)
  registers every shim with a `remove_in` release; `host/tests/test_deprecation_expiry.py`
  fails once the framework version reaches it (#515, `docs/framework/deprecations.md`).
- German catalogues for all framework and module screens, available by adding `de` to `i18n_supported_locales`,
  with enforced key and placeholder parity in CI (#492).
- `make ci-doc-paths` (`scripts/check_doc_paths.py`, part of `make lint` and the
  `python-lint` job) fails when a backticked repo-rooted path in `docs/`,
  `CLAUDE.md`, `README.md` or `skills/**/SKILL.md` does not exist; tutorial
  examples go in `scripts/doc_path_allowlist.txt` (#519).
- New `docs-build` PR job (`make ci-docs-build`) builds the VitePress site, which
  `docs/superpowers/` and `docs/plans/` are excluded from (#519).
- `AuditLink.for_model(Model, url_template=..., ...)` fills `entity_type` (class
  name) and `table_name` from the model; every module's `register_audit_links`
  now uses it. `simple_module_db.independent_session(app)` is an async context
  manager for out-of-request sessions that commits on success and rolls back on
  error (`permissions` startup replay and `api_tokens` last-used write use it)
  (#523).
- Framework pagination helper (#513): `simple_module_db.PageParams`, `Page` and
  `async paginate(session, stmt, params)` (clamps to the last page, never a
  negative offset, counts through soft-delete/tenant filters), `clamp_page` /
  `total_pages`; `simple_module_hosting.pagination` adds the strict
  `page_params(n)` and clamping `lenient_page_params(n)` dependencies; and a
  `PaginationBar` component in `@simple-module-py/ui` (`ui.pagination.*` keys).
- New `mail` module (`simple_module_mail`) owns outgoing mail: the SMTP/console
  transport, its settings (`/admin/settings/`, package `mail`) and the on-demand
  `mail.mailer` health check behind "Test mailer connection". Modules send through
  `simple_module_core.mail` (`current_mail_sender()` / `resolve_mail_sender(db)`),
  which falls back to logging when no transport is installed (#496).
- Tenant invitations are now emailed (#496). With `background_tasks` installed
  the email goes through the durable outbox (`tenants.send_invitation_email`,
  retried); otherwise it is sent after the request commits. A link is only
  emailed when `public_base_url` is set. The invite API response gains
  `emailed`, and the invite form says whether the link was emailed.
- `captured_mail` pytest fixture in `simple_module_test` records sent mail.
- User directory protocol (#501): `simple_module_core.user_directory`
  (`UserDirectory`, `DirectoryUser`, `DirectoryStats`, `NullUserDirectory`,
  `get_user_directory` / `set_user_directory`). `users` installs
  `UsersDirectory`, `keycloak` installs `KeycloakDirectory` (users who have
  signed in; roles unknown). `audit_log`, `dashboard`, `file_storage`,
  `api_tokens` and `permissions` read users through it instead of importing
  `users.models`, so actor names and search, dashboard tiles and uploader
  names now work under Keycloak instead of querying the empty `users_user`
  table. `get_many` returns an entry for every caller spelling of a known id
  (`parse_user_ids` maps a uuid to all of them). See
  `docs/framework/user-directory.md`.
- Activity feed protocol (#501): `simple_module_core.activity_feed`.
  `audit_log` installs it; the users edit page's *Recent activity* card reads
  it, which removes the `users` ↔ `audit_log` import cycle.

### Changed
- **Behaviour change:** the `simple_module_test` plugin no longer refuses `-n`
  on Postgres: each pytest-xdist worker creates and uses its own database
  (`<db>_gw0`, `<db>_gw1`, ...) and points `SM_TEST_DATABASE_URL` at it, so the
  role needs `CREATEDB`. `make test-py-pg` now runs with
  `-n $(PYTEST_WORKERS) --dist loadgroup` like `make test-py`
  (`PYTEST_WORKERS=0` keeps the old serial run on the named database).
- `simple_module_test` on Postgres builds the schema once per process and, before
  each later test, deletes every row and restarts the sequences instead of
  dropping and re-creating `public` (~0.05 s instead of ~0.25 s per test). A
  direct `reset_schema()` call or any change to the catalog (a test's own
  tables, extensions, constraints) falls back to the full rebuild.
- `create_app` no longer resolves every route's dependencies at build time
  (~0.5 s for the full module set, ~70% of a test's setup): module routers now
  get their prefix from `include_router(prefix=...)`, which skips FastAPI's
  resolving empty-path check (effective paths and the OpenAPI document are
  unchanged), and the route prefix guard and the SPA overlap check read paths
  from FastAPI's include contexts without resolving routes. Outside
  `environment="testing"` the lifespan still resolves all routes at startup,
  so the first requests after boot stay warm. The SQLite and Postgres suites
  run ~45% faster.
- tenants and api_tokens pages call their APIs through the typed client and take
  typed component props (#504). **Behaviour change:** the api_tokens pages no longer
  receive the unused `api_url` prop.
- users, background_tasks, branding, settings, file_storage and the first-run setup
  wizard call their APIs through the typed client (#504), completing the migration.
  **Behaviour change:** failed requests from these pages now show translated error
  toasts (the server's `detail` or a localized fallback) instead of raw or generic
  English text. `make lint` / CI reject raw `fetch(` in shipped `.ts`/`.tsx`
  (`ci-check-no-raw-fetch`, `scripts/check_no_raw_fetch.py`) unless marked
  `// raw-fetch-ok: <reason>`.
- file_storage's public file routes (`/api/file-storage/public/{file_id}` and
  `.../{filename}`) now have distinct OpenAPI operation ids (`file_storage_public_file`,
  `file_storage_public_file_named`); the cosmetic `filename` is a path segment on the
  named route only. Paths and responses are unchanged.
- Typed page props (#505): `@simple-module-py/ui` registers `SharedProps` (now including `i18n`) with
  Inertia, so `usePage().props.auth` is typed, and exports `usePageProps<T>()` for components and
  layouts. Pages take typed component arguments. The `as unknown as` casts in module pages, `packages/ui`
  and `host/client_app` are gone, and `make lint` / CI reject new ones (`ci-check-no-double-cast`)
  unless marked `// cast-ok: <reason>`. `docs/frontend/shared-props.md` and the
  `simple-module-inertia-pages` skill no longer teach the cast.
- **Behaviour change:** bulk and Core DML writes on audited models now produce
  audit entries (actions `bulk_*`), in requests and Celery workers. Statements
  that set only excluded columns (the outbox, `TaskExecution.heartbeat_at`) are
  still not recorded. Opt a statement out with
  `execution_options(sm_audit=False)` (#557).
- **Behaviour change:** `simple_module_db` no longer emits the `entity.created` / `entity.updated` /
  `entity.soft_deleted` log lines for models flagged `__audit_exclude__ = True` (`AuditEntry`,
  `OutboxMessage`, `RetainedLog`), so retained logs cannot re-log their own writes (#537).
- **Behaviour change:** `rate_limit_authenticated` (off by default) now keeps one budget per
  signed-in user instead of one per client IP, so users behind one NAT no longer share it (#529).
- `scripts/bump_version.py` also bumps every `modules/*/package.json`; all
  `package.json` versions are now in lockstep with the Python packages (they were
  0.1.0, keycloak 0.0.0) (#510).
- `users` and `keycloak` register their anonymous login routes with
  `register_public_routes` instead of `AuthProvider.get_public_paths()`, so the
  maintenance gate and `AuthMiddleware` read one mechanism (#515).
- `simple_module_hosting.settings.Settings` is documented as the combined host
  settings type, not a "back-compat shim" (#515).
- `host/client_app` now depends on `@simple-module-py/ui`; `tailwindcss` floor raised to `^4.3.3` to match the installed version (#521).
- `@simple-module-py/ui` now declares `react-hook-form`, which `components/ui/form.tsx` imports (it was only reachable through the host app) (#521).
- Docs: stale example paths in `README.md`, `CLAUDE.md`, the testing overview and the
  quickstart corrected; the historical `docs/perf` note is marked as exempt (#519).
- Bound FastAPI to `>=0.140,<0.157` in framework and module dependencies; a
  contract test guards the route guard's private FastAPI/Starlette APIs (#516).
- Declare and document the optional `file_storage[tasks]` extra for the lockstep
  background-tasks package; document `DurableTransport` as the durable-event
  extension point and verify uploads without background tasks (#502).
- Users, file_storage, background_tasks (executions and outbox), audit_log,
  settings and tenants lists now share the pagination helpers instead of
  per-module copies (#513). Browser view routes (`background_tasks`
  including the outbox page, `file_storage`, `tenants` admin, `users` admin) clamp
  `?page=0`/negative/garbage to page 1 rather than reject; every JSON list API
  (`background_tasks` executions and outbox, `audit_log`, `file_storage`,
  `users` admin) answers 422 for `page` outside 1..1,000,000 and `per_page`
  outside 1..200, where some used to accept `page=0` or an unbounded `per_page`
  or forward a huge page to SQL as an out-of-range offset. The outbox API now
  reports the clamped page when asked past the end. The audit log, executions
  and outbox tables use `PaginationBar`; their private `showing/previous/next`
  locale keys are removed in favour of `ui.pagination.*`.
- One module scaffolder (#509). `make new-module` now calls the CLI's
  `create_module` (`framework_repo=True` overlay) instead of ~980 lines of
  f-string templates in `scripts/_templates_*.py`, which are deleted, so
  `smpy create-module` / `smpy new` and `make new-module` share one set of
  `templates/module/` files. Both now emit `constants.py`, `models.py`,
  `contracts/`, `service.py`, `deps.py`, permission-guarded REST + Inertia
  endpoints, Browse/Create/Edit pages, a menu item with `label_key`,
  `register_permissions`, `locale_dirs` and `locales/en.json` (the CLI sample
  page `Index.tsx` is replaced by `Browse.tsx`). `make new-module` also adds
  the module to the `publish-pypi` matrix and runs `npm install` and
  `make gen-i18n`; a fresh module passes `make lint`. The scaffold tests live in
  `framework/cli/tests/` only.
- `audit_log` and `dashboard` no longer depend on `Users` (meta `depends_on`
  and package dependency); `background_tasks` drops its unused `Users`
  dependency (#501). `api_tokens` moves `Users` to `optional_depends_on` and
  its package depends on `fastapi-users-db-sqlalchemy` instead of
  `simple_module_users`, so a Keycloak install keeps service keys (personal
  tokens are refused there). `permissions` (role pages) still depends on
  `Users`.
- **Behaviour change (#501):** dashboard user figures the auth provider cannot
  give are `null` in `/api/dashboard/stats` and their tile is hidden (with no
  provider, all three; under Keycloak, `users_created_this_month`). Personal
  API tokens are refused for an owner whose roles the directory cannot read
  (Keycloak), as before.
- `audit_log.resolve`: `resolve_actors`, `actor_filter` and `actor_link` take
  the `UserDirectory`; `USER_ENTITY_TYPE` is gone (use the directory's
  `entity_type`). `audit_log.export.stream_csv` takes the directory too.
  `PermissionService` and `ApiTokenService` accept a directory (defaults to
  the null directory). With no directory, the audit Actor search matches the
  term as an exact actor id (#501).
- `file_storage.resolve.resolve_uploader_labels` is now core's
  `resolve_user_labels(directory, db, ids)` (the directory is the first
  argument), and `users.audit.resolve_user_labels` delegates to it (#501).
- `smpy` module catalog: `background_tasks` requires `settings` instead of
  `users` and `dashboard` requires nothing; a test pins that every entry's
  `requires` covers its module's `depends_on` (#501).
- **Behaviour change (#501):** outside development, a module whose
  `depends_on` names a module that is not loaded now refuses the boot with one
  `MissingDependencyError` (an `InvalidModuleError`) listing every
  `(module, dependency)` pair, instead of a warning and a module running
  against tables nobody owns. Development still logs it; `make doctor`
  reports it as the new `SM030` error. Selecting `keycloak` drops `Users`, so
  a Keycloak install must leave out `permissions` (`SM_MODULES_ENABLED`). The outbox worker still sorts leniently.
- New `ModuleMeta.optional_depends_on`: modules to sort after when loaded,
  never required (#501). `users`, `tenants`, `file_storage`,
  `background_tasks`, `site_lock`, `api_tokens` and `keycloak` move their
  ordering-only `Settings` entry there, so the boot order is unchanged and
  the `settings` plugin can still be disabled (#500).
- The module-settings mechanism moved from the `settings` plugin into the
  framework (#500): `register_module_settings` / `ModuleSettingsRegistry` to
  `simple_module_core.module_settings`, hydration (`hydrate_settings`,
  `build_settings`, `OverrideSource`, field helpers) to
  `simple_module_core.settings_hydrate`, secret-field masking to
  `simple_module_core.secret_fields`, and the `Setting` model, its constants,
  the read-only override queries and `hydrate_settings_sync` to
  `simple_module_db.stored_settings`. The table (`settings_setting`) is
  unchanged; no migration. The hosting layer imports these statically instead
  of reaching the plugin through `importlib` strings, and builds its pre-app
  and secret-key SQL from the shared column constants.
- **Behaviour change (#500):** registration and boot-time hydration no longer
  need the `settings` plugin. The registry is created on `app.state` on first
  use, `host` settings are always registered, and the lifespan hydrates from the
  table directly, so module and host settings still come from the DB with the
  plugin disabled (it keeps the admin UI, hot reload and the key/value API).
  The pre-app host read and the generated `SM_SECRET_KEY` are likewise stored
  and read without it; outside development an unreachable database now refuses
  the boot even when the plugin is not installed.
- **Out-of-tree hosts without the `settings` plugin (#500):** the framework now
  always contributes `settings_setting` to the migration metadata, so the next
  `alembic revision --autogenerate` will emit a `create_table` for it. Keep that
  operation (the framework reads the table at boot).
- `make new-module` / `smpy create-module` scaffolds subclass `DbBackedSettings`
  and register through `register_module_settings` instead of assigning
  `app.state.<pkg>` directly (#500).
- SM009 now detects dynamic framework imports of plugin packages, including importlib aliases and fixed f-string package prefixes (#500).
- CI and local lint now share one definition (#508). `make ci-js-typecheck`
  depends on `gen-pages`, so `make lint` works on a fresh clone. New targets
  `ci-check-metadata` (now also runs `check_readmes.py` in CI), `ci-i18n-fresh`
  (in `make lint`), `ci-css-build` and `ci-doctor`; `pr.yml` calls them. CI gains
  a `doctor` job (`make doctor` against a freshly migrated SQLite DB) and a
  separate `postgres-tests.yml` workflow (`make test-py-pg`; nightly, manual and
  path-filtered PRs, not part of `pr-checks`).
- Biome runs with `--error-on-warnings`; the seven unused `type React` imports
  and the useless fragment in `ErrorPage.test.tsx` are removed (#508).
- `uv.lock` is now committed (the ignore rule is gone), keys the CI caches, and
  CI installs with `uv sync --locked` (`UV_SYNC_FLAGS`); `make install` is
  unchanged (#508). The release workflow runs `uv lock` after
  the version bump so the lock follows the lockstep versions.
- **Behaviour change:** the `users` mailer settings (`mailer`, `smtp_*`) moved to
  the `mail` module as `backend` and `smtp_*`; a data migration (`d7b3a9e5c1f2`)
  moves stored values (#496). `simple_module_users` now depends on `simple_module_mail`, and
  the `users.mailer` health check is now `mail.mailer`. The `users.Mailer`
  protocol is unchanged.
- `ty` now checks `invalid-argument-type` and `invalid-assignment` in shipped
  code (tests stay exempt), and the ~150 mypy-style `# type: ignore[...]`
  comments, which suppressed nothing under ty, are gone (#507). Remaining
  third-party false positives carry `# ty: ignore[<rule>]`.
  `settings.registration.register_module_settings` is generic over the settings
  class, so `services_factory` receives the concrete type.
- **Behaviour change (#507):** a tenant resolver that returns a `UUID` (bare,
  in a pair or in `TenantResolution`) now binds its string form; any other
  non-`str` tenant id or source raises `TypeError` instead of flowing into
  tenant filters.
- **Behaviour change (#507):** `UsersSettings.cookie_samesite` only accepts
  `lax`, `strict` or `none` (case-insensitive). Any other stored value is
  dropped with a WARNING and the default `lax` applies.
  The settings editor treats a `Literal[...]` of strings as a string select
  (it was filed under `json` with a free-text box).
- `get_file_storage_service` raises a clear `RuntimeError` when the storage
  backend has not been initialised, instead of building a service around
  `None` (#507).
- `RequiresPermission` raises `simple_module_core.permission_denied.PermissionDenied`
  (an `HTTPException` carrying `.permission`); the 403 handler reads the
  attribute instead of parsing the message (#518). `PERMISSION_DENIED_PREFIX`
  stays importable.
- Settings cross-field validators (background_tasks, file_storage, site_lock,
  users, keycloak) name their related fields, so lenient hydration drops only
  the stored culprit instead of resetting the whole module (#558).
- The tenancy scope walk is about 2× cheaper for statements that pass through
  unchanged (get 26→15 µs, pagination count 83→44 µs) (#559).
- **Behaviour change (#494):** a pre-app settings read that fails (connection,
  query, import error) is no longer treated as a fresh install. Outside
  development and testing the host and the Celery worker refuse to boot with
  `HostSettingsUnavailableError` instead of building with defaults (which
  silently disabled `multi_tenant`). Only a missing settings table falls back
  quietly. Likewise the secret key: an ephemeral key is used only before the
  settings table exists; otherwise boot fails with `SecretKeyUnavailableError`,
  and a blank stored key is replaced atomically.
- **Behaviour change (#495):** the session cookie is `Secure` outside
  development and testing. New `HostSettings.session_cookie_secure`
  (`SM_SESSION_COOKIE_SECURE`); set `SM_TRUSTED_PROXY` behind a TLS terminator,
  and `false` only for installs that serve browsers plain HTTP on purpose.
- **Behaviour change (#498):** with `audit_log` installed, writes made in Celery
  tasks and durable outbox handlers are audited (including `TaskExecution`
  creation and status changes; its heartbeat, timestamps and retry counter are
  excluded, so a heartbeat-only update writes no audit row, and the
  `OutboxMessage` delivery bookkeeping is not audited at all). The audit callback is bound per engine instead of a
  process-global, through the new `simple_module.audit_sinks` entry-point
  group. Worker tests that build a database without the audit table need the
  sink off (see `background_tasks/tests/conftest.py`).
- **Behaviour change (#530):** password-login lockout now holds across workers,
  source IPs and restarts. `users.login_lockout_account_failures` (new, default
  10) failures for one account within `login_rate_limit_window_seconds`, from
  any network, lock it for `login_rate_limit_cooldown_seconds`: every password
  login for it answers 429 with `Retry-After`, the correct password included;
  the failure that trips the lock is itself answered 429. Attempts are counted
  before the password is checked (a correct password gives the slot back), so
  a parallel burst gets no more tries than the threshold.
  `login_rate_limit_failures` (5) attempts from one IP for one username per
  window are admitted. Unknown usernames go through the same rules on the rate
  limit store, so a 429 does not reveal whether an account exists.
  Counters live on `users_user` (a migration adds `failed_login_count`,
  `last_failed_login_at` and `locked_until`) and on the host rate-limit store
  (Redis when `SM_REDIS_URL` is set). The per-worker `LoginRateLimiter` is gone.
  A successful password reset lifts the lock and clears the failure count
  (audited, like an admin unlock).
- **Behaviour change (#530):** `POST /api/users/auth/token` now has the same
  lockout and throttle: 429 while locked; bad credentials are still 401. Its
  email lookup is now case-insensitive, matching the session login.
- **Behaviour change (#530):** the stock fastapi-users auth router is no longer
  mounted, so `/api/users/auth-inner/login` and `/api/users/auth-inner/logout`
  are gone. Use `/api/users/auth/login` and `/api/users/auth/logout`.
- **Behaviour change (#543):** with `allow_signup` off, an OAuth sign-in no
  longer creates an account. It answers 403 `OAUTH_SIGNUP_DISABLED` unless the
  identity is already linked or its email matches an existing account, which
  still link and sign in.
- **Behaviour change (#547):** `users.require_verification` is honoured. With
  it off, no verification email is sent, the register page says so, and
  password login no longer requires a verified email — including for accounts
  registered while it was on. Such accounts stay unverified, and an OAuth
  sign-in whose email matches an unverified password account is refused with
  403 `OAUTH_ACCOUNT_NOT_VERIFIED` instead of linking to it (an account already
  linked to that OAuth identity still signs in). With it on,
  `POST /api/users/auth/token` now refuses an unverified account with 400
  `LOGIN_USER_NOT_VERIFIED`, as the session login already did; it used to mint
  bearer tokens for one.
- **Behaviour change (#544):** `file_storage` callers without
  `file_storage.manage` (granted to admins and to `tenant:admin`/`tenant:owner`)
  see, download, change and delete only files they uploaded; anyone else's
  file is a 404. Files with no recorded uploader are visible to managers only.
- **Behaviour change (#545):** `file_storage` serves a stored type inline only
  from an allow-list (raster images, PDF, JSON/GeoJSON, plain text, CSV, opaque
  binaries, audio/video/font). Everything else, any `*+xml` and any malformed
  value included, is a sandboxed attachment.
- `POST /api/users/auth/token` returns `token_type="Bearer"`, and every bearer
  resolver (users, keycloak, api_tokens) accepts the scheme in any case (#533).
- **Behaviour change (#486):** for settings classes that read the environment
  (today `background_tasks`, `SM_BG_TASKS_*`), an env var now beats a value
  stored from the admin UI, and `SM_REDIS_URL` beats a stored broker/result
  backend. Saving a field the environment sets returns a 422 on that field.
- **Behaviour change (#488):** self-registered users now get the standard
  `user` role; OAuth-provisioned users get it only while `allow_signup` is on.
  A new data migration (`b5018b617142`) seeds the role on **fresh installs
  only** (no rows in `users_user`), so a role an admin deleted is never brought
  back. On an existing install without a `user` role, signups still get no
  role and a warning is logged — create the role in Admin → Roles to opt in.
- **Contract change (#489):** `StorageBackend.presigned_get_url` takes
  keyword-only `content_disposition` / `content_type`.
- **Behaviour change (#456):** the OpenAPI schema moved from `/openapi.json` to
  `/api/openapi.json`, and is no longer served outside development unless
  `openapi_public` (`SM_OPENAPI_PUBLIC`) is on. The bare `/openapi.json` was
  previously served, and anonymous, in production.

### Fixed
- Background task stuck sweeps and retention purges now use DB-backed settings so admin edits apply instead of reading only environment variables (#565).
- User directory follow-ups (#501): `audit_log` installs its activity feed in
  `on_startup` (cleared on shutdown) instead of `register_settings`, which
  tripped `SM012`; `resolve_user_labels` omits users whose label is empty so
  callers show the stored id; the `users` and `keycloak` directories compute
  their stats in one query instead of two or three.

### Deprecated
- `AuthProvider.get_public_paths()` is no longer part of the `AuthProvider`
  protocol; third-party providers that still define it keep working with a
  `DeprecationWarning`. Removed in 0.1.0 (#515).
- Every existing shim now has an enforced removal release of 0.1.0 (#515):
  `host/routes_legacy.py`, `settings.registration` / `settings.module_registry` /
  `settings.hydrate`, `props.lazy()` and the one-argument `register_event_handlers`
  form (which now warns).
- `settings.registration`, `settings.module_registry` and `settings.hydrate`
  re-export the framework objects above and emit a `DeprecationWarning`;
  `settings.models.Setting`, `settings._secrets` and the moved names in
  `settings.store` / `settings.constants` re-export them silently (the same
  objects, never a second `Setting` mapping). Removal no earlier than 0.1.0
  (#500).

### Added
- `TenantDeleted` event and `TenantService.delete_tenant` (#491). No endpoint
  yet: what deleting a tenant means for other modules' rows is still open.
- `simple_module_test.wait_for` / `wait_for_sync`; `make ci-check-test-sleeps`
  flags unmarked fixed sleeps in tests (#512).
- `scripts/check_metadata.py` asserts the ty `extra-paths` and pytest
  `testpaths` lists match the packages on disk, in `make lint` and CI (#520).
- Tests for the api_tokens, feature_flags and background_tasks pages,
  `tenants/shared_props.py` and `file_storage/upload_guards.py` (#514).
- `PATCH /api/users/admin/{id}/unlock` lifts a login lockout early (audited).
  `UserListItem` carries `locked_until`; the users list shows a "locked" badge
  and the edit page a "Locked until" row with an Unlock action (#530).
- `app.state.sm.rate_limit_store` exposes the host's rate-limit store to
  modules. `WindowStore` gains `peek()` (read without counting), `reset()` and
  `hit(..., sliding=True)` (#530).
- Durable event delivery (#459). `bus.subscribe_durable(EventType, handler,
  name=...)` and `await bus.publish_durable(event, db)` in
  `simple_module_core.events`; handlers are called as
  `await handler(event, ctx: DurableContext)`. `background_tasks` installs the
  transport: an outbox table (`background_tasks_outbox`, **migration**
  `e878882924e7`) written in the publisher's transaction, a post-commit
  `background_tasks.dispatch_outbox` task, and a 30 s beat sweep
  (`background_tasks.sweep_outbox`) for crashes between commit and publish.
  At-least-once delivery with exponential backoff (10 s doubling, 1 h cap);
  writes through `ctx.db` commit with the delivery mark and land exactly once
  (a handler committing `ctx.db` itself is refused with `HandlerCommitError`);
  other side effects are at-least-once. Handlers run in the scope recorded at
  publish (`scope`: the publisher's tenant; `all_tenants()` for a publish made
  inside `all_tenants()`; no tenant — strict — for one made with none bound),
  with a timeout inside the lease, and
  may publish durably themselves, in a worker too. Timestamps come from the
  database clock. Rows go `dead` after `outbox_max_attempts` (8); an unknown
  handler (rolling deploy) is retried like a failure. New admin page
  `/admin/background-tasks/outbox` (retry dead, discard) and API under
  `/api/background_tasks/admin/outbox`. New settings `outbox_max_attempts`,
  `outbox_sweep_interval_seconds`, `outbox_lease_seconds`,
  `outbox_handler_timeout_seconds`. Delivered rows are
  purged after `retention_days`. Without background_tasks, `publish_durable`
  raises `DurableDeliveryUnavailable`; `publish` / `publish_nowait` are unchanged.
  New `simple_module_db.no_tenant()` context: no tenant bound and outside any
  `all_tenants()`.
- **New `api_tokens` module** (#455): personal access tokens (`smpat_…`) and
  service API keys (`smsk_…`). Only `sha256(token)` is stored and the secret
  is shown once; a token is resolved by one indexed lookup per request (no
  cache), so a revoke applies on the next request. Every token carries scopes
  that cap the principal's permissions on top of the owner's live grants (an
  admin's token is worth its scopes only). Service keys get roles chosen at
  creation (never `admin`); every token is pinned to the tenant it was created
  in (a PAT only while its owner is still a member). Self-service page at
  `/api-tokens/` (user menu), admin screen at `/admin/api-tokens/`; tokens can
  only be managed from a cookie session, with `RequiresCsrf`. New PyPI package
  `simple_module_api_tokens`; not added to the `smpy new` scaffold. Needs a
  migration (`branch_labels = ("api_tokens",)`).
- `UserContext` gains `auth_kind` (`"session"` by default; `"pat"` /
  `"service"` for tokens) and `scopes` (`None` = uncapped), carried through
  `from_user`, `to_session_dict` and `from_session_dict`. `auth.contracts.tokens`
  holds the kinds and the `smpat_` / `smsk_` prefixes.
- `simple_module_hosting.permissions.apply_scope_cap` and
  `simple_module_core.permissions.is_admin_principal`. A role-only admin gate
  should use `is_admin_principal(user)`, which is `False` for any token.
- `simple_module_hosting.token_guard` (#455): an app-wide dependency that
  refuses an API token (403) on every route without a permission gate
  (`RequiresPermission` / `require_permission`) and on every page; a public
  route serves it as anonymous. `TokenAllowed()` opts a route in explicitly.
  Sessions and provider bearer tokens are unaffected. **Behaviour change** for
  any module that relied on a token reaching an ungated route: gate it with a
  permission, or mark it `TokenAllowed`.
- `auth.contracts.tokens.AUTH_KIND_BEARER`: a `users` access token or Keycloak
  JWT now reports `auth_kind == "bearer"` (was `"session"`). Same rights; it
  only stops such credentials from managing API tokens.
- Resumable multipart uploads for `file_storage` (#454): `POST /api/file-storage/uploads`
  sessions with presigned S3 part URLs (or relayed parts on the filesystem backend),
  4-way parallel parts with retry and `localStorage` resume in the Files page,
  `s3_public_endpoint_url`, CSP `connect-src` for the S3 origin, and an hourly
  `file_storage.reap_stale_uploads` janitor (with `background_tasks`). Sessions count
  against the quota and the assembled size is re-verified at completion. Migration
  `a659221c464b` adds `file_storage_upload_session`.
- background_tasks Celery config (#447, #448, #450): a module can ship a light
  `task_config.py` (`TASK_ROUTES`, `QUEUES`, `BEAT_SCHEDULE`) read without
  importing `tasks.py`; `task_routes_override` re-routes tasks at runtime and the
  Workers page lists the effective routes. New restart-required settings:
  `visibility_timeout_seconds`, `worker_max_tasks_per_child`,
  `worker_max_memory_per_child_kb`, `task_reject_on_worker_lost`,
  `task_soft_time_limit`, `task_time_limit`, `worker_concurrency`; raw Celery conf goes in the environment-only
  `SM_BG_TASKS_CELERY_OVERRIDES` (serializer/import/code-loading keys refused). `SM_BG_TASKS_WORKER_QUEUES` / `_INCLUDE_MODULES` / `_EXCLUDE_MODULES`
  (comma-separated, environment only, never DB-backed; `SM_BG_TASKS_WORKER_QUEUES=a,b`) limit which modules' `tasks.py` a process
  imports (autodiscovery and the eager beat import); `make worker` passes `-Q`.
  `make doctor` warns (`SM028`) on a top-level heavy import in `tasks.py`.
- OpenAPI export (#456): `smpy openapi export [--out] [--module]` / `make openapi`
  write the `/api/**` schema without starting a server; operationIds are
  `<module>_<function>`; view routes are excluded; new host settings
  `api_title`, `api_version`, `api_description`, `openapi_public`. See
  `docs/guide/openapi-clients.md` for hey-api and Dart CI recipes.
- Postgres extensions and column types (#458): `ModuleBase.db_extensions()`
  declares the extensions a module needs (`["ltree"]`); `ensure_db_extensions`
  runs from `env.py` (host and scaffold) before the revisions, emitting
  `CREATE EXTENSION IF NOT EXISTS` (also in offline SQL) and raising
  `UnsupportedDatabaseError` on SQLite. `simple_module_db.types.LTree` and
  `TSVector` are native on Postgres and `TEXT` on SQLite; autogenerate renders
  them with the right import. New doctor code `SM029`, and a `postgres` pytest
  marker (skipped unless `SM_TEST_DATABASE_URL` is Postgres). The Postgres test
  fixtures re-create declared extensions after each schema reset. No migration.
- `from background_tasks import heartbeat` (#451): a long-running task calls
  `heartbeat()` to refresh `heartbeat_at` (throttled to one write per 30 s; a
  no-op outside a task). `@shared_task(..., stuck_after=<seconds>)` sets a
  per-task stuck threshold that the sweep honours ahead of
  `SM_BG_TASKS_STUCK_AFTER_SECONDS`. No migration.
- `from background_tasks import enqueue_after_commit` (#452): publishes a task
  only once the caller's transaction commits (nothing on rollback), and
  returns the reserved task id so a row can name it up front.
- HTTP `Range` support on file downloads (#453): single ranges answer `206`
  (`416` when unsatisfiable, multi-range falls back to `200`), honouring
  `If-Range`. Storage backends gain `get_range(key, start, end)` (inclusive
  end); a third-party backend without it keeps serving full `200`s.
- `smpy host gen-i18n` and a scaffold `make gen-i18n` target (#449).
- **Host override layer for module copy** (#415). A host ships
  `host/locales/overrides/<lang>.json` (nested or flat dotted keys) and it is
  applied after every module, framework and host catalog, so the server-side
  `Translator`, menus and Inertia props all see it. An override only replaces an
  existing key: an unknown key is skipped with a warning and reported by
  `make doctor`. Admin-only keys stay admin-only.
- **Public tenancy API** (#418): `simple_module_hosting.tenancy` exposes
  `tenancy_mode(app)`, `single_tenant_id(app)`, `require_tenant(...)` (binds
  the single-tenant id, or the request's tenant else `on_missing`) and
  `tenant_vary(request)`; `TenancyMode` lives in `simple_module_core.tenancy`.
  Modules no longer need to read the middleware stack.
- `NativeSelect` takes a `wrapperClassName` for sizing the control (#421).
  `className` still targets the `<select>`.
- **The `/setup` wizard ships with the framework** (#351). Since 0.0.33
  `SetupMiddleware` redirected a fresh install to `/setup`, but the route and
  page lived only in this repository's unpublished host, so any other host got
  `/` → `/setup` → 404. `create_app` now mounts the wizard
  (`simple_module_hosting.setup_wizard`) and `gen-pages` registers its page
  (`Setup/Wizard`) from the wheel; a host needs no setup code and should delete
  any copy it carries. Steps complete from the browser through a new
  `SetupStep.action` (`SetupAction` / `SetupField` in `simple_module_core`),
  POSTed to `/setup/steps/<id>` with the session CSRF token. An action runs only
  while its own step is pending (409 otherwise); `users` ships the
  first-administrator action, which re-checks under a database lock inside the
  inserting transaction so concurrent requests create one superuser. Required
  steps without an action are logged at boot. The old host-only
  `/setup/administrator`, `/setup/migrations` and the UI-less
  `/setup/site-basics` endpoints are gone.
- **Postgres test runs** (#343) — `SM_TEST_DATABASE_URL` points the
  `simple_module_test` fixtures at Postgres, and `make test-py-pg` runs the
  whole Python suite there. The schema is reset once per test, so `app` and
  `db_session` see each other's rows as they would in production.
- **`tenants` module** — SaaS organisations: tenants, many-to-many memberships
  with per-tenant roles (`owner`/`admin`/`member`, surfaced as `tenant:<role>`
  on the active tenant only), email-bound invitations, platform suspend /
  reactivate, and the membership-validated tenant resolver. Ships the seams a
  billing module needs: an `EntitlementProvider` on
  `app.state.tenants.entitlements` (seat limits enforced, HTTP 402), lifecycle
  via `TenantService.set_status`, and after-commit domain events. See
  [docs/framework/multi-tenancy.md](docs/framework/multi-tenancy.md).
- `simple_module_db.tenant_context()` / `all_tenants()` and the
  `all_tenants=True` execution option, for acting as one tenant — or
  deliberately across tenants — outside a request.
- `TenantMiddleware` consults `app.state.tenant_resolver` when a module
  registers one.
- `background_tasks` carries the enqueuing request's tenant into the Celery
  task and restores it around the task body.
- Doctor check `SM024`: a unique key on a `MultiTenantMixin` table that omits
  `tenant_id`.

- `InvalidationBus` — a framework-level cache-invalidation channel any module can
  publish on (`ModuleBase.register_invalidations`, `app.state.sm.invalidation`).
  In-process by default; `background_tasks` installs a Redis pub/sub transport on
  the connection it already configures, so a write drops the matching entry in
  *every* worker instead of only the one that performed it.
  Turn it off with `SM_BG_TASKS_BROADCAST_INVALIDATIONS=false`; rename the channel
  with `SM_BG_TASKS_INVALIDATION_CHANNEL` for every app on a shared Redis server
  (pub/sub ignores the database index, so DB 4 vs DB 5 does not isolate it).
  See [docs/framework/invalidation.md](docs/framework/invalidation.md) (GH #318).
- `users` publishes its `session_version` bump on that bus, so "sign out
  everywhere" and a password change stop being honoured across every worker at
  once rather than after each worker's `users.session_version_cache_ttl_seconds`
  window. The TTL now bounds a *dropped* message rather than every cross-worker
  revocation; installs without a reachable Redis keep the previous behaviour.
- Request-scoped database sessions now expose `session.on_commit(callback)` for
  synchronous or asynchronous cache refreshes and other derived state. The
  framework invokes callbacks only after a successful commit and discards them
  on rollback or commit failure.
- Every `smpy new` scaffold now ships Docker assets by default: a multi-stage
  `docker/host.Dockerfile` (uv + Node builder that runs `gen-pages` before the
  Vite build, slim non-root runtime that applies migrations on start), a
  `docker-compose.yml` matched to the `--db` choice (`app` on a SQLite named
  volume, or `postgres` + `app` — migration histories are dialect-frozen at
  autogenerate time, so containers run the same DB the migrations were
  generated against), plus `redis`/`worker`/`beat` reusing the app image when
  `background_tasks` is selected, a `.dockerignore`, and `make docker-up` /
  `docker-build` / `docker-down` targets. Previously Docker files only
  appeared with `background_tasks`, and their frontend stage couldn't build
  real apps (no `gen-pages` step). The separate `worker.Dockerfile` is gone;
  worker/beat run the same image with a celery command. `smpy new` also
  generates real `SM_USERS_*_TOKEN_SECRET` values into `.env.example` so the
  production-mode containers pass `UsersSettings` boot validation.

### Changed
- The `users` and `keycloak` auth providers return `None` at once for a bearer
  value with an `api_tokens` prefix instead of looking it up (#455), leaving it
  to the principal resolver chain.
- `require_permission` (auth) skips its admin-role shortcut, and
  `resolve_principal_permissions` / `resolved_permissions_for` cap the set,
  when the principal carries `scopes`. The `/admin` index, the Doctor page and
  the maintenance bypass no longer admit an admin's token on the role alone.
- The `tenants` resolver binds a service principal to its pinned tenant and
  ignores the tenant header and subdomain for it.
- `make new-module`: the scaffolded `tsconfig.json` no longer sets `baseUrl`
  (removed in TypeScript 6), `views.py` imports `InertiaResponse` from
  `simple_module_inertia`, and `package.json` peers `@inertiajs/react` `^3.7.0`.
- `StoredFile.checksum_sha256` / `StoredFileOut.checksum_sha256` are now nullable (#454):
  files uploaded through the multipart flow have no checksum until
  `file_storage.compute_checksum` runs, and `ETag`s fall back to id + size.
- **Dashboard stats are admin-only on single-tenant installs too** (#464).
  `dashboard.view` was mapped to the ordinary `user` role when
  `multi_tenant` was off, so any self-registered account could read user
  counts and system info. Only `admin` holds it now; grant it to another role
  in the role editor to restore the old behaviour. `/dashboard/` still renders
  for everyone, without the stats.
- **Error-page copy moved from `host.error.*` to `ui.error_page.*`** (#475),
  shipped with `simple_module_hosting`'s `ui` catalog so scaffolded apps get
  it. A host that overrides `host.error.*` in
  `host/locales/overrides/<lang>.json` must rename those keys.
- An anonymous request to a path that matches no route now gets the 404 page
  instead of a redirect to sign-in (#473). Every path that matches a route is
  gated exactly as before.
- `TenantMiddleware` now varies on `Cookie` when the tenant came from the
  session, and on `Cookie, Authorization` when it came from an authentication
  claim, so a shared cache can no longer serve one tenant's response to another
  (#418).
- **Tenant isolation fails closed.** With `multi_tenant` on, a query, bulk
  `update()`/`delete()` or insert on a `MultiTenantMixin` model with no tenant
  context raises `TenantIsolationError` instead of reading or writing every
  tenant's rows. ORM `update()`/`delete()` are now tenant-scoped too; they were
  not before.
- Changing a row's `tenant_id` is refused whether or not a tenant is bound
  (it used to be checked only inside a tenant context); only an `all_tenants()`
  block may move a row between tenants.
- Tenant rules now cover every ORM write path, not only `session.add`: an
  ORM `insert(Model)` (bulk or `.values()`) is stamped with the bound tenant
  and refused for a different one (#357); `update(Model).values(tenant_id=…)`
  is refused; a flush that writes or deletes an object belonging to another
  tenant (e.g. one returned from the identity map after a `tenant_context`
  switch) is refused.
- `tenant_context()` nested in `all_tenants()` now scopes its block; it used
  to be ignored there, so a per-tenant loop inside a platform job ran
  unscoped.
- Strict mode is held per engine, so a second `DatabaseState` in the process
  no longer switches it off for the first. The Celery worker's session gets the
  tenant listeners and the host's `multi_tenant` setting too (#371).
- New `MissingTenantError` (a `TenantIsolationError`) for "no tenant bound".
- Tenant and soft-delete criteria reach join targets, subqueries (including a
  bare Core `exists().where(...)`), `count().select_from()` and top-level Core
  statements on `Model.__table__` (#332). **Behaviour change:** a join or count
  over a soft-deletable model now excludes trashed rows, as a plain `select`
  already did; `include_deleted=True` still reveals them.
- `HostSettings.default_tenant`: single-tenant hosts run mixin tables as one
  tenant (#359). `bind_current_tenant(fn)` carries the tenant into work a
  module defers past the request (#364). The `tenants` module resolves a
  tenant from the subdomain (`subdomain_base`), anonymous visitors included
  (#363).
- **Request-path performance** (Postgres load test,
  [docs/perf/2026-10-08-postgres-loadtest.md](docs/perf/2026-10-08-postgres-loadtest.md)).
  Route matching skips any included router whose routes cannot match the path:
  FastAPI ≥ 0.140 regex-tested nearly all ~190 routes per request, ~30% of a
  cheap request's CPU (`/health` 1.98 → 1.46 ms). The guards are built at
  startup, which also takes FastAPI's lazy per-route build off the first
  request after boot (360 → 32 ms). GZip runs at level 5 instead of 9: about
  1% larger output for 2.4× less CPU. Trivial sync FastAPI dependencies
  (`get_permission_registry`, `get_feature_flag_registry`, the `file_storage`,
  `tenants` and `users` accessors) are now `async`, so they no longer
  take a threadpool round-trip. `/admin/users` counts its status cards in one
  query instead of three.
- `SetupMiddleware` refreshes its cached verdict single-flight. When the 5 s
  TTL lapsed under load, every in-flight request ran the setup steps itself,
  each checking out a pooled connection. Behind a saturated pool those
  checkouts queued and fed `QueuePool limit … reached` timeouts. The expired
  *complete* verdict now keeps answering while one refresh runs.

### Security
- An ORM select that reads a raw `Model.__table__` (or an `aliased()` entity's
  table) only in its WHERE clause now gets the tenant filter, and strict mode
  refuses it without a tenant; such a select could read another tenant's link
  rows (#559, extends #506).
- Tenant and soft-delete filters now cover Core statements that used to leak
  other tenants' or deleted rows (#506): outer and FULL joins over
  `Model.__table__`, table aliases, subqueries, CTEs, scalar/correlated
  subqueries, `exists()` over joins or in ON clauses, `union`/`intersect`/
  `except`, tables joined into UPDATE/DELETE, and `insert().from_select()`
  sources. Raw `text()` SQL remains unfiltered by design.
- `smpy new` no longer writes generated secrets into the committed
  `.env.example` (#441). `SM_SECRET_KEY` and the users token secrets go to a
  gitignored `.env` (created if absent; an existing one only gains missing
  keys), and `.env.example` keeps `# KEY=` placeholders. Apps scaffolded
  earlier should rotate those secrets if `.env.example` was committed.
- The scaffold's `docker-compose.yml` no longer publishes Postgres on
  `0.0.0.0:5432` with `postgres`/`postgres` while the app runs in production
  mode (#444). The password comes from `POSTGRES_PASSWORD` (generated into
  `.env`; compose refuses to start without it), and Postgres and Redis bind
  `127.0.0.1` only.
- The tenant header (`tenant_header`) is no longer honoured for an
  authenticated user without a tenant of their own: such a user could name any
  tenant. On the legacy path it applies to anonymous requests only; with the
  `tenants` resolver it selects among the user's own memberships.

### Fixed
- A stored host setting that parses but fails validation (or an unrecognised
  boolean like `"tru"`) is dropped with a WARNING instead of crashing boot or
  reading as false (#497); one failing module settings read no longer resets
  that module or poisons the others' reads.
- Every `HostSettings` field `create_app` reads is marked restart-required, so
  the settings editor says so (#499).
- An established install whose setup check raises no longer drops into the
  first-run wizard.
- The admin mobile sidebar drawer closes on Escape, traps focus and is a
  labelled dialog while open (#554).
- Docs describe the real migration graph (two roots, four heads, inherited
  labels), pinned by a test (#503).
- `file_storage` browse page: a caller without `file_storage.manage` sees their
  own usage and no tenant quota, instead of the tenant-wide total; the
  authenticated download now carries the same sandbox CSP as public serving.
- Settings editor: saving a field's default (clearing an optional field
  included) removes its override row instead of storing it, so the field
  reads "default" again; a field's validation error sits on its own row below
  the control instead of wrapping beside it.
- A runtime permission source that raises is no longer cached as empty until
  invalidated: it contributes nothing for 30 seconds (one logged traceback),
  then is retried; `invalidate_source` retries it at once (#517).
- `background_tasks`: a prefork Celery child no longer reuses the sync engine
  (and Postgres connections) built in the parent (#532).
- Settings validation: `file_storage.quota_bytes` must be positive (and at most
  2^53-1), and `background_tasks.task_time_limit` must exceed
  `task_soft_time_limit` when both are set (#548). With the hard limit set by
  env, an offending stored soft limit is dropped (and logged) at boot instead
  of discarding every background_tasks override and stopping the worker.
- Settings editor: list/dict fields are edited and stored as JSON, and
  `X | None` fields as their real type with empty meaning unset (#487).
  Secrets inside such fields are stored intact, and any field declared with
  `SecretStr`/`SecretBytes` is masked on every read path whatever its name.
- Module settings classes without an `env_prefix` are no longer pinned by
  unrelated bare env vars (`HOME`, `USER`, ...) (#486).
- S3 presigned downloads keep the original filename and content type, and the
  streamed download no longer 500s on a non-Latin-1 filename (#489).
- The scaffolded `run_worker.py` hydrates DB-backed `background_tasks`
  settings like the repo's own worker, via
  `background_tasks.runner.build_runner_celery()` (#490).
- A failing verification email no longer leaves a new signup without its role
  (#488).
- The Celery worker/beat process now hydrates DB-backed `background_tasks`
  settings at boot (it used to read the environment only, so admin edits reached
  the web process but never the worker).
- `enqueue_after_commit` from a request that writes nothing else no longer loses
  the publish to a read-only rollback; a retry whose send fails after commit is
  marked `failed` instead of left `pending`; a sub-second `stuck_after` no longer
  truncates to 0; a `416` response no longer carries `Cache-Control`.
- `POST /i18n/set-locale` is mounted by `create_app` (#462), so the language
  switcher works in scaffolded apps instead of posting to a 404.
- The Register page shows field-level errors (weak password, existing
  account, invalid email) under the right field, translated, and blocks
  submit until the password meets the server's policy (#465).
- Auth screens drop the framework "python" caption once branding sets an app
  name, and only mention Keycloak SSO when Keycloak is installed (#466).
- `@simple-module-py/ui` loads `@tailwindcss/typography`, so `prose` content
  (e.g. markdown widgets) is styled in scaffolded hosts (#474).
- Scaffolded apps render the real Error page (layout, per-status copy,
  sign-in link, correlation id) instead of a bare "Something went wrong"
  (#475).
- Timezone-aware timestamp columns read back aware on SQLite (#468). Columns
  declared `sa_type=DateTime(timezone=True)` (the `AuditMixin`/`SoftDeleteMixin`
  timestamps, audit log, users, permissions, tenant invitations) came back
  naive, so the API sent them with no offset and browsers showed UTC as local
  time. New `simple_module_db.AwareDateTime` replaces that column type; it
  migrates as `sa.DateTime(timezone=True)`, so no schema change.
- Background-task Retry sends one request per execution while one is in
  flight (#467); a burst of confirm clicks no longer queues duplicate retries.
- The background-tasks list shows its plain empty state when no executions
  exist at all, instead of claiming some exist outside the search (#469).
- Deleting files another tab already deleted says so, instead of a success
  toast reading "0 files deleted" (#470).
- `smpy`'s workspace-member hint prints `./modules/...` for a module inside
  the host directory, so the suggested `smpy add` reads it as a path, not a
  PyPI name (#471).
- Scaffolded compose apps require a URL-safe `POSTGRES_PASSWORD`: compose puts
  it unencoded into `SM_DATABASE_URL`, so `make docker-up` now refuses other
  characters with a clear message (#472).
- `S3Backend.get` streams objects in 64 KiB reads instead of buffering the
  whole object in memory (#453). It is now awaited like the filesystem
  backend, which also fixes S3 thumbnails and the streamed public-file path
  (they raised `TypeError`), and a missing object answers `404`, not `500`.
- Admin task retries publish to the broker only after the new
  `TaskExecution` rows commit (#452); a rolled-back request no longer leaves a
  queued task with no execution row.
- `POST /api/users/auth/token` persists the upgraded password hash, as the
  browser login already did (#457), so bcrypt hashes imported from another
  system migrate to Argon2 on API/mobile sign-in too.
- Scaffolded apps regenerate `keys.generated.ts` in development (#449): when
  `packages/i18n/src` is absent the host writes into the installed
  `@simple-module-py/i18n` package, merging the keys it already ships.
- Scaffolded `make kill` stops only this app's ports (`API_PORT`, and
  `VITE_PORT` read from `SM_VITE_DEV_URL`) instead of `pkill`-ing every
  uvicorn and vite on the machine, vitest runs included (#461).
- `render_item` renders sqlmodel>=0.0.48's `UTCDateTime` as
  `sa.DateTime(timezone=True)` and adds `import sqlmodel` for any other
  sqlmodel type, so an initial autogenerate no longer emits a migration that
  dies with `NameError: name 'sqlmodel' is not defined` (#440).
- `smpy add <path>` for a module inside the host's uv workspace writes
  `{ workspace = true }` and an unpinned dependency instead of a path source uv
  rejects (#442). A relative path missing under `--path` falls back to the cwd,
  and `smpy create-module` inside a workspace prints the `smpy add` command.
- Scaffold hygiene (#443): templates name the `smpy` CLI (not `sm`), `uv.lock`
  is committed rather than gitignored, and the Postgres database name is
  snake_case (`demo_app`, not `demo-app`).
- Scaffolded dev groups floor `playwright>=1.45`; without it uv resolved
  playwright 1.18 and every `pytest` run failed at plugin load (#445).
- `/admin/background-tasks` returned 500 on Postgres (#413): `TaskExecution`'s
  timestamps were declared naive although the columns are `timestamptz` since
  `e5f2a8c1d7b3`. This was already fixed on `main` by #406 (unreleased since
  v0.0.35); this branch only pins it with tests. No migration.
- Sign-in aside footer text met only 2.7:1 contrast; `--color-dark-text-subtle`
  is lighter and clears WCAG AA (#414).
- Only top-level navigations record the post-login target (#416): a favicon,
  script, image or `fetch()` hitting an unauthenticated route no longer
  overwrites it. Navigations and Inertia visits record the target as before;
  requests that carry no fetch metadata keep the old behaviour.
- The tenant filter no longer turns an outer join into an inner join when the
  joined table is only referenced inside a function such as
  `func.count(Child.id)` (#417), whether it joins the entity or a relationship
  path (`.outerjoin(Parent.children)`, with or without `of_type`). A raw-table
  target or a `secondary` relationship stays filtered in `WHERE`, so this never
  leaks another tenant's rows.
- `attach_session_listeners` (simple_module_db) now marks each session class it
  wires instead of asking SQLAlchemy's `event.contains`, which keys on `id()`.
  A new session class that reused the id of a garbage-collected one was treated
  as already wired and got no tenant filter, soft-delete filter or write
  markers, so tenant isolation failed open. A single-app worker process was not
  affected; any process that builds more than one app or DatabaseState and
  drops an earlier one was (the test suite, scripts, embedders).
- `gen-pages` emits `@source` lines for subdirectories of wheel modules (#419);
  uv's `.venv/.gitignore` made Tailwind skip them, so their utility classes
  were missing from the built CSS.
- Brand foreground ink follows the brand colour (#420): `deriveBrandRamp` sets
  `--primary-foreground` and `--sidebar-primary-foreground` by WCAG contrast
  (white or dark ink), so buttons and the active sidebar row stay legible on a
  light brand colour; the logo badge initial stays white on the ramp gradient.
- Admin screens (#422): `/admin/users/` has a document title, `/admin/settings/`
  has a visible `<h1>`, and error pages under `/admin` for a signed-in admin
  render inside the admin shell.
- `TenantMiddleware` merges every `Vary` response line and leaves a `Vary: *`
  response untouched (#423), and `tenant_source` is `None` whenever no tenant is
  bound (#424).
- Public pages no longer reload the whole document when a visitor clicks a link
  in authored content. A simple_module app is client-rendered — the root
  template ships `<div id="app"></div>` empty — so a navigation that creates a
  new document paints a blank white body until the bundle has booted. Admin
  screens were never affected because the shell navigates with Inertia's
  `<Link>`, but pagebuilder widgets and their markdown/rich-text fields render
  author-entered URLs as plain `<a href>`, and there is no component to swap for
  a `<Link>` when the anchor comes out of a markdown parser. A downstream site
  measured ~330ms of blank viewport per click on a throttled connection.
  `@simple-module-py/ui` now exports `startSpaLinkInterception()`, a delegated
  click handler that routes same-origin page links through Inertia whatever
  produced the anchor; the `smpy new` app template calls it. It deliberately
  leaves alone anything Inertia cannot render — other origins, non-http schemes,
  paths that look like a file, in-page anchors, `download`/`target`/
  `rel="external"`/`data-native-link`, and anchors inside a Puck editor surface
  — and falls back to a hard navigation if a visit returns without an
  `x-inertia` header, so a media download can never be replaced by an error
  modal. **Existing apps must add the one-line call to their own
  `host/client_app/app.tsx`**, which is scaffold output and so is not upgraded
  for them.
- `smpy gen-pages` now emits module stylesheet `@import` lines as **absolute
  paths** instead of `#module/<pkg>` alias specifiers. The alias only resolved
  if the host's `vite.config.ts` defined a matching `resolve.alias` — but that
  file is scaffold output, written into an app once and then owned and edited
  there, so it is versioned independently of these Python packages. Upgrading
  `simple_module_*` 0.0.26 → 0.0.27 therefore broke `vite build` in every app
  scaffolded earlier, failing with `Can't resolve '#module/<pkg>/styles.css'` —
  naming a specifier that appears nowhere in the app's own sources.

  `modules.generated.css` is now self-contained: it resolves under any
  `vite.config.ts`, with no alias configured at all, exactly as the `@source`
  lines in the same file already did. **No host action is required** — upgrade
  and re-run `gen-pages`. The scaffold template still defines the
  `#module/<pkg>` alias for hand-written imports, but nothing generated depends
  on it any more (GH issue #253).

### Added
- A module can now import another module's TS/TSX by npm package name:
  `import x from '@simple-module-py/pagebuilder/components/blockRegistry'`.
  Nothing in Node's own resolution made this work — a wheel-installed module is
  not an npm workspace member, so it never lands in `node_modules` at all;
  a workspace member *is* symlinked, but onto the source-tree module root, one
  level above the Python package, so subpaths landed somewhere nonexistent.

  `gen-pages` now records each module's `npm_name` in `modules.assets.json`,
  and the host aliases it onto the module's **Python package directory**. That
  anchor is forced, not chosen: a wheel ships `site-packages/<pkg>/**` and
  nothing above it, so the module root does not survive installation and the
  package directory is the only anchor both layouts share. The practical
  consequence is that the subpath is relative to the *package*:

  ```tsx
  import x from '@simple-module-py/foo/components/Widget';      // ✅ both layouts
  import x from '@simple-module-py/foo/foo/components/Widget';  // ❌ workspace-only
  ```

  If you previously hand-rolled this alias against the module root, drop the
  duplicated path segment. **Existing hosts need a `vite.config.ts` change** —
  unlike the CSS fix above, the import lives in module source rather than a
  generated file, so it cannot be made self-contained. In the loop over
  `modules.assets.json` entries, add:

  ```ts
  if (entry.npm_name) {
    moduleAliases.push({ find: entry.npm_name, replacement: entry.package });
  }
  ```

  and skip those names when collecting `optimizeDeps.include` — they resolve to
  source directories, not to pre-bundlable packages (GH issue #253).

## [0.0.27] — 2026-08-06

### Known issue
- Fixed in the `[Unreleased]` entry above. `gen-pages` emitted
  `@import "#module/<pkg>/…"` into `modules.generated.css`, which resolves only
  in hosts scaffolded at 0.0.27 or later; apps scaffolded earlier fail
  `vite build` after a Python-only upgrade. Either upgrade past this release,
  or add the alias to `host/client_app/vite.config.ts` by hand — build
  `{ find: '#module/' + package_name, replacement: package }` from each entry
  in `client_app/modules.assets.json` and pass the list as `resolve.alias`
  (GH issue #253).

## [0.0.16] — 2026-05-25

### Fixed
- The `users` module's post-login redirect (`login_redirect_url`) no longer
  hard-codes a `/` fallback when the Dashboard module isn't installed — `/`
  404s on apps without a root route (e.g. `smpy_gis`, `--preset minimal`). It
  now redirects to the first sibling module that exposes view routes, falling
  back to `/` only as an absolute last resort. Operator-set overrides are
  always preserved (GH issue #173).

## [0.0.15] — 2026-05-21

### Fixed
- The `moduleBareImportResolver` Vite plugin no longer short-circuits on
  `fsRoot`/`projectRoot` containment, so workspace-member modules at
  `modules/<name>/<pkg>/pages/` get the same workspace-root re-resolution as
  wheel-installed modules. In an npm-workspaces layout the workspace root *is*
  the resolver root, so the previous early-return excluded the very modules
  that need it. Cross-package bare imports (`maplibre-gl`, `pmtiles`, peer
  deps) now resolve in both wheel and workspace install modes (GH issue #156).
- The framework repo (Vite 8) seeds
  `optimizeDeps.rolldownOptions.resolve.modules` with the workspace
  `node_modules/` as a NODE_PATH-style fallback for the dep scanner
  (GH issue #155).

## [0.0.13] — 2026-05-15

### Fixed
- Vite's dev-mode dependency pre-bundling now resolves cross-package bare
  imports (e.g. `maplibre-gl`, `pmtiles`) from module pages whose importers sit
  outside the host's `client_app/`. The scaffold template (Vite 6) seeds
  `optimizeDeps.esbuildOptions.nodePaths` with the workspace `node_modules/`
  as a NODE_PATH-style fallback for the dep scanner (GH issue #152).

## [0.0.1] — 2026-04-21

Initial public release. All 12 Python packages publish to PyPI and all 3 JS packages publish to npm under the `@simple-module-py` scope.

### Python packages (PyPI)

- `simple_module_core`
- `simple_module_db`
- `simple_module_hosting`
- `simple_module_test`
- `simple_module_auth`
- `simple_module_background_tasks`
- `simple_module_dashboard`
- `simple_module_feature_flags`
- `simple_module_file_storage`
- `simple_module_permissions`
- `simple_module_settings`
- `simple_module_users`

### npm packages

- `@simple-module-py/ui`
- `@simple-module-py/i18n`
- `@simple-module-py/tsconfig`

### Added

- `smpy new <app>` CLI generator (shipped via the `simple_module_cli` PyPI distribution) scaffolding a working app with `users + dashboard + permissions` pre-wired.
- PyPI Trusted Publishing workflow (`.github/workflows/release.yml`) for zero-secret releases.
- npm Trusted Publishing for all three JS packages.

[Unreleased]: https://github.com/antosubash/simple_module_python/compare/v0.0.41...HEAD
[0.0.41]: https://github.com/antosubash/simple_module_python/compare/v0.0.40...v0.0.41
[0.0.40]: https://github.com/antosubash/simple_module_python/compare/v0.0.39...v0.0.40
[0.0.39]: https://github.com/antosubash/simple_module_python/compare/v0.0.38...v0.0.39
[0.0.38]: https://github.com/antosubash/simple_module_python/compare/v0.0.37...v0.0.38
[0.0.27]: https://github.com/antosubash/simple_module_python/compare/v0.0.26...v0.0.27
[0.0.16]: https://github.com/antosubash/simple_module_python/compare/v0.0.15...v0.0.16
[0.0.15]: https://github.com/antosubash/simple_module_python/compare/v0.0.14...v0.0.15
[0.0.13]: https://github.com/antosubash/simple_module_python/compare/v0.0.12...v0.0.13
[0.0.1]: https://github.com/antosubash/simple_module_python/releases/tag/v0.0.1
