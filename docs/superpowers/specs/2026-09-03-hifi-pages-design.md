# Hi-Fi Pages — implementing every screen of the deck

**Date:** 2026-09-03
**Source:** Claude Design project `4ad8fe06-c68f-4444-bcf7-0d0b4839e681`, file `Hi-Fi Pages.dc.html` (+ `support.js`). The copy used here was cached on 2026-08-19; the live project could not be re-fetched in this session (Claude Design MCP not authorised), so any edits made to the deck after that date are not reflected.
**Baseline:** `origin/main` @ 3f64f3c, branch `worktree-hifi-pages`.
**Gap analysis:** per-screen findings live in [`hifi-gap/`](hifi-gap/). This document records the decisions; the gap files hold the evidence.

## Goal

Make every one of the deck's 28 screens (8 public, 10 app, 9 ops, 1 mobile board) match the design in structure, copy and behaviour, on top of the shell work already shipped in #271 and the admin split shipped in #274. Where the deck and a later product decision disagree, the product decision wins and is listed under *Deliberate departures*.

## Deliberate departures from the deck

| Deck | Decision | Why |
|---|---|---|
| One charcoal shell with `Main / Operations / System` nav, Permissions as a top-level item | Keep the registry-driven app/admin split (two sidebars, one emerald shell — main already dropped the red admin tint before this branch) | #274 post-dates the deck and CLAUDE.md mandates the split; Permissions has no index page. Only the *styling* of nav items follows the deck (solid primary pill in both sidebars, 44px rows on phones). |
| No footer inside the app frame | Keep `BrandingFooter` | Footer links became admin-configurable in #282/#287, after the deck. |
| Landing badge "Batteries-included **Django** + Inertia starter" | "Batteries-included **FastAPI** + Inertia starter" | Deck typo. |
| Settings nav lands on the raw override table; module forms are a sub-page | Keep `/admin/settings/` = module forms, `/admin/settings/store` = overrides | Decided in #261 (item 1o). Each screen is restyled in place. |
| Files under an "Ops" admin group | Stays at `/file-storage/` in the app shell | Moving it means `/admin/files` + `AdminLayout` + `ADMIN_SIDEBAR` together; not a design change. |
| Profile → Preferences → "Task failure emails" toggle | **Omitted** | No notification subsystem exists; a toggle that does nothing is worse than none. Everything else on the Preferences card ships. |
| Profile → Sessions lists other devices with UA / IP | Lists **this browser** only, plus "Sign out everywhere" | Browser auth is a signed cookie, not a server-side session store. "Sign out everywhere" is real: it bumps a per-user `session_version` that the auth provider checks. |
| Workers offline card "last heartbeat 6m ago" | "offline" without an age | Celery inspect cannot report a worker that did not answer; persisting last-seen is a separate feature. |
| Storage subtitle "1.2 GB of 5 GB used" | "… · 1.2 GB used · 25 MB per file", quota segment appears only when `SM_FILE_STORAGE_QUOTA_BYTES` is set | No quota concept existed; adding the setting is cheap, inventing a number is not. |
| Doctor "Fix" / "Generate" / "Apply pending" run tools | They **copy the command** to the clipboard | Running Alembic from a web request is not something this app should do. |
| Locale pill "EN" always visible | Visible always; a single-locale install renders it as a static label | A control that opens nothing is noise, but the deck's placement is kept. |
| Register intro "The first account becomes the admin; later ones get the default role." | "New accounts start with no roles until an admin grants them." | The bootstrap admin is seeded from settings, not the first registrant. |
| Module tiles tint degraded modules emerald-soft | Degraded tiles are amber | Emerald is the shell's "everything is fine" colour, and a degraded health check tinted with it reads as a decoration rather than a warning. Amber matches the Doctor warn rows and the Failed/Stuck task tiles, so one colour means one thing across the ops screens. |
| Tasks index has no worker banner | `WorkerHealthBanner` stays above the table | The deck assumes a worker is running. A queue with a backlog and nobody consuming it looks identical to an idle queue in the table alone, and that is the single most common misconfiguration of this module — the banner is the answer to "why is nothing happening?". Shown only when unfiltered, so it never contradicts a narrowed view. |
| Users list collapses to a search-only bar on phones | Dropdown filters, the stat row and the Users/Roles tabs all stay at 390 | Dropping them made the phone layout a different feature rather than a narrower one: "show me invited users" is exactly the query someone runs from a phone. The controls wrap and take 44px tap targets instead of disappearing. |
| "Keep me signed in for 30 days" is just a longer cookie | Session cookie signature window is 30 days; effective lifetime is bounded per session at 14 / 30 days | Starlette signs and expires with one number, so honouring the checkbox forces the *signature* window to 30 days for everyone. Login writes an absolute `expires_at` into the session (`now + cookie_max_age_seconds`, or `remember_me_max_age_seconds` when ticked) and `UsersAuthProvider` refuses a session past it — so an ordinary sign-in still dies at 14 days even though the signer would verify it for 30. Sessions minted before this carry no `expires_at` and are accepted as legacy; that fail-open is temporary. |

