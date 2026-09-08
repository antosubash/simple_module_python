# Hi-Fi Pages Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make all 28 screens of the "Hi-Fi Pages" design deck real in this app — structure, copy, states and the small backend additions they need — and verify every screen in a browser.

**Architecture:** Shared primitives land first in `packages/ui` (stat card, segmented control, confirm dialog, password inputs, relative time, initials, page-shell slots, split auth shell, theme). Then each module's screens are brought to the deck by an owner task with disjoint file ownership so tasks can run in parallel in one worktree. Backend additions are small and local to each module (new props, a few endpoints, two columns on `users`). Audit-log label resolution runs last because it touches every module's `register_audit_links`.

**Tech Stack:** Python 3.12 / FastAPI / SQLModel / Alembic; Inertia.js + React 19 + Tailwind 4 + shadcn (vendored under `packages/ui/src/components/ui`); vitest + testing-library; pytest with the `simple_module_test` fixtures; Playwright for browser verification.

**Spec:** `docs/superpowers/specs/2026-09-03-hifi-pages-design.md` — the decisions. Per-screen evidence: `docs/superpowers/specs/hifi-gap/*.md`. Deck source (one file per screen): `/tmp/hifi/screens/NN-<id>.html`, tokens `/tmp/hifi/tokens.html`, sample data `/tmp/hifi/script.js`. If `/tmp/hifi` is gone, re-extract it from `docs/superpowers/specs/hifi-gap/` (the gap files quote every string) — the deck HTML is not committed.

## Global Constraints

