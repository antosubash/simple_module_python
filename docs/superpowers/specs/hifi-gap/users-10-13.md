# Hi-Fi deck gap analysis — users-10-13

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

# Design-vs-implementation gap analysis — Users / Add people / Edit user / Profile

All repo paths below are under `/home/anto/Repos/simple_module_python/`; the users module root is `/home/anto/Repos/simple_module_python/modules/users/users/`. Deck copy is quoted verbatim. No files were modified.

Two cross-cutting findings that affect several screens:

- **Relative time.** The deck uses "2h ago / 3d ago / 1mo ago" everywhere. `packages/ui/src/lib/relative-time.ts` (`relativeAge`) only buckets up to hours (`ui.relative_time.{just_now,seconds_ago,minutes_ago,hours_ago}` in `packages/ui/locales/en.json`); it needs `days_ago`/`months_ago` buckets + keys.
- **Auth resolution is session-cookie based, not DB-token based.** `modules/users/users/provider.py:28-57` authenticates browser requests from Starlette's signed session (`session[SESSION_USER_ID_KEY]`, with a cached `UserContext`), not from `users_access_token`. This determines what "Sessions" / "Sign out everywhere" can actually do (see Profile §5).

---

## 10 — Users list (`/tmp/hifi/screens/10-users.html`)

### 1. Route + files
- `GET /admin/users/` → `modules/users/users/admin/views.py::admin_index` → Inertia `Users/Users/Index`
- Page: `modules/users/users/pages/Users/Index.tsx`; sub-components `modules/users/users/admin/components/{IndexFilters,RolesTab,UserRow,UsersEmpty}.tsx`, `modules/users/users/pages/Users/components/UserStats.tsx`
- Data: `modules/users/users/admin/queries.py` (`list_users`, `count_user_states`, `list_roles`), DTO `UserListItem` in `modules/users/users/contracts/schemas.py:118-128`
- Copy: `modules/users/users/locales/en.json` → `index.*`, `filters.*`, `user_row.*`, `empty.*`

### 2. Design structure
1. Header: h1 **"Users"**, sub **"People with access to this workspace"**; right: primary button **"+ Add people"**.
2. Four flat stat cards (label over big number, no icon, no delta badge): **"Members"** 128 · **"Active"** 119 · **"Pending invites"** 6 (number in amber `#b45309`) · **"Roles"** 4.
3. Toolbar (one row): segmented control **"Users 128"** / **"Roles 4"**; search (flex-fills) placeholder **"Search by name or email…"**; two dropdown buttons **"Status: all ▾"**, **"Role: all ▾"**.
4. Table card, columns (grid `2.2fr 1fr 1fr 1fr 44px`): **"Member ↑"**, **"Role"**, **"Status"**, **"Last seen"**, blank actions column.
   - Rows: 32px round avatar with two-letter initials ("DR"), name bold + email muted; role as plain muted text; status pill **"active"** (green soft), **"unverified"** (amber), **"disabled"** (grey, whole row `opacity:.62`), **"invited"** (amber, row tinted `rgba(180,83,9,.05)`, dashed-circle **"✉"** avatar, primary line is the email, secondary **"invited 2d ago · expires in 5d"**, action cell shows **"Resend"** instead of the kebab). Last seen: **"2h ago"**, **"—"**, **"3d ago"**, **"1mo ago"**. Action cell **"⋯"**. Rows have `cursor:pointer` + hover bg.
5. Card footer: **"Showing 1–20 of 128"** left; **"Previous"** / **"Next"** outline buttons right. Always shown.

### 3. Already matches
Title; "Add people" CTA; four stat labels; Users/Roles tabs with counts; identical search placeholder; Status + Role filters; column set and sort arrow on Member; active/invited/disabled pills; Previous/Next; "Pending invites" = active && !verified (`count_user_states`).