## Cross-cutting building blocks (packages/ui)

These are built first because three or more screens depend on each.

- **`StatCard`** — relaid out to the deck: label top-left, optional icon top-right, value in Sora, delta as inline coloured text (not a badge). New `tone: 'default' | 'warning' | 'destructive'` tints the whole card (Doctor "Pending migrations", tasks "Failed"/"Stuck", users "Pending invites" number). `icon` becomes optional so the users/grants "plain" stats use the same component.
- **`SegmentedControl`** — `--sec` track with a raised card-coloured active chip, optional inline counts. Used by users (Users/Roles), settings store (scope tabs), tasks (status filter), flags (scope), add-people (mode), branding preview (App/Sign-in/Email).
- **`ConfirmActionDialog`** — one destructive/primary confirm over `AlertDialog`: icon tile, title, description, optional `confirmText` (type-to-confirm, mono input), optional children (args box), `confirmLabel`/`cancelLabel` props (labels come from the caller's catalog). Replaces the four ad-hoc dialogs (file delete, user delete, task retry, flag toggle).
- **`PasswordInput`** (show/hide) and **`PasswordStrength`** (bar + label; scoring: length ≥ 8, not all digits, mixed classes; labels weak/ok/strong) for login, register, reset, invite, profile.
- **`relative-time.ts`** gains day/month/year buckets and a future form ("in 5d") with matching `ui.relative_time.*` keys.
- **`initials()`** helper — two letters from name or email; used by every avatar (sidebar user row, users list, edit header, profile).
- **`PageShell`** gains `titleClassName` (mono task names), `leading` (avatar), `badge` (status pill next to the title), `mobileAction` (compact label + href/onClick shown in the phone bar), and `back` (href for the phone bar's chevron).
- **`AuthCardShell`** gains `variant="split"` with an `aside` slot: dark brand column (Login) or light intro column (Register, Accept invite). Its card surface uses semantic tokens so the `.dark` theme works.
- **Theme** — `light | dark | system` stored in `localStorage`, applied to `<html class="dark">` on boot (`host/client_app/app.tsx`) and from the Profile preference. The semantic tokens already define `.dark`; components with hardcoded light colours are fixed as found during verification.

## Shell (00, 28)

- Sidebar active item: solid `bg-primary text-white` pill in both the app and admin sidebars; 15px labels; rows `min-h-11` below `lg`.
- Topbar: breadcrumb · "Search ⌘K" · locale pill · **Log out** (POST, from the `userDropdown` logout item).
- Sidebar user row: two-letter initials on a neutral surface.
- Phone bar (< lg): back chevron when the page declares `back`, else hamburger; **page title** (from the heading context; mono when the shell is told so); right slot = `mobileAction` or the avatar. Locale control moves to the drawer footer.
- Drawer: full-width below `sm`, `✕` + app name header, no icons on rows, active pill.
- Menu regression: restore `section=MenuSection.ADMIN_SIDEBAR` (+ Branding `order=105`) dropped by #280, with a registry test.

## Public screens (01–08)

- **Landing**: copy pass (badge, h1, subtitle, six feature cards, quickstart body, CTA strip), helper line under the terminal, visible "Copy / ✓ Copied" label, grey terminal comments, primary CTA anchors `#quickstart`, nav shows one "Sign in" (or "Open dashboard" when signed in).
- **Errors**: numeral coloured per status (amber/emerald/red) at 64px inside a bordered card; no "HTTP n" pill; sentence-case titles ("No access", "Not found", "Something broke"); new descriptions; 403 names the missing permission from a new `required_permission` prop; 500 shows the short `req_` id chip with copy and a **Retry** action; "Go home" targets the dashboard when signed in.
- **Login**: dark split layout; "Sign in" heading and button; "Forgot password?"; show/hide password; "Keep me signed in for 30 days" (new `remember` flag → 30-day cookie); rule divider "or" + "Continue with {provider}"; footer "No account? Register — or ask an admin to invite you." (register link only when signup is allowed); a "Waiting on you" state replaces the inline unverified banner.
- **Register**: light split with intro + two check rows; "Optional" name placeholder; strength meter + helper; field-level confirm error; "Create account"; "Sign in" link.
- **Forgot / Reset**: "valid for {minutes} minutes" from settings; sent state with ✉ tile, bold email, amber console-mailer callout (only when the mailer does not deliver) and a resend countdown; reset page "Set a new password" / "Confirm" / strength / "Save and sign in" (signs in with the email decoded from the token); "Link expired" state rendered on GET when the token is dead.
- **Verify**: "Email verified" / "Go to sign in"; "Link expired" amber card with "Resend verification" (email decoded from the expired token, `verify_exp=False`); lifetime from settings.
- **Accept invite**: light split; "{inviter} invited you to {app}" (falls back to "You've been invited to {app}"), summary card Email / Role / Expires, form with Full name, "Join workspace", helper line. Backend: `invited_by` claim on the invite token, `expires_at` from `exp`, optional `full_name` on accept.
- **Keycloak**: both interstitials inside `AuthCardShell`; realm URL prop; "Not redirected? Continue manually"; the signed-out page gets a real route (`/keycloak/logged-out`, public) and becomes the post-logout target.

## App screens (09–18)

- **Dashboard**: new `StatCard` layout; "+{n} this month" (new `users_created_this_month` stat), "all loaded", meta gains "· all checks healthy"; two-row `ModuleTile` with "loaded · healthy / degraded / no checks" and "Open / No view"; `DemoPlaceholders` removed.
- **Users list**: plain stat row; segmented Users/Roles; "Status: all ▾" / "Role: all ▾" (Verified folded into Status: all / active / unverified / invited / disabled); flex search; two-letter avatars; **invited vs unverified** (new `invited_at` column + migration) with tinted invited rows ("invited 2d ago · expires in 5d", **Resend** via new admin endpoint); dimmed disabled rows; relative "Last seen"; row click → edit; kebab menu (Edit / Resend / Copy reset link / Disable); in-card "Showing 1–20 of N" footer.
- **Add people**: mode control above the cards ("Invite by email" / "Create account"); page-level amber mailer banner naming the mailer with a "Configure SMTP" link to module settings; chip email input (Enter/paste to add, invalid chips red, "N addresses · M invalid", send count = valid chips); "Roles for everyone in this batch"; "Message (optional)" threaded through the bulk-invite schema and both mailers; two-column with a persistent "Last batch" card (✓ Copy link / ✕ Retry, "{sent} sent · {failed} failed", 7-day expiry note from settings); no redirect after a fully successful batch.
- **Edit user**: header with avatar, name, "email · joined Mon YYYY · last login 2h ago", status pill, "{n} unsaved changes" / Discard / Save changes; Details card holds name, email, roles and "Manage permissions →"; one Account card (Sign-in, Created, Verified, Disabled at, Disable/Enable, Copy reset link, Mark verified); **Recent activity** card from the audit log (actor = this user, hidden when `audit_log` is not installed) with "See all in the audit log →"; Danger zone copy and red-tinted style.
- **Profile**: view passes a real `user` prop (fixes the blank-name bug); two columns: Details (avatar, email, name, "Save details"), Password (current/new/confirm + strength, new `POST /api/users/me/password`, hidden for SSO users), Sessions (this browser + "Sign out everywhere" via `session_version`), Preferences (Language via the locale form, Theme light/dark/system).
- **Role edit**: "Edit role: {name}"; Reset / Cancel / Save role; "Filter modules or permissions…" searches keys too; "Granted only" toggle; bold granted count + flat bar; two-column card grid; tri-state header checkbox; "n / m"; muted off keys; no footer badge; leave-guard ported from Users/Edit.
- **User grants**: "Permissions — {email}"; "{name} · effective permissions combine role grants and direct grants"; Cancel / Save grants; plain stats (Roles pill, Direct grants, Effective n / total); legend "direct grant" / "from role"; two-column cards with "{n} effective / {total}"; single-column rows switch-first with "direct" / "granted by {role}" pills.
- **Settings store**: description per deck; "Per-module forms" / "+ New override"; scope tabs with counts; "Search keys…"; server-side paging (20/page) with "Showing a–b of N"; columns Scope / Key (scope id as sub-line) / Type (short, lowercase) / Value (hex swatch) / Actions "Edit · Delete".
- **New override**: title/subtitle/labels per deck; `1.3fr 1fr` grid; suggestion dropdown with "Registered by modules" header and "{type} · env {VAR}" / "{type} · default {v}" meta; **Resolved value** panel (this override / env fallback / module default, with the restart note); `known_keys` enriched with `env_var`, `env_set`, `default`, `requires_restart`, `is_secret` (secrets masked) and the settings registry's definitions.
- **Module settings**: sidebar shows package names with "· n overridden"; header outside the card ("`users` settings", subtitle, "{n} unsaved", Save); rows `170px 1fr 210px` with trailing meta (env var · default / "overridden in DB · Revert" / "write-only · never returned"); Revert only for DB overrides; overridden inputs highlighted; `Switch` for booleans, select for enum-pattern strings; Test connection in the card footer with the last result ("✓ Last test succeeded 4m ago", kept in sessionStorage); `testable` becomes `{package: [check names]}`.

## Ops screens (19–27)

- **Feature flags**: copy pass; segmented scope (system + tenants + "Other…" for a new id); columns Name / Description / System (on/off) / Effective / Actions; text "Clear override"; tinted overridden rows; audit footer note; "View change history →" to the audit log filtered on `FeatureFlagOverride` (module registers audit links).
- **File storage**: "File storage" + backend/usage/limit subtitle; drag-and-drop strip; "Uploads in progress" card with cancel (`xhr.abort`) and Retry, real failure reasons from the API body; "Type: image/png (12)" trigger; "Uploaded by" filter with resolved names; relative "When"; checkbox selection + "Delete selected" (new bulk endpoint); footer "{n} selected · showing a–b of N"; "Download" text link; delete confirm via the shared dialog (name in curly quotes, backend in the copy, "Delete file").
- **Confirms**: user delete uses the destructive variant (bug: it was primary) with "Type the email to confirm"; retry says "Queue retry" with "This one has already been retried {n} time(s)." and a one-line args/kwargs box; flag toggle restyled on the shared dialog.
- **Background tasks**: copy; Workers + "Retry all failed" (new bulk endpoint, failed + stuck, current filter) in the header; five tiles Queued / Running / Succeeded 24h (new windowed count) / Failed (red) / Stuck (amber) that still act as filters; segmented All / Failed / Running / Stuck + "Queue: all ▾" (new `queue` filter and `queues` prop); six columns (Worker dropped), mono task names, tinted lowercase pills, relative "Queued", "—" duration until finished, text "Retry", clickable rows, in-card paging.
- **Task detail**: mono title with inline status pill; "execution {id} · attempt {n} of {max}" (`max_retries` prop); "Back to executions"; Details in deck order with Duration and an Exception footer; Arguments / Keyword arguments side by side; terminal-styled Traceback with Copy and a highlighted last line; `320px 1fr` grid; phone order = status strip, facts, traceback, bottom "Retry task".
- **Workers**: header actions ("Last updated HH:MM:SS", Refresh, Executions); two-column fleet; mono hostnames, "celery 5.4.0 · uptime 4d 2h" (new `uptime_seconds`), primary dots, tinted pills, dimmed offline cards, mono queue chips; broker-unreachable state shows `SM_BG_TASKS_BROKER_URL=<redacted url>`; the start command literal is corrected to the real `celery -A scripts.run_worker:celery worker -Q …`.
- **Audit log**: copy; **Export CSV** (streaming endpoint honouring filters); filter grid with labels above (Entity type / Action / Actor "Anyone" / Date range popover) and Apply + outline Clear; Time as `d MMM HH:mm:ss` mono; borderless lowercase action pills; entity cell = resolved display name link + muted table-name tag (registry gains a label resolver hook, implemented by users/settings/background_tasks/feature_flags); actor by name or email; "field old → new" with `null`/`""` distinct, "+{n} more fields" after 2, "no changes recorded"; in-card paging with `2,431` formatting.
- **Branding**: description; header "{n} unsaved changes" (amber) / Discard / Publish branding with dirty tracking (presets and text stage locally; images still upload on pick); `1.15fr 1fr`; App name + Primary colour on one row; four lowercase preset chips matching the deck colours; three dashed image dropzones in one row; footer text + links editor per deck (existing `FooterLinksField` restyled); "Design pack: emerald ▾" in the form foot; "Live preview" with App / Sign-in / Email tabs, topbar and footer strips, caption.
- **Doctor**: **real data** — `checks` from `run_diagnostics` (boot result kept on `app.state`, re-run on POST), `migrations` from Alembic's script directory with applied/pending status, `dev_server` from settings (vite/api ports, worker from the last workers snapshot when the module is present); "Copy report" + "↻ Re-run checks"; stats "Checks passing 7 / 8", "Modules loaded", tinted "Pending migrations", "Python"; one-line pass rows and expandable warn rows with "Fix" (copies the command); migrations rows with "Generate" / "Apply pending" (copy); Dev server rows; terminal transcript panel. Fixture data is deleted.

## Data, migrations, endpoints (summary)

| Module | Change |
|---|---|
| users | `invited_at`, `session_version` columns (+ migration); `remember` on login; `message` on bulk invite; `invited_by` claim + `expires_at` in invite preview; `full_name` on accept; `POST /api/users/admin/{id}/resend-invite`; `POST /api/users/me/password`; `POST /api/users/me/sessions/revoke-all`; profile view passes `user`; forgot/reset/verify views pass lifetimes, mailer flag and decoded email |
| keycloak | `realm_url` prop; `GET /keycloak/logged-out` (public) |
| hosting | `required_permission` on 403 error pages; diagnostics result kept on `app.state.sm`; Alembic revision listing helper |
| dashboard | `users_created_this_month`; Doctor props + `POST /admin/doctor/rerun` |
| settings | store view: `scope`, `q`, `page` + `counts`, `pagination`; `known_keys` enrichment; `testable` as `{package: [checks]}` |
| feature_flags | `register_audit_links` |
| file_storage | `used_bytes`, `backend`, limits, optional `quota_bytes` setting; `created_by` filter + uploader facet + resolved labels; `POST /api/file-storage/files/bulk-delete` |
| background_tasks | `success_24h` count; `queue` filter + `queues`; `POST …/executions/retry-failed`; `max_retries` on detail; `uptime_seconds` on workers; redacted broker url |
| audit_log | `GET /api/audit_log/export.csv` (the module's api prefix is its package name, not the view url); browse view passes `items[]`; actor-by-name filter; entity display labels via a registry label hook |
| core | `AuditLink` gains an optional `label_resolver`; `MenuItem` section fix |

## Testing

- Python: every new endpoint/prop gets a test in its module's `tests/` (pattern: `authenticated_client`); migration covered by the existing autogenerate-drift check.
- JS: new `packages/ui` primitives get vitest specs (`SegmentedControl`, `ConfirmActionDialog`, `PasswordStrength`, `relative-time` buckets, `initials`); module components with logic (email chips, module settings row meta, changes list) get `tests-js/` specs.
- Gates: `make lint` (incl. untranslated-string and 300-line checks), `make test`, `make doctor`.
- Browser: every screen is opened at 1440 and 390 wide through Playwright against `make dev`, compared against `/tmp/hifi/screens/*.html`, and screenshots are kept under `qa-shots/hifi/`.