- Follow `CLAUDE.md` (repo root) and `docs/framework-conventions.md`. In particular: **300-line cap** on `.py/.ts/.tsx`; **no user-visible string literals in `.tsx`** — every string goes through `t(keys.<ns>.…)` from `@simple-module-py/i18n` (wrap technical literals in `<code>` or mark `// i18n-exempt: <reason>`); SQLModel for every model/DTO; per-module `SM_<MODULE>_*` settings; Zod schemas built inside hooks.
- After adding catalog keys run `make gen-i18n` (Task 0 adds it) — never hand-edit `packages/i18n/src/{keys.generated,generated-resources}.ts`.
- Copy is the deck's copy, verbatim, except the departures listed in the spec. Sentence case ("Feature flags", "Go home"). Status/scope/type values that the deck shows lowercase are lowercase.
- Typography/colour: use the existing tokens (`font-[var(--font-display)]` = Sora for headings/values, `font-mono` for keys/ids/commands, `text-primary-700` / `bg-primary-600/10` for the emerald "soft" pill, amber = `text-amber-700 bg-amber-50 border-amber-200`, red = `text-red-700 bg-red-50 border-red-200`, blue = `text-blue-700 bg-blue-50 border-blue-200`). Never hardcode hex in TSX unless the deck value is a data value (colour swatch).
- Tables: header cells `bg-secondary/40 text-[11px] font-semibold uppercase tracking-[0.08em] text-muted-foreground`; in-card footers use `border-t px-4 py-3 flex items-center justify-between text-sm text-muted-foreground`.
- Pagination copy everywhere: "Showing {from}–{to} of {total}" (en dash), buttons "Previous" / "Next", always visible.
- Phone (< `lg`): minimum 44px hit targets on primary controls (`min-h-11`), no horizontal scroll at 390px.
- Tests: Python in `modules/<name>/tests/` using `client`/`authenticated_client`; JS in `modules/<name>/tests-js/*.test.tsx` or `packages/ui/src/**/*.test.tsx`. Run scoped commands while other tasks are in flight (see each task's "Verify" step); the full `make lint && make test && make doctor` runs in Task 12.
- **Parallel-safe git:** commit only your own paths with `git add -- <paths>` (never `-A`, `-a`, `stash`, `reset`, `checkout -- .`). If git reports `index.lock`, wait 3 s and retry. Shared files other tasks also edit (`packages/ui/locales/en.json`, `packages/ui/src/index.ts`, `modules/users/users/locales/en.json`, `modules/users/users/contracts/schemas.py`): make surgical `Edit`s, never rewrite the file; if an edit fails because the file changed, re-read and retry.
- Do not edit files owned by another task (each task lists its files). If you need a change there, write it in your report under "Cross-task requests".

---

### Task 0: Menu-section regression fix + `make gen-i18n`

**Files:**
- Modify: `modules/branding/branding/module.py` (menu item: `section=MenuSection.ADMIN_SIDEBAR`, `order=105` — verify current state first; gap file says they were dropped by #280, the worktree base may already have them)
- Modify: `modules/feature_flags/feature_flags/module.py` (same check)
- Test: `modules/branding/tests/test_menu_section.py`, `modules/feature_flags/tests/test_menu_section.py`
- Create: `scripts/gen_i18n.py`
- Modify: `Makefile` (add `gen-i18n` target next to `gen-pages`)

**Interfaces:**
- Produces: `make gen-i18n` — regenerates `packages/i18n/src/{generated-resources,keys.generated}.ts` from every installed module's `locales/`, `host/locales`, `packages/ui/locales` without booting the app.

- [ ] **Step 1: Menu tests.** For each module write a test that builds a `MenuRegistry`, calls `Module().register_menu_items(registry)`, and asserts the item with `url == MENU_URL` has `section == MenuSection.ADMIN_SIDEBAR` (and `order == 105` for Branding). Run them; fix `module.py` if they fail (the base commit may already be correct — then the tests simply guard it).
- [ ] **Step 2: `scripts/gen_i18n.py`:**
  ```python
  """Regenerate the typed i18n key files without booting the host. `make gen-i18n`."""

  from pathlib import Path
  from simple_module_core.discovery import discover_modules
  from simple_module_hosting.i18n_manifest import emit_frontend_types_for_modules
  from simple_module_hosting.settings import Settings

  ROOT = Path(__file__).resolve().parent.parent

  if __name__ == "__main__":
      emit_frontend_types_for_modules(Settings(), discover_modules(), ROOT)
      print("i18n key files regenerated")
  ```
  Makefile: `gen-i18n:` → `uv run --project host python scripts/gen_i18n.py`. Add `gen-i18n` to `.PHONY`.
- [ ] **Step 3: Verify** `make gen-i18n` runs and leaves `git status` clean for the generated files (no key changes yet). `uv run pytest modules/branding/tests/test_menu_section.py modules/feature_flags/tests/test_menu_section.py -q`.
- [ ] **Step 4: Commit** `git add -- scripts/gen_i18n.py Makefile modules/branding modules/feature_flags && git commit -m "fix: guard admin-sidebar menu sections; add make gen-i18n"`.

---

### Task 1: Shared UI primitives (`packages/ui` components)

**Files:**
- Modify: `packages/ui/src/components/StatCard.tsx` (+ update `StatCard.test.tsx`)
- Create: `packages/ui/src/components/SegmentedControl.tsx` (+ `.test.tsx`)
- Create: `packages/ui/src/components/ConfirmActionDialog.tsx` (+ `.test.tsx`)
- Create: `packages/ui/src/components/PasswordInput.tsx`, `packages/ui/src/components/PasswordStrength.tsx` (+ `password-strength.test.ts` for `scorePassword`)
- Modify: `packages/ui/src/lib/relative-time.ts` (+ `.test.ts`); Create: `packages/ui/src/hooks/use-relative-time.ts`
- Create: `packages/ui/src/lib/initials.ts` (+ `.test.ts`)
- Create: `packages/ui/src/lib/theme.ts` (+ `.test.ts`)
- Modify: `packages/ui/locales/en.json` (surgical), `packages/ui/src/index.ts` (add exports)

**Interfaces (produces — other tasks code against these exactly):**
```ts
// StatCard.tsx — deck layout: label top-left, optional icon tile top-right, value (Sora 25–30px), delta inline text
interface StatCardProps {
  label: string;
  value: React.ReactNode;
  icon?: LucideIcon;                 // optional now ("plain" stats)
  delta?: string;                    // rendered as inline text after/under the value, coloured by deltaTone
  deltaTone?: 'success' | 'info' | 'warning' | 'destructive' | 'secondary';
  suffix?: string;                   // muted text right after the value, e.g. "/ 8"
  tone?: 'default' | 'warning' | 'destructive'; // tints the whole card (bg + border + value colour)
  valueClassName?: string;
  className?: string;
}
// SegmentedControl.tsx — `--sec` track, active option = card bg + shadow; role="radiogroup"/"radio"
interface SegmentedOption<V extends string> { value: V; label: string; count?: number; disabled?: boolean }
interface SegmentedControlProps<V extends string> {
  value: V; onChange: (next: V) => void; options: SegmentedOption<V>[];
  'aria-label': string; size?: 'sm' | 'md'; className?: string;
}
// ConfirmActionDialog.tsx — over ui/alert-dialog. Controlled.
interface ConfirmActionDialogProps {
  open: boolean; onOpenChange: (open: boolean) => void;
  tone?: 'destructive' | 'primary';      // icon tile tint + confirm button variant
  icon: LucideIcon;
  title: React.ReactNode; description: React.ReactNode;
  confirmLabel: string; cancelLabel: string;
  onConfirm: () => void; busy?: boolean;
  confirmText?: { expected: string; label: string; placeholder?: string }; // type-to-confirm (mono input, case-insensitive match), gates the confirm button
  children?: React.ReactNode;            // extra block between description and buttons (args box)
}
// PasswordInput.tsx — Input with trailing show/hide text button
interface PasswordInputProps extends Omit<React.ComponentProps<typeof Input>, 'type'> { showLabel: string; hideLabel: string }
// PasswordStrength.tsx
export type StrengthLevel = 'none' | 'weak' | 'ok' | 'strong';
export function scorePassword(pw: string): { level: StrengthLevel; percent: number }
//   '' → none/0; <8 chars or all digits → weak/33; ≥8 with letters+digits → ok/66; ≥12 with 3 classes → strong/100
interface PasswordStrengthProps { password: string; labels: Record<Exclude<StrengthLevel,'none'>, string>; hint?: string; className?: string }
// relative-time.ts
export const RELATIVE_AGE_KEYS = { unknown, justNow, seconds, minutes, hours, days: 'ui.relative_time.days_ago', months: 'ui.relative_time.months_ago', years: 'ui.relative_time.years_ago' }
export function relativeAge(ageMs: number): RelativeAge   // buckets: <10s justNow, <1m seconds, <1h minutes, <24h hours, <30d days, <365d months, else years
export const RELATIVE_UNTIL_KEYS = { minutes: 'ui.relative_time.in_minutes', hours: 'ui.relative_time.in_hours', days: 'ui.relative_time.in_days', expired: 'ui.relative_time.expired' }
export function relativeUntil(msUntil: number): RelativeAge   // ≤0 expired, <1h minutes, <24h hours, else days
// hooks/use-relative-time.ts
export function useRelativeTime(): { ago: (iso: string | null | undefined) => string; until: (iso: string | null | undefined) => string }
//   uses useT(); `now` sampled once per render; returns t(ui.relative_time.unknown) for unparsable input
// lib/initials.ts
export function initials(name?: string | null, email?: string | null): string
//   "Dana Rivera" → "DR"; "admin" → "AD"; "rob@example.com" (no name) → "RO"; nothing → "?"
// lib/theme.ts
export type ThemePreference = 'light' | 'dark' | 'system';
export const THEME_STORAGE_KEY = 'sm.theme';
export function readThemePreference(): ThemePreference;           // localStorage, default 'system'
export function resolveTheme(pref: ThemePreference, prefersDark: boolean): 'light' | 'dark';
export function applyTheme(pref: ThemePreference): void;         // toggles `dark` on <html>
export function setThemePreference(pref: ThemePreference): void; // persists + applies
export function initTheme(): () => void;                         // apply + subscribe to matchMedia('(prefers-color-scheme: dark)'); returns unsubscribe
```
- Catalog keys to add in `packages/ui/locales/en.json` (namespace `ui`): `relative_time.days_ago` "{count}d ago", `relative_time.months_ago` "{count}mo ago", `relative_time.years_ago` "{count}y ago", `relative_time.in_minutes` "in {count}m", `relative_time.in_hours` "in {count}h", `relative_time.in_days` "in {count}d", `relative_time.expired` "expired".

- [ ] **Step 1:** Tests first for `scorePassword`, `relativeAge`/`relativeUntil` buckets, `initials`, `theme` (jsdom: `applyTheme('dark')` adds the class, `resolveTheme('system', true) === 'dark'`), `SegmentedControl` (renders radios, click calls `onChange`, counts rendered), `ConfirmActionDialog` (confirm disabled until `confirmText.expected` typed; `onConfirm` called), `StatCard` (tone class + suffix). Run `npx vitest run packages/ui` — expect failures.
- [ ] **Step 2:** Implement each component. `StatCard`: `Card` → `CardContent` with a flex row (label / icon tile `h-8 w-8 rounded-lg bg-primary-600/10 text-primary-700`), value `font-[var(--font-display)] text-[26px] font-bold tracking-tight`, delta `text-sm` coloured by tone, `tone='warning'` → `bg-amber-50/60 border-amber-200 [&_.stat-value]:text-amber-700`, `destructive` → red equivalents. `ConfirmActionDialog`: `AlertDialogContent` with a 40px icon tile (`bg-red-50 text-red-600` / `bg-primary-600/10 text-primary-700`), left-aligned title/description, optional children, footer Cancel (outline) + confirm (`variant="destructive"` or default).
- [ ] **Step 3:** Export everything from `packages/ui/src/index.ts`; `make gen-i18n`.
- [ ] **Step 4: Verify** `npx vitest run packages/ui`, `npx tsc --noEmit -p packages/ui/tsconfig.json`, `npx biome check packages/ui`.
- [ ] **Step 5: Commit** `git add -- packages/ui packages/i18n/src && git commit -m "feat(ui): deck primitives — StatCard layout, SegmentedControl, ConfirmActionDialog, password inputs, relative time, initials, theme"`.

---

### Task 2: App shell, PageShell slots, split auth shell, theme boot

**Files:**
- Modify: `packages/ui/src/components/page-heading.tsx`, `packages/ui/src/components/PageShell.tsx`, `packages/ui/src/components/AppTopbar.tsx`, `packages/ui/src/components/LocaleSwitcher.tsx`, `packages/ui/src/layouts/{SidebarLayout,SidebarUserMenu,AuthenticatedLayout,AdminLayout,AuthCardShell}.tsx`
- Create: `packages/ui/src/layouts/MobileBar.tsx` (extracted from SidebarLayout to stay under 300 lines), `packages/ui/src/layouts/AuthSplitAside.tsx`
- Modify: `host/client_app/app.tsx` (call `initTheme()` in `setup`), `packages/ui/locales/en.json` (surgical), tests `packages/ui/src/components/AppTopbar.test.tsx`, `packages/ui/src/layouts/*.test.tsx` as needed
- Reads (do not modify): Task 1's `initials`, `theme`, `SegmentedControl`

**Interfaces (produces):**
```ts
// page-heading.tsx
interface Heading { title: string; url: string; section?: string; back?: string; mono?: boolean; mobileAction?: { label: string; href?: string; onClick?: () => void } }
export function useReportPageHeading(heading: Omit<Heading, 'url'>): void   // keep the old (title, section) overload working
export function usePageChrome(currentUrl: string): Heading | null
// PageShell.tsx
interface PageShellProps {
  title: string; description?: React.ReactNode; children; actions?; maxWidth?: 'full' | 'screen-xl'; section?: string;
  titleClassName?: string; leading?: React.ReactNode; badge?: React.ReactNode;
  mobileAction?: { label: string; href?: string; onClick?: () => void }; back?: string; mono?: boolean;
}
// AuthCardShell.tsx
interface AuthCardShellProps { children; variant?: 'card' | 'split-dark' | 'split-light'; aside?: React.ReactNode; width?: 'md' | 'lg' }
//   'card' = today's centred glass card (default). 'split-dark' = dark brand column (bg-landing-bg, blob, lockup, copyright) left + card right.
//   'split-light' = light column with `aside` content (no card) left + card right. Both collapse to a single column below `lg` (aside on top).
// AuthSplitAside.tsx — dark column content used by Login: lockup + h2 + p + check rows + "© {year} {appName}"; props { heading, body, checks: string[] }
```
- Shell requirements (spec § Shell): sidebar active item `bg-primary text-white` (app) / `bg-red-600 text-white` (admin) with `rounded-lg`, 15px labels; nav rows `min-h-11 lg:min-h-0`; topbar adds a **Log out** `Link method="post" as="button"` (outline, from the `userDropdown` item with `method === 'post'`, label from `ui.topbar.log_out`); locale pill = text code (`EN`) in a bordered 8px-radius pill; with one locale render a non-interactive pill with `title={t(ui.switcher.single_locale)}`; sidebar user row avatar = `initials(name, email)` on `bg-white/10 text-white` (no ring). Phone bar: left = `back` chevron `Link` when the page declares one else hamburger; title = `usePageChrome` title (`font-mono` when `mono`), else app name; right = `mobileAction` (text link, `min-h-11`) else avatar initials. Locale control moves into the drawer footer above the user row. Drawer `w-full sm:w-72 lg:w-64`, header `✕` + app name, rows without icons below `lg` (`NavIcon` gets `className="hidden lg:block"`).
- Catalog keys (`ui`): `topbar.log_out` "Log out", `switcher.single_locale` "Only {locale} is enabled", `sidebar.back` "Back".
- Keep `SidebarLayout.tsx` ≤ 300 lines by moving the mobile bar into `MobileBar.tsx`.

- [ ] **Step 1:** Tests: `AppTopbar` renders "Log out" when a post item exists; `PageShell` reports `mobileAction`/`back` (render inside `PageHeadingProvider`, read via a probe component using `usePageChrome`); `AuthCardShell variant="split-dark"` renders the aside. Run `npx vitest run packages/ui` → fail.
- [ ] **Step 2:** Implement. Run the same tests → pass. `make gen-i18n`.
- [ ] **Step 3: Verify** `npx vitest run packages/ui host`, `npx tsc --noEmit -p packages/ui/tsconfig.json`, `npx tsc --noEmit -p host/client_app/tsconfig.json`, `npx biome check packages/ui host/client_app`.
- [ ] **Step 4: Commit** `git add -- packages/ui host/client_app/app.tsx packages/i18n/src && git commit -m "feat(shell): deck shell — solid active nav, topbar log out + locale pill, phone bar title/action/back, split auth shell, theme boot"`.

---

### Task 3: Landing + error screens (host)

**Files:**
- Modify: `host/client_app/pages/Landing.tsx`, `host/client_app/pages/Error.tsx`, `host/client_app/components/CopyCommand.tsx` (+ test), `host/locales/en.json`, `packages/ui/src/components/ErrorScreen.tsx`, `packages/ui/src/layouts/PublicLayout.tsx` (nav: one "Sign in" / "Open dashboard"), `packages/ui/locales/en.json` (surgical: `public_nav.sign_in` "Sign in", `public_nav.open_dashboard` "Open dashboard")
- Modify: `framework/hosting/simple_module_hosting/_error_handlers.py` (+ `framework/hosting/tests/test_error_page_shared_props.py`): add `required_permission` to the Error page props, parsed from a `HTTPException.detail` of the form "Permission required: <perm>" (see `simple_module_hosting/permissions.py`); `None` otherwise.
- Evidence: `docs/superpowers/specs/hifi-gap/landing-errors-mobile-01-08-28.md` §01 and §08; deck `/tmp/hifi/screens/01-landing.html`, `08-errors.html`.

**Requirements:** every delta in the gap file's §01.4 and §08.4 except: keep the CopyCommand wrapping behaviour (delta 6), keep footer links (spec departure), nav shows "Sign in" (anon) or "Open dashboard" (authed) and no "Sign up". Landing badge reads "✦ Batteries-included FastAPI + Inertia starter". Error page: numeral colour per status (`text-amber-700` 403, `text-primary-700` 404, `text-red-600` 5xx) at `text-[64px]`, bordered card `max-w-md`, no HTTP pill, titles "No access" / "Not found" / "Something broke", descriptions per deck (403 uses `required_permission` in `<code>` when present, else "Your role doesn't include the permission this page needs. Ask an admin to grant it."), 500 shows `CopyableId` with `label={id.slice(0,8)}` prefixed `req_` and a **Retry** button (`router.reload()`), other statuses keep Go back; "Go home" → `/dashboard/` when `auth.isAuthenticated` else `/`. Extend the same rules to 401/419/422/429/503 (keep their existing copy, sentence-case the titles).

- [ ] **Step 1:** Python test: a 403 raised by `RequiresPermission("settings.manage")` renders the Error page with `required_permission == "settings.manage"`. JS test: `CopyCommand` shows the visible "Copy" label and "✓ Copied" after click. Run → fail.
- [ ] **Step 2:** Implement backend + pages + copy. `make gen-i18n`.
- [ ] **Step 3: Verify** `uv run pytest framework/hosting/tests host/tests -q`, `npx vitest run host packages/ui`, `npx tsc --noEmit -p host/client_app/tsconfig.json`, `npx biome check host/client_app packages/ui/src/components/ErrorScreen.tsx packages/ui/src/layouts/PublicLayout.tsx`, `node scripts/check_untranslated_strings.mjs` (only your files matter).
- [ ] **Step 4: Commit** own paths, `feat(host): landing and error screens per the hi-fi deck`.

---

### Task 4: Public auth screens (users auth_local + keycloak)

**Files:**
- Modify: `modules/users/users/pages/{Login,Register,ForgotPassword,ResetPassword,VerifyEmail,AcceptInvite}.tsx` (split large ones into `modules/users/users/auth_local/components/*.tsx` — that directory is not scanned as pages), `modules/users/users/auth_local/{views.py,api.py,invite_preview.py}`, new `modules/users/users/auth_local/token_preview.py`, `modules/users/users/contracts/schemas.py` (surgical: `LoginRequest.remember: bool = False`, `AcceptInviteRequest.full_name: str | None = None`), `modules/users/users/locales/en.json` (surgical), `modules/users/users/settings.py` only if a lifetime constant is missing
- Modify: `modules/keycloak/keycloak/pages/{Login,LoggedOut}.tsx`, `modules/keycloak/keycloak/endpoints/views.py`, `modules/keycloak/keycloak/provider.py` (public path), `modules/keycloak/keycloak/locales/en.json`
- Modify: `tests/e2e/test_{audit_log_ui,document_titles,error_pages,i18n_rendering,settings_ui,shell_ui}.py` — the login button is now "Sign in"
- Tests: `modules/users/tests/test_auth_screens_props.py` (new), extend `modules/users/tests/test_views.py`, `modules/keycloak/tests/test_views.py`
- Evidence: `hifi-gap/auth-screens-02-07.md`; deck `02`–`07`.

**Interfaces (consumes):** `AuthCardShell variant`, `AuthSplitAside`, `PasswordInput`, `PasswordStrength`, `useRelativeTime`. **Produces:** invite preview reads optional `invited_by` (display name) claim and `exp` → `invite.invited_by_name: str | None`, `invite.expires_at: str | None` (Task 5 mints the claim; tolerate its absence).

**Requirements:** every delta in §02–§07 of the gap file, with these rulings: "Keep me signed in for 30 days" posts `remember: true` and the login endpoint sets the session cookie max-age to 30 days (else the configured default) — implement by setting `request.session` max-age via the response cookie (see how the session cookie is issued in `auth_local/api.py`; if the session middleware owns the cookie, set `request.scope["session_max_age"]`-style override only if supported — otherwise issue the cookie explicitly with `max_age=30*24*3600`); "Waiting on you" is a state of `Login.tsx` shown after `LOGIN_USER_NOT_VERIFIED` with the mono email chip and "Resend verification email"; forgot view passes `reset_link_lifetime_minutes` and `mailer_delivers`; reset view decodes the token on GET (`token_preview.decode_reset_token(token, secret) -> {email} | None`, `verify_exp=True`) and renders the "Link expired" card when it is `None`; "Save and sign in" resets then POSTs login with the decoded email; verify view decodes with `verify_exp=False` to pass `email` for "Resend verification" and `verification_lifetime_hours`; Keycloak gets `GET /keycloak/logged-out` (public path) + `realm_url` prop and both pages render inside `AuthCardShell`. Update the six e2e files' `get_by_role("button", name="Log in")` to "Sign in".

- [ ] **Step 1:** Python tests: login with `remember` sets a cookie with `Max-Age=2592000`; forgot page props carry `reset_link_lifetime_minutes == 60` and `mailer_delivers`; reset page with an expired token renders `expired: true`; verify page passes `email` for an expired token; invite preview returns `invited_by_name`/`expires_at` when the claims are present; keycloak `/keycloak/logged-out` is 200 unauthenticated. Run → fail.
- [ ] **Step 2:** Implement backend, then pages. `make gen-i18n`.
- [ ] **Step 3: Verify** `uv run pytest modules/users/tests modules/keycloak/tests -q`, `npx tsc --noEmit -p modules/users/tsconfig.json -p modules/keycloak/tsconfig.json` (run each), `npx biome check modules/users modules/keycloak`, `node scripts/check_untranslated_strings.mjs`.
- [ ] **Step 4: Commit** own paths, `feat(users,keycloak): public auth screens per the hi-fi deck`.

---

### Task 5: Users admin screens — list, add people, edit user, profile

**Files:**
- Modify: `modules/users/users/pages/Users/{Index,AddPeople,Edit}.tsx`, `modules/users/users/pages/Users/components/*`, `modules/users/users/admin/components/*`, `modules/users/users/pages/Profile.tsx` (+ new `modules/users/users/auth_local/components/{PasswordCard,SessionsCard,PreferencesCard,ProfileDetailsCard}.tsx`), `modules/users/users/admin/{views.py,api.py,queries.py,service.py,bulk_invite.py}`, `modules/users/users/models/user.py`, `modules/users/users/contracts/schemas.py` (surgical), `modules/users/users/manager.py` (invite token claim), `modules/users/users/provider.py` (session_version check), `modules/users/users/mailer/{__init__,console,smtp}.py` + template (invite message), `modules/users/users/auth_local/views.py` **only** the `profile_page` function (Task 4 owns the rest — coordinate by editing just that function), `modules/users/users/auth_local/api.py` **only** to add `POST /me/password` and `POST /me/sessions/revoke-all` (append at the end), `modules/users/users/locales/en.json` (surgical)
- Create: `host/migrations/versions/<rev>_users_invited_at_session_version.py` via `make migration msg="users invited_at and session_version"` then review it
- Tests: `modules/users/tests/test_users_list_invites.py`, `test_admin_resend_invite.py`, `test_profile_password.py`, `test_sessions_revoke.py`, `test_bulk_invite_message.py`; JS `modules/users/tests-js/EmailChipInput.test.tsx`
- Evidence: `hifi-gap/users-10-13.md`; deck `10`–`13`.

**Interfaces (consumes):** `StatCard` (no icon), `SegmentedControl`, `ConfirmActionDialog`, `PasswordInput`, `PasswordStrength`, `useRelativeTime`, `initials`, `PageShell` `leading`/`badge`/`mobileAction`/`back`, `theme.ts` (`setThemePreference`). **Produces:** invite tokens carry `invited_by` (inviter display name) — mint through one helper `manager.mint_invite_token(user, invited_by: str | None)` used by bulk invite and resend; `User.invited_at`, `User.session_version`; `UserListItem.invited_at`, `.invite_expires_at`, `.state: 'active'|'unverified'|'invited'|'disabled'`.

**Requirements:** every delta in §10–§13 with the spec's rulings: Verified filter folds into Status (`all/active/unverified/invited/disabled`); kebab menu = Edit / Resend invite (invited only) / Copy reset link / Disable|Enable; whole row links to edit; "Last batch" is in-memory (React state) with Retry re-posting the single address; no redirect after a fully successful batch; Recent activity reads `audit_log` through `request.app.state` duck-typing (`getattr(app.state.sm, "audit_links", None)` is not enough — import `audit_log.service` lazily inside a `try/except ImportError` and pass `recent_activity: list[{at, summary, href}] | None`); Profile: `profile_page` passes `user` (`UserRead`), Password card posts `POST /api/users/me/password {current_password, new_password}` (403-style 400 for SSO users), Sessions card shows "This browser · signed in {ago}" from `last_login_at` and "Sign out everywhere" posts `POST /api/users/me/sessions/revoke-all` which increments `session_version`, revokes refresh tokens, and clears the current session (provider's `resolve_user` compares the session's stored `session_version` with the user's and rejects mismatches — store it in the session at login); Preferences: Language select posts the existing set-locale form, Theme select calls `setThemePreference`. Phone: users rows fold to cards (`sm:hidden` card list with avatar, email, "role · status · 2h ago", chevron), `mobileAction={{label: '+ Add', href: '/admin/users/add'}}`.

- [ ] **Step 1:** Python tests first (list shows `state == 'invited'` for an invited user and `'unverified'` for a self-signup; resend endpoint 202 + mailer called + `invited_at` refreshed; password change rejects a wrong current password and accepts a valid change; revoke-all bumps `session_version` and the old cookie no longer authenticates; bulk invite passes `message` to the mailer). JS test for the chip input (Enter adds, invalid chip flagged, paste splits on commas/whitespace). Run → fail.
- [ ] **Step 2:** Migration, models, backend, then pages. Keep every `.tsx` under 300 lines by splitting components. `make gen-i18n`.
- [ ] **Step 3: Verify** `uv run pytest modules/users/tests -q`, `npx vitest run modules/users`, `npx tsc --noEmit -p modules/users/tsconfig.json`, `npx biome check modules/users`, `node scripts/check_untranslated_strings.mjs`, `uv run alembic -c host/alembic.ini check` (or `make doctor` if the app boots in your environment).
- [ ] **Step 4: Commit** own paths, `feat(users): admin users, add people, edit user and profile per the hi-fi deck`.

---

### Task 6: Permissions screens — role edit, user grants

**Files:**
- Modify: `modules/permissions/permissions/pages/{RoleEdit,UserEdit}.tsx`, `modules/permissions/permissions/pages/components/*` (add `GroupCard.tsx`, `PlainStat.tsx` only if `StatCard` without icon does not fit), `modules/permissions/permissions/locales/en.json`
- Tests: `modules/permissions/tests-js/RoleEdit.test.tsx` (filter by key, granted-only), `UserEdit.test.tsx` (badges)
- Evidence: `hifi-gap/permissions-14-15.md`; deck `14`, `15`.

**Interfaces (consumes):** `StatCard`, `ui/checkbox` (`checked="indeterminate"`), `PageShell`.

**Requirements:** every delta in §14.4 and §15.4; rulings: keep header actions (no sticky bar), keep dirty-gating, group names render as the registry's display name with the key prefix as a muted mono tag only when they differ, show both "direct" and "granted by {role}" pills when both apply, multiple roles → "granted by {a}, {b}", rows keep registry order, Cancel → `/admin/users/`, after save stay on the page (change the 303 target only if the current redirect leaves the page — check `endpoints/views.py`; if it redirects to the users list keep it, do not change backend), leave-guard ported from `modules/users/users/pages/Users/Edit.tsx`.

- [ ] **Step 1:** JS tests first → fail. **Step 2:** implement + `make gen-i18n`. **Step 3: Verify** `npx vitest run modules/permissions`, `npx tsc --noEmit -p modules/permissions/tsconfig.json`, `npx biome check modules/permissions`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(permissions): role and grant editors per the hi-fi deck`.

---

### Task 7: Settings screens — store, new override, module settings

**Files:**
- Modify: `modules/settings/settings/pages/{Browse,Create,Edit,ModulesEdit}.tsx`, `modules/settings/settings/pages/components/*` (add `ResolvedValue.tsx`, `ScopeTabs.tsx`, `ModuleFieldRow.tsx` as needed), `modules/settings/settings/endpoints/views.py`, `modules/settings/settings/service.py`, `modules/settings/settings/_module_settings.py` (choices, env meta), `modules/settings/settings/locales/en.json`, `modules/settings/settings/constants.py`
- Tests: `modules/settings/tests/test_store_filters.py`, `test_known_keys_meta.py`, `test_testable_checks.py`; JS `modules/settings/tests-js/{ModuleForm,ScopeTabs}.test.tsx`
- Evidence: `hifi-gap/settings-16-18.md`; deck `16`–`18`.

**Interfaces (consumes):** `SegmentedControl`, `ui/switch`, `ui/select`, `ConfirmActionDialog` (delete override), `useRelativeTime`. **Produces:** `browse` view accepts `scope`, `q`, `page` and returns `settings`, `pagination {page, per_page, total}`, `counts {all, system, tenant, user}`, `filters {scope, q}`; `known_keys[]` gains `env_var`, `env_set`, `default`, `requires_restart`, `is_secret`, `choices`; `testable: dict[str, list[str]]`.

**Requirements:** every delta in §16–§18 with the spec's rulings (keep app IA; server-side filter/search/paging at 20/page; description dropped from the table; secrets stay masked in the Resolved value panel; "env fallback" row shows "not read" when the module declares no env prefix; Reveal is not implemented — the secret row reads "write-only · never returned" with a "Set new value" link; fields stay grouped by their declared `group` (flat when none); last test result kept in `sessionStorage` keyed by package).

- [ ] **Step 1:** Python tests first (scope filter + counts + paging; known_keys meta; testable shape) → fail. **Step 2:** backend, then pages; `make gen-i18n`. **Step 3: Verify** `uv run pytest modules/settings/tests -q`, `npx vitest run modules/settings`, `npx tsc --noEmit -p modules/settings/tsconfig.json`, `npx biome check modules/settings`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(settings): store, new override and module settings per the hi-fi deck`.

---

### Task 8: Feature flags + file storage + destructive confirms

**Files:**
- Modify: `modules/feature_flags/feature_flags/pages/Browse.tsx`, `pages/components/{TenantPicker,ToggleConfirmDialog}.tsx`, `modules/feature_flags/feature_flags/{module.py,constants.py,locales/en.json}` (register audit links; `MENU_LABEL` "Feature flags")
- Modify: `modules/file_storage/file_storage/pages/Browse.tsx`, `pages/components/*` (add `UploadsCard.tsx`, `SelectionFooter.tsx`), `pages/upload-queue.ts`, `pages/constants.ts`, `modules/file_storage/file_storage/{endpoints/views.py,endpoints/api.py,service.py,settings.py,locales/en.json}`
- Tests: `modules/feature_flags/tests/test_audit_links.py`; `modules/file_storage/tests/test_browse_props.py`, `test_bulk_delete.py`, `test_uploader_filter.py`; JS `modules/file_storage/tests-js/upload-queue.test.ts`
- Evidence: `hifi-gap/flags-files-confirms-19-21.md`; deck `19`–`21`.

**Interfaces (consumes):** `SegmentedControl`, `ConfirmActionDialog`, `useRelativeTime`. **Produces:** `POST /api/file-storage/files/bulk-delete {ids: [...]}` → `{deleted: n}`; browse props `backend`, `used_bytes`, `quota_bytes | null`, `max_file_size_bytes`, `allowed_content_types | null`, `uploaders: [{id, label, count}]`, `filters.uploaded_by`; `StoredFile.uploaded_by_label`.

**Requirements:** every delta in §19–§21 with the spec's rulings (files stay in the app shell; quota segment only when `SM_FILE_STORAGE_QUOTA_BYTES` is set; unrestricted types read "any type"; uploader label resolved from `users.models.User` by `created_by` in the view (lazy import inside try/except, `None` → "—"); failure reasons parsed from the API's JSON `detail`; user-delete dialog is owned by Task 5 — you only restyle flag toggle, file delete here; the task retry dialog is Task 9's).

- [ ] **Step 1:** Python tests first → fail. **Step 2:** implement; `make gen-i18n`. **Step 3: Verify** `uv run pytest modules/feature_flags/tests modules/file_storage/tests -q`, `npx vitest run modules/file_storage modules/feature_flags`, `npx tsc --noEmit -p modules/feature_flags/tsconfig.json` and `-p modules/file_storage/tsconfig.json`, `npx biome check modules/feature_flags modules/file_storage`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(feature_flags,file_storage): deck screens, uploads card, bulk delete, shared confirms`.

---

### Task 9: Background tasks — index, task detail, workers (+ retry confirm)

**Files:**
- Modify: `modules/background_tasks/background_tasks/pages/{Index,Detail,Workers}.tsx`, `pages/components/*` (add `TracebackCard.tsx`, `TaskFilters.tsx`, `WorkerCard.tsx`), `pages/constants.ts`, `modules/background_tasks/background_tasks/{endpoints/views.py,endpoints/api_admin.py,service.py,contracts/schemas.py,worker_inspector.py,locales/en.json}`
- Tests: `modules/background_tasks/tests/test_index_filters.py` (queue filter, success_24h), `test_retry_failed_bulk.py`, `test_detail_props.py` (max_retries), `test_workers_uptime.py`
- Evidence: `hifi-gap/tasks-workers-audit-22-25.md` §22–§24 and `flags-files-confirms-19-21.md` §21 (retry card); deck `22`–`24`, `21`.

**Interfaces (consumes):** `StatCard` (`tone`), `SegmentedControl`, `ConfirmActionDialog`, `useRelativeTime`, `PageShell` (`titleClassName`, `badge`, `mono`, `back`). **Produces:** `POST /api/background_tasks/admin/executions/retry-failed?status=&queue=` → `{queued: n}`; index props `status_counts.success_24h`, `queues: list[str]`, `filters.queue`; detail prop `max_retries`; `WorkerInfo.uptime_seconds`, workers props `broker_url_redacted`.

**Requirements:** every delta in §22–§24 with the spec's rulings (stat tiles stay clickable filters; "Retry all failed" includes stuck, respects the current filter, and confirms through `ConfirmActionDialog`; Worker column dropped; duration "—" until finished; timestamps `d MMM HH:mm:ss`; Copy copies the traceback text; retry dialog says "This one has already been retried {count} time(s)." only when `retries > 0`; offline worker subline "celery {ver} · offline"; start command `uv run celery -A scripts.run_worker:celery worker -l info -Q {queues}`). Phone order on Detail: status strip, two fact cards, traceback, full-width "Retry task" (`lg:hidden`).

- [ ] **Step 1:** Python tests first → fail. **Step 2:** implement; `make gen-i18n`. **Step 3: Verify** `uv run pytest modules/background_tasks/tests -q`, `npx vitest run modules/background_tasks`, `npx tsc --noEmit -p modules/background_tasks/tsconfig.json`, `npx biome check modules/background_tasks`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(background_tasks): executions, detail and workers per the hi-fi deck`.

---

### Task 10: Dashboard, Doctor (real data), Branding

**Files:**
- Modify: `modules/dashboard/dashboard/pages/{Home,Doctor}.tsx`, `pages/components/*` (delete `DemoPlaceholders.tsx` and `doctor-data.ts`; add `doctor/{ChecksCard,MigrationsCard,DevServerCard,TerminalPanel}.tsx`), `modules/dashboard/dashboard/{endpoints/views.py,stats.py,locales/en.json}`, Create `modules/dashboard/dashboard/doctor.py`
- Modify: `framework/hosting/simple_module_hosting/{app_builder.py,migrations.py}` and `framework/core/simple_module_core/services.py` (add `diagnostics: DiagnosticsState` holder — a small dataclass with `results: list[Diagnostic]`, `ran_at`, and a `rerun()` closure — to `Services`), tests `framework/hosting/tests/test_diagnostics_state.py`, `test_migration_listing.py`
- Modify: `modules/branding/branding/pages/Manage.tsx`, `modules/branding/branding/components/*` (add `PreviewTabs.tsx`, `ImageDropzones.tsx`), `modules/branding/branding/{presets.py,locales/en.json}`
- Tests: `modules/dashboard/tests/test_doctor_props.py`, `test_dashboard_month_delta.py`; `modules/branding/tests/test_presets.py`; JS `modules/branding/tests-js/dirty-state.test.tsx`
- Evidence: `hifi-gap/shell-dashboard-doctor-branding-00-09-27-26.md` §09, §27, §26; deck `09`, `27`, `26`.

**Interfaces (consumes):** `StatCard` (`tone`, `suffix`), `SegmentedControl`, `PageShell`. **Produces:** `app.state.sm.diagnostics` (see above); `list_migrations(project_root, current_revision) -> list[{id, module, message, applied}]` in `simple_module_hosting/migrations.py`; Doctor view props `checks`, `migrations`, `dev_server`, `stats {checks_passing, checks_total, modules_loaded, pending_migrations, python_version}`; `POST /admin/doctor/rerun` (admin) re-runs diagnostics and redirects back; dashboard prop `users_created_this_month`.

**Requirements:** every delta in §09/§27/§26 with the spec's rulings: Doctor runs on real data only (delete fixtures); in production (diagnostics skipped at boot) the checks card shows "Diagnostics run in development only" via an empty state; "Fix"/"Generate"/"Apply pending" copy the command to the clipboard (`make migrations` / `make migrate`); dev-server rows come from settings (`vite` from `SM_VITE_DEV_URL`, `api` from the request's port, `worker` from `app.state.background_tasks` last snapshot if present else "—"); Branding presets become the deck's four (emerald `#0f766e`, slate `#475569`, indigo `#4f46e5`, amber `#b45309`) and stage locally (no immediate POST); images still upload on pick; footer editor restyled to the deck (text + link chips + "+ add link"); preview tabs App / Sign-in / Email with the banner in the brand colour only in the preview; dashboard `DemoPlaceholders` removed.

- [ ] **Step 1:** Python tests first → fail. **Step 2:** implement; `make gen-i18n`. **Step 3: Verify** `uv run pytest modules/dashboard/tests modules/branding/tests framework/hosting/tests framework/core/tests -q`, `npx vitest run modules/dashboard modules/branding`, `npx tsc --noEmit -p modules/dashboard/tsconfig.json` and `-p modules/branding/tsconfig.json`, `npx biome check modules/dashboard modules/branding`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(dashboard,branding): dashboard tiles, real-data doctor and branding editor per the hi-fi deck`.

---

### Task 11: Audit log (+ entity labels across modules) — runs after Tasks 3–10

**Files:**
- Modify: `modules/audit_log/audit_log/pages/Browse.tsx`, `pages/components/*` (add `ChangesList.tsx`, `DateRangeField.tsx`), `modules/audit_log/audit_log/{endpoints/views.py,endpoints/api.py,service.py,resolve.py,locales/en.json}`
- Modify: `framework/core/simple_module_core/audit_links.py` (+ `framework/core/tests/test_audit_links.py`): `AuditLink` gains `table_name: str | None = None` and `label_resolver: Callable[[Session, list[str]], Awaitable[dict[str, str]]] | None = None`
- Modify: `register_audit_links` in `modules/{users,settings,background_tasks,feature_flags}/**/module.py` to pass `table_name` and a resolver (users → full_name or email; settings → key; background_tasks → task_name; feature_flags → flag name)
- Tests: `modules/audit_log/tests/test_export_csv.py`, `test_actor_filter_by_name.py`, `test_entity_labels.py`; JS `modules/audit_log/tests-js/ChangesList.test.tsx`
- Evidence: `hifi-gap/tasks-workers-audit-22-25.md` §25; deck `25`.

**Interfaces (consumes):** `ui/calendar` + `ui/popover` for the range, `useRelativeTime` not needed (absolute times). **Produces:** `GET /api/audit-log/export.csv?<same filters>` streaming `text/csv` (columns: time, action, entity_type, entity_id, entity_label, actor, changes as `field: old → new; …`), permission `audit_log.view`; browse props `entries[].entity.display`, `.table_name`.

**Requirements:** every delta in §25.4 with the spec's rulings: type tag = table name; export honours the current filters (all pages); date range is date-only, `to_date` treated as end of day; actor filter accepts a UUID (exact) or text (`ilike` on users' name/email, resolved to ids in the view); the correlation link stays under the Time cell.

- [ ] **Step 1:** Python tests first → fail. **Step 2:** core registry, module hooks, audit_log backend, then page; `make gen-i18n`. **Step 3: Verify** `uv run pytest modules/audit_log/tests framework/core/tests -q`, `npx vitest run modules/audit_log`, `npx tsc --noEmit -p modules/audit_log/tsconfig.json`, `npx biome check modules/audit_log framework/core`, `node scripts/check_untranslated_strings.mjs`. **Step 4: Commit** `feat(audit_log): deck audit screen, CSV export, entity labels`.

---

### Task 12: Integration, full gates, browser verification

**Files:** anything the fix wave needs; screenshots under `qa-shots/hifi/` (gitignored? check `.gitignore`; if not ignored, do not commit them).

- [ ] **Step 1:** `make gen-i18n && make gen-pages`; `make lint`; `make test`; `make doctor` — fix everything.
- [ ] **Step 2:** Start the app from the worktree on non-default ports: `SM_VITE_PORT=5051 npm run dev` and `SM_VITE_DEV_URL=http://localhost:5051 uv run --project host uvicorn host.main:app --port 8001` (after `make migrate`). Bootstrap admin from `.env`.
- [ ] **Step 3:** For every deck screen open the route at 1440×900 and 390×720 with Playwright, compare against `/tmp/hifi/screens/NN-*.html`, record mismatches, fix, re-shoot. Screens and routes: landing `/`; login `/users/login`; register `/users/register` (needs `SM_USERS_ALLOW_SIGNUP=true`); forgot `/users/forgot-password` (+ sent state); reset `/users/reset-password?token=<minted>` (+ expired); verify `/users/verify?token=<expired>`; invite `/users/invite/accept?token=<minted>`; keycloak `/keycloak/login`, `/keycloak/logged-out` (only when `SM_AUTH_PROVIDER=keycloak` — otherwise render the pages through a vitest snapshot instead); errors `/admin` as a non-admin (403), `/nope` (404), a forced 500 via a test route if one exists (else the vitest render); dashboard `/dashboard/`; users `/admin/users/`; add people `/admin/users/add`; edit `/admin/users/<id>`; profile `/users/me`; role `/admin/permissions/roles/<id>/edit`; grants `/admin/permissions/users/<id>/edit`; settings store `/admin/settings/store`; new override `/admin/settings/create`; module settings `/admin/settings/`; flags `/admin/feature-flags/`; files `/file-storage/` (+ delete dialog); tasks `/admin/background-tasks/`; task detail `/admin/background-tasks/<id>`; workers `/admin/background-tasks/workers`; audit `/admin/audit-log/`; branding `/admin/branding/`; doctor `/admin/doctor/`; mobile = dashboard, drawer open, users, task detail at 390px.
- [ ] **Step 4:** Run `make test-e2e` against the running server (`E2E_BASE_URL=http://localhost:8001`). Fix failures.
- [ ] **Step 5:** Commit the fix wave; write the verification summary into the SDD ledger.