### 4. Deltas
1. **Description copy** — impl `index.description` = "People with access to this workspace. Invites use the configured mailer." → deck drops the second sentence. `en.json`.
2. **Stat cards** — `UserStats.tsx` uses `StatCard` (icon + "review"/"all set" delta badge); deck is plain label+number with the pending number amber. Either a `plain` variant on `packages/ui/src/components/StatCard.tsx` or a local card in `UserStats.tsx`.
3. **Tabs** — deck is a segmented pill with the count inline ("Users 128"); impl is shadcn `Tabs` with lucide icon + `Badge`. `Index.tsx`.
4. **Filters** — deck has only Status and Role, rendered as label-prefixed buttons ("Status: all ▾"); impl `IndexFilters.tsx` has three `Select`s (Status/Role/**Verified**) with "All statuses"/"All roles"/"All". Drop or fold Verified; change trigger text. `IndexFilters.tsx` + `filters.*` keys.
5. **Search width** — deck flex-fills between tabs and filters; impl `max-w-sm`. `Index.tsx`.
6. **Avatar** — deck two-letter initials on soft-primary/grey bg; impl `UserRow.tsx` `Avatar` is one letter on a primary gradient.
7. **"unverified" vs "invited"** — impl `StatusBadge` maps every `is_active && !is_verified` to "invited"; deck shows "unverified" (Sam, has a name) and "invited" (rob, no name) as distinct states. `UserRow.tsx` + backend (§5).
8. **Invited-row treatment** — tinted row, dashed ✉ avatar, email as primary line, "invited 2d ago · expires in 5d", **"Resend"** action. None exists. `UserRow.tsx` + backend.
9. **Disabled row dimming** — deck dims the whole row; impl only greys the badge. `UserRow.tsx`.
10. **Last seen** — impl `new Date(...).toLocaleDateString()`; deck relative. `UserRow.tsx` + extend `relative-time.ts`.
11. **Row action** — deck "⋯" kebab (implies a menu) and whole row clickable; impl a pencil `Link` only. `UserRow.tsx`.
12. **Pagination** — deck: inside the card footer, "Showing 1–20 of 128" + buttons, always visible; impl: centered below the card, "Page {page} of {total}", hidden when one page. `Index.tsx` + new `index.showing_range` key.
13. Impl-only, absent from deck (keep): SSO badge, `SoloAccountPrompt`, filtered/empty `UsersEmptyRow`.

### 5. Backend / props / DB needed
- **Invited vs unverified**: no column distinguishes them. `service.invite()` (`admin/service.py:125-161`) creates `is_verified=False` with a random password — identical shape to a self-signup. A `UserInvited` event exists (`contracts/events.py:18`) but nothing persists it on the user. Needs `invited_at` (+ optionally `invited_by`) on `models/user.py`, `UserListItem`, `queries.py::list_users` select, and a migration under `host/migrations/versions/`.
- **"expires in 5d"**: invite = fastapi-users verification JWT; lifetime `verification_token_lifetime_seconds` = 7d (`modules/users/users/settings.py:51`); not stored. Derive `invited_at + lifetime` once `invited_at` exists.
- **Resend**: no admin endpoint. Only self-service `POST /api/users/auth/request-verify-token` (used by `pages/Login.tsx:82`). Needs `POST /api/users/admin/{id}/resend-invite` in `admin/api.py` reusing `manager.generate_verification_token` + `mailer.send_invite` with the console-mailer link fallback from `admin/bulk_invite.py::_invite_link`.
- Pending-invites count (`count_user_states`) should then key off `invited_at`.
- `last_login_at` exists and is populated (`manager.py:137`). "Showing X–Y of N" is derivable from the existing `pagination` prop.

### 6. Ambiguities
- Kebab menu contents (edit / disable / resend / copy reset link?).
- Whether the Verified filter is removed or merged into Status (`all/active/unverified/invited/disabled`).
- Whether "Roles 4" still shows the role-card grid (`RolesTab.tsx`); deck never shows it.
- Whether clicking an invited row opens the edit page.
- Whether "Resend" should be offered for self-registered "unverified" users too.

---

## 11 — Add people (`/tmp/hifi/screens/11-addpeople.html`)

### 1. Route + files
- `GET /admin/users/add[?mode=create]` → `admin/views.py::admin_add_people_page` (props `roles`, `mailer_delivers`); `/invite` and `/create` 307 here.
- Page: `modules/users/users/pages/Users/AddPeople.tsx`; components `pages/Users/components/{InviteFields,CreateUserFields,RolePicker,InviteResults}.tsx`
- APIs: `POST /api/users/admin/invite/bulk` (`modules/users/users/admin/bulk_invite.py`), `POST /api/users/admin` (`admin/api.py::admin_create_user`)
- Copy: `en.json` → `add_people.*`, `invite_fields.*`, `create_fields.*`, `invite_results.*`, `role_picker.*`

### 2. Design structure
1. h1 **"Add people"**; sub **"Invite by email, or create an account directly with a password you set."**
2. Standalone segmented control: **"Invite by email"** (active) / **"Create account"**.
3. Full-width amber banner: **"⚠ Mailer is *console* — invite links are printed to the server log instead of emailed. Each result row below carries a copy-link button."** + underlined link **"Configure SMTP"**.
4. Grid `1.25fr 1fr`:
   - Left card: label **"Email addresses"**; chip input (min-height 96px) with chips **"rob@example.com ✕"**, **"nia@example.com ✕"** (green) and **"not-an-email ✕"** (red); placeholder **"Paste a list, or type and press Enter…"**; helper **"3 addresses · 1 invalid"**. Then **"Roles for everyone in this batch"** with pills **"editor ✓"**, "admin", "viewer". Then **"Message (optional)"** textarea placeholder **"Added to the invite email."** Footer right: **"Cancel"**, primary **"Send 2 invites"** (count excludes the invalid chip).
   - Right card **"Last batch"** with header meta **"2 sent · 1 failed"**; rows **"✓ dana@example.com — Copy link"**, **"✓ lee@example.com — Copy link"**, **"✕ ana@example.com — Retry"** with red sub-line **"Already a member of this workspace"** (row tinted red). Footer note **"Invites expire after 7 days. Pending invites appear in the Users table with a Resend action."**
5. "Create account" mode is not depicted.

### 3. Already matches
Title; invite/create mode switch (`role="tablist"`); role chips; "Cancel" + "Send {count} invites" with CLDR plural; console-mailer warning concept (`invite_fields.no_mailer`); per-address results with copy-link (`InviteResults.tsx` + `CopyableId`); "Already registered" failure detail; create-mode fields (email, full name, password + hint).

### 4. Deltas
1. **Description** — impl "Invite them to set their own password, or create the account yourself." → deck copy. `en.json add_people.description`.
2. **Mode labels/placement** — impl "Send invites" → deck "Invite by email"; toggle sits inside the card in impl, standalone above in deck. `add_people.mode_invite`, `AddPeople.tsx`.
3. **Mailer banner** — impl: small amber `<p>` inside `InviteFields.tsx` ("This deployment logs invite mail instead of sending it…"); deck: page-level banner naming the mailer + "Configure SMTP" link. Use `packages/ui/src/components/InlineBanner.tsx` (`tone="warning"`) in `AddPeople.tsx`; link to `/admin/settings/` (module settings now render at the section root — `modules/settings/settings/endpoints/views.py:187-207`; `/admin/settings/modules` 308-redirects there). New keys.
4. **Email input** — deck is a chip/tag input with Enter-to-add, paste-split, per-chip validity colouring and an "N addresses · M invalid" counter; impl is a monospace `Textarea` + "One per line, or separated by commas. {count} recognised." New `EmailChipInput.tsx` under `pages/Users/components/`, client-side format check, submit count = valid chips. `InviteFields.tsx`, `invite_fields.*`.
5. **Roles label** — deck "Roles for everyone in this batch"; impl `RolePicker` default "Roles". Pass `label` in `AddPeople.tsx` (invite mode) + key.
6. **"Message (optional)"** — absent. Frontend `InviteFields.tsx`; backend §5.
7. **Layout** — deck two-column with a persistent right "Last batch" card; impl single `max-w-2xl` card, results appended below the form after submit, and `router.visit('/admin/users/')` when everything sent (`AddPeople.tsx:92-95`) so the all-sent batch is never shown. `AddPeople.tsx`, `InviteResults.tsx` (card, header "Last batch", meta "{sent} sent · {failed} failed").
8. **Result rows** — deck has ✓/✕ glyph rows with **"Copy link"** / **"Retry"**; impl groups by status, shows links only for status `link` (intentional: no live token on screen when mail delivered — see `InviteResults.tsx` docstring; in the console-mailer case every row *is* `link`, so this coincides with the deck). "Retry" is missing. Impl-only "Dismiss", "Copy all", "All invites delivered." — keep or drop.
9. **Failure copy** — server string "Already registered" (`bulk_invite.py:56`) vs deck "Already a member of this workspace"; note it is an untranslated server literal.
10. **Footer note** about 7-day expiry — missing; needs the TTL as a prop.
11. Impl "Back to Users" header action — not in deck.

### 5. Backend / props / DB needed
- `message` — nothing exists (`UserBulkInvite` = `emails`, `role_names`; `contracts/schemas.py:67-82`). Add to schema, thread through `bulk_invite.py`, extend `Mailer.send_invite(email, token, invited_by_name)` in `mailer/__init__.py:26`, `mailer/console.py:42`, `mailer/smtp.py:68` + template under `mailer/templates/`.
- Mailer name for the banner — `settings.mailer` (`"console"|"smtp"`, `settings.py:64`) exists but only `mailer_delivers: bool` is passed (`admin/views.py:123`).
- Invite TTL — `settings.py:51`; not passed.
- Retry — reuse the bulk endpoint with one address; no backend change.

### 6. Ambiguities
- Do invalid chips block submit or just get excluded (deck implies excluded: "Send 2 invites" with 3 chips).
- Does "Last batch" persist across reload (needs storage) or is it in-memory only; what it shows before any submit.
- Keep or drop the redirect-to-list on full success.
- "Retry" on "Already a member" will fail again — is Retry only for transient failures (status `link`/mailer error)?
- Create-account mode: what occupies the right column.

---

## 12 — Edit user (`/tmp/hifi/screens/12-edituser.html`)

### 1. Route + files
- `GET /admin/users/{user_id}` → `admin/views.py::admin_edit_page` (props `user: UserListItem`, `roles`, `has_permissions_module`; `auth` shared).
- Page: `modules/users/users/pages/Users/Edit.tsx`; components `pages/Users/components/{DetailsCard,RolesCard,RolePicker,MetadataCard,AccountStatusCard,DangerZone}.tsx`, `useUserActions.ts`
- APIs (`admin/api.py`): `PATCH /{id}`, `PUT /{id}/roles`, `PATCH /{id}/disable|enable|verify`, `POST /{id}/reset-password-link`, `DELETE /{id}`
- Copy: `en.json` → `edit.*`, `details_card.*`, `roles_card.*`, `metadata_card.*`, `account_status.*`, `danger_zone.*`

### 2. Design structure
1. Header: 52px avatar **"DR"**; h1 **"Dana Rivera"**; sub **"dana@example.com · joined Mar 2026 · last login 2h ago"**; pill **"active"** beside the name. Right: **"3 unsaved changes"** (muted), **"Discard"** (outline), **"Save changes"** (primary). No "Back" button.
2. Grid `1.3fr 1fr`, two rows:
   - **"Details"** (left, top): **"Full name"** input, **"Email"** input (shown focused), then **"Roles"** label with pills **"admin ✓"**, "editor", "viewer" and right-aligned link **"Manage permissions →"**.
   - **"Account"** (right, top): key/value rows **"Sign-in"** → mono pill **"local · password"**; **"Created"** → **"12 Mar 2026"**; **"Verified"** → **"yes"** (green text); **"Disabled at"** → **"—"**; bottom buttons **"Disable account"**, **"Copy reset link"** (both outline).
   - **"Recent activity"** (left, bottom): mono timestamps + text: **"14:02:11 Changed `is_active` on sam@example.com"**, **"13:47:02 Updated setting `users.smtp_host`"**, **"09:03:40 Invited rob@example.com"**; link **"See all in the audit log →"**.
   - **"Danger zone"** (right, bottom; red border, red-tinted bg, red heading): **"Deleting removes the account and its sessions. Audit entries are kept. Blocked when editing your own account."**; outline-red button **"Delete user"**.

### 3. Already matches
One dirty state with Discard / Save changes and leave-guard; Full name + Email inputs; role chips; "Manage permissions →" (gated on permissions module); Sign-in / Created / Verified / Disabled at rows; "Disable account" + "Copy reset link" with confirm dialogs; Danger zone with typed-email confirm; self-delete blocked (`danger_zone.self_note`).

### 4. Deltas
1. **Header** — impl `PageShell title={user.email} description={full_name}`; deck title = name, avatar, sub "email · joined {Mon YYYY} · last login {relative}", status pill. `Edit.tsx` (custom header block; `PageShell.tsx` has no leading/badge slot) + `edit.subtitle` key + relative time.
2. **"3 unsaved changes"** — impl `edit.unsaved_changes` = "Unsaved changes" (no count). Count changed fields (email, fullName, roles) in `Edit.tsx`; plural keys.
3. **"Back to Users"** action in impl header — not in deck.
4. **Roles inside Details** — impl separate `RolesCard.tsx` (`lg:col-span-2`); deck folds roles + manage link into "Details". Merge into `DetailsCard.tsx`; also field order (deck Full name first; impl Email first).
5. **One "Account" card** — impl splits into `MetadataCard.tsx` ("Metadata": Sign-in/Created/Last login/Disabled at/Verified + "Mark verified") and `AccountStatusCard.tsx` ("Account status": pill + Disable/Enable/Copy reset link). Merge into one `AccountCard.tsx`, title "Account"; keep impl-only "Mark verified", "Enable account", SSO `external_note`.
6. **Sign-in value** — impl badge "Local · password" (`metadata_card.local_badge`); deck lowercase mono pill "local · password".
7. **Date format** — impl `toLocaleString()` (date+time); deck "12 Mar 2026". `MetadataCard.tsx::fmt`.
8. **"Last login"** row moves from the card to the header.
9. **Verified "yes"** — plain green text in deck; impl `Badge`.
10. **"Recent activity" card** — missing entirely. New `RecentActivityCard.tsx`; link `/admin/audit-log/?user_id={id}` (browse view accepts `user_id`, `modules/audit_log/audit_log/endpoints/views.py:50`).
11. **Danger zone copy/style** — impl description "Permanently delete this user. This cannot be undone."; deck copy above. Impl card `border-destructive/40`, default-colour heading, filled destructive button; deck red-tinted bg, red heading, outline-red button. `DangerZone.tsx`, `danger_zone.description`.
12. **Grid** — deck `1.3fr 1fr` fixed two rows; impl `lg:grid-cols-2` with three cards spanning both columns. `Edit.tsx`.
13. Status pill in header (deck) currently lives in `AccountStatusCard.tsx`.

### 5. Backend / props / DB needed
- **`recent_activity` prop** — data exists: `modules/audit_log/audit_log/models.py::AuditEntry` (`entity_type, entity_id, action, changes, user_id, created_at`) and `AuditLogService.list_entries(user_id=…, page_size=…)` (`service.py:57`). Human summaries ("Changed `is_active` on sam@…") need `changes` + entity resolution; helpers `resolve_actors`/`entity_link` live in `modules/audit_log/audit_log/resolve.py`. Users must not hard-depend on audit_log (it already gates `has_permissions_module` by name, `admin/views.py:167`) — resolve via `app.state`/importlib and hide the card when absent. Deck rows are things Dana *did* → filter by actor `user_id`; "about this user" would be `entity_type="User", entity_id=…`.
- Header "joined": `created_at` (AuditMixin) already in `UserListItem`. `last_login_at` present.
- No other new data.

### 6. Ambiguities
- Activity by actor vs about the entity; row count; timestamp format (deck shows `HH:MM:SS` only — needs a date for older entries).
- Whether the header pill updates immediately after Disable (it should, via `useUserActions`).
- Where "Mark verified" / "Enable account" / SSO variants go in the merged card.
- Whether the hidden "Delete user" for self remains (deck text implies a disabled button).

---

## 13 — Your profile (`/tmp/hifi/screens/13-profile.html`)

### 1. Route + files
- `GET /users/me` → `modules/users/users/auth_local/views.py:124-126::profile_page` — renders `Users/Profile` with **empty props `{}`**.
- Page: `modules/users/users/pages/Profile.tsx` (`AuthenticatedLayout`, not `AdminLayout`).
- API: `GET/PATCH /api/users/me` (`auth_local/api.py:183-200`; `SelfProfileUpdate` = `full_name` only, `contracts/schemas.py:152`).
- Copy: `en.json` → `profile.*`, `common.*`

### 2. Design structure
1. h1 **"Your profile"**; sub **"Name, email, password and active sessions"**.
2. Grid `1.2fr 1fr`:
   - Left, **"Details"**: 56px avatar **"AD"**; beside it **"admin@example.com"** + helper **"Avatars come from the branding logo — no per-user upload."**; fields **"Full name"** ("Alex Doyle"), **"Email"** ("admin@example.com"); right-aligned primary **"Save details"**.
   - Left, **"Password"**: three fields **"Current"**, **"New"**, **"Confirm"**; strength bar (72% green) + **"At least 8 characters, not all numbers"**; right-aligned outline **"Change password"**.
   - Right, **"Sessions"**: green-dot row **"This browser · Chrome on macOS"** / **"Signed in 2h ago · 10.0.0.14"**; grey-dot row **"Firefox on Linux"** / **"Signed in 3d ago"** + link **"Revoke"**; red link **"Sign out everywhere"**.
   - Right, **"Preferences"**: **"Language"** → **"English ▾"**; **"Theme"** → **"System ▾"**; **"Task failure emails"** → toggle (on).

### 3. Already matches
Title "Your profile"; a card with avatar initial, editable name, email, save button.

### 4. Deltas
1. **Description** — impl "Shown to teammates in audit logs and dropdowns." → deck copy. `profile.description`.
2. **Section/labels** — impl "Account" / "Display name" / "Save changes" → deck "Details" / "Full name" / "Save details". `profile.*`, `Profile.tsx`.
3. **Avatar block** — impl has a dead **"Upload avatar"** button + "PNG or JPG, up to 2MB." (no handler, no avatar column anywhere); deck explicitly says no per-user upload and shows the email beside the avatar. Remove; two-letter initials.
4. **Email** — impl `readOnly` + verified/unverified badge; deck plain editable-looking input, no badge (see §6).
5. **Roles badges** — impl-only; not in deck.
6. **"Password" card** — missing. Needs UI + backend (§5). Hint text matches the existing policy string in `create_fields.password_hint`. Hide for `is_external` users (no local password — `AccountStatusCard.tsx` already models this).
7. **"Sessions" card** — missing (§5).
8. **"Preferences" card** — missing (§5).
9. **Layout** — single `max-w-2xl` card → two-column grid. Sub-components: follow the `admin/components/` precedent, e.g. `modules/users/users/auth_local/components/{PasswordCard,SessionsCard,PreferencesCard}.tsx` (the Vite glob is `pages/**/*.tsx`, `manifest.py:229`, so keep non-pages out of `pages/`).
10. **Bug (pre-existing):** `Profile.tsx:33,62,100` reads `auth.user.full_name` and `auth.user.is_verified`, but `auth.user` is `{id, name, email, roles}` (`modules/auth/auth/module.py:28-34`; `UserContext` has no such fields, `modules/auth/auth/contracts/schemas.py:15-22`). The name field always loads empty and the badge always reads "unverified". Fix by having `profile_page` pass a `user` prop (`UserRead` shape) instead of `{}`.

### 5. Backend / props / DB needed
- **Profile prop** — `auth_local/views.py::profile_page` must load the current user (`UserRead`: has `full_name`, `is_verified`, `is_external`, `last_login_at`).
- **Change password** — no endpoint. fastapi-users' `get_users_router` is not mounted (only reset/verify/register, `module.py:185-205`); `update_me` accepts `full_name` only. Add `POST /api/users/me/password {current_password, new_password}` verifying the current hash and applying `UserUpdate(password=…)` via `UserManager` (policy already enforced there); refuse for `is_external`.
- **Sessions** — the closest data is `users_access_token` (`models/access_token.py`: `token`, `created_at`, `user_id`; written by the `DatabaseStrategy` on login), but browser auth is resolved from the **Starlette signed session**, not that table (`provider.py:33-57`). So listing/revoking token rows would not sign anyone out. A real implementation needs either a server-side session store or a per-user `session_version`/per-session id stored in the session dict and checked in `resolve_user`, plus `user_agent`/`ip`/`last_seen_at` columns and a surrogate id (the raw token must never be sent to the client). Endpoints: `GET /api/users/me/sessions`, `DELETE /api/users/me/sessions/{id}`, `POST /api/users/me/sessions/revoke-all`; "everywhere" should also revoke `users_refresh_token` rows (`revoked_at` exists, `models/refresh_token.py`). Migration required.
- **Language** — cookie-based only (`framework/hosting/simple_module_hosting/i18n_middleware.py`, `POST /i18n/set-locale`, `packages/ui/src/components/LocaleSwitcher.tsx`); a select can reuse that form; no per-user persistence.
- **Theme** — no `ThemeProvider`/`next-themes` provider in `host/client_app` or `packages/ui/src/layouts`; no `dark` variant in `host/client_app/styles.css` (only `sonner.tsx` calls `useTheme`). "System ▾" requires dark-mode plumbing that does not exist.
- **Task failure emails** — nothing (no notification setting in `modules/background_tasks`). Would need a user-scoped setting (the settings module already has a user scope: `API_USER_PATH = /user/{scope_id}/{key}`, `modules/settings/settings/constants.py:62`) plus a `TaskFailed` handler that emails via the users mailer.

### 6. Ambiguities
- Is email editable (implies re-verification + `SelfProfileUpdate.email`), or read-only as today?
- Keep roles badges / verified badge?
- Language select vs the existing topbar `LocaleSwitcher`; Theme without dark-mode support.
- "Task failure emails": all failures, or only tasks the user triggered?
- Strength-meter algorithm; whether Password/Sessions cards apply to SSO/bearer sessions.
- Deck shows Profile inside the admin shell with "Users" highlighted; impl uses `AuthenticatedLayout` (shell out of scope, but the layout choice differs).

---

## Overall summary (largest gap first)

1. **Profile (13)** — three of four cards don't exist (Password, Sessions, Preferences); each needs new backend (password endpoint, real session tracking incompatible with today's session-cookie auth, theme plumbing, a notification setting), plus a live prop bug that blanks the name and mis-reports verification.
2. **Edit user (12)** — "Recent activity" card and header (name/avatar/joined/last-login/status) are new; the rest is restructuring (merge Roles into Details, merge Metadata+Account status) and copy/date formatting, with audit data already available.
3. **Add people (11)** — chip email input, "Message (optional)" (new field through schema → mailer → template), persistent two-column "Last batch" panel with Retry, page-level mailer banner with settings link, and expiry note; core invite flow already works.
4. **Users list (10)** — mostly styling/copy (flat stats, segmented tabs, relative "Last seen", in-card pagination, row dimming) plus one real feature: distinguishing invited from unverified and a "Resend" action, which needs an `invited_at` column and an admin resend endpoint.
5. Shared prerequisites: extend `relative-time.ts` to days/months, a plain `StatCard` variant, and a `PageShell` header slot for avatar/badge.