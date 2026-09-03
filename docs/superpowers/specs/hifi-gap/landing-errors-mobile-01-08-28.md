# Hi-Fi deck gap analysis — landing-errors-mobile-01-08-28

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

Gap analysis complete. All findings below are read-only; no files were modified.

Repo root for every path below: `/home/anto/Repos/simple_module_python/`. Deck files: `/tmp/hifi/screens/{01-landing,08-errors,28-mobile}.html`, data in `/tmp/hifi/script.js`.

---

## 01 — Landing

**1. Route / files**
- `GET /` → `host/routes.py::landing` → `inertia.render("Landing", {"isAuthenticated"})`
- `host/client_app/pages/Landing.tsx` (wrapped in `PublicLayout`), `host/client_app/components/CopyCommand.tsx`
- `packages/ui/src/layouts/PublicLayout.tsx` (nav), `packages/ui/src/components/BrandingFooter.tsx` + `packages/ui/src/lib/brand.ts` (footer links)
- Copy: `host/locales/en.json` → `landing.*`; nav labels `packages/ui/locales/en.json` → `public_nav.*`

**2. Deck structure**
1. Sticky nav: emerald 32px "S" tile + wordmark `simple_module_py` · right: `Docs` `Modules` `GitHub` | divider | bordered chip `EN` | outline button `Sign in` (→ dashboard).
2. Hero (two blurred blobs, pri @ .13 top-right, pri8 @ .13 mid-left): pill `✦ Batteries-included Django + Inertia starter`; h1 60px Sora `Modular Python apps,` / gradient line `assembled not glued`; sub `Every feature is a self-contained module with its own routes, migrations, permissions and Inertia views. Drop one in, and the host wires it up on boot.`; buttons: primary `Scaffold a project` (href `#quickstart`), outline `Read the docs`; 560px dark terminal strip `$ uvx --from simple_module_cli smpy new my-app` with text button `Copy` → `✓ Copied` (emerald, 1.6 s); helper line `No account needed to run it locally. Sign-in is only for the hosted admin UI.`
3. Features (secondary bg): eyebrow `How it works`; h2 `One process · many modules · zero glue.`; 3×2 cards (icon tile, h3 17px, desc 14.5px; hover = border pri + shadow-lg):
   `Schema-first` / `Each module declares its models, routes and permissions in one place; the host reads that declaration on boot.` · `Module system` / `Drop a package into modules/ and its URLs, migrations and menu entries register themselves.` · `Inertia views` / `React pages served straight from Python views. No separate API layer to keep in sync.` · `Devtools` / `make new-module scaffolds a working module, complete with tests and a page shell.` · `Auth included` / `Email and cookie sessions, invites, password reset and optional Keycloak SSO out of the box.` · `Diagnostics` / `Every module can register health checks; make doctor and the Doctor screen report on all of them.`
4. `#quickstart` (1fr / 1.2fr): eyebrow `Quickstart`; h2 `Working app in five commands.`; body `Land on http://localhost:8000 with users, dashboard and permissions pre-wired. Sign in with the admin account you bootstrap and go from there.`; check-list `users` — `Email + cookie sessions via fastapi-users`, `dashboard` — `Authenticated home with module tiles`, `permissions` — `Per-module permission registry`; terminal window (3 dots, `~/my-app — bash`) with 5 numbered steps, comments grey, `✓` lines emerald.
5. CTA strip: gradient card, h3 `Already running it?`, p `Open the admin UI to manage users, modules and background tasks.`, white button `Sign in to the admin UI`, white-outline `GitHub →`.
6. Footer: `© 2026 simple_module_py` · `Docs` `Changelog` `License`.

**3. Already matches** — section order and skeleton are 1:1 (blobs, badge, two-line gradient h1, two CTAs, CopyCommand, 6 feature cards with the same icon assignments, quickstart split with identical checklist and terminal text, gradient CTA strip, footer). Fonts already configured in `packages/ui/src/styles/globals.css`.

**4. Deltas**
1. Badge copy: impl `v0.1 · Python 3.12 · experimental` → deck `✦ Batteries-included Django + Inertia starter` (see ambiguity re "Django"). `en.json landing.badge`.
2. h1: impl `Modular monoliths for Python —` / `without the boilerplate.` → `Modular Python apps,` / `assembled not glued`. `en.json hero_title_line1/2`.
3. Subtitle differs entirely. `en.json hero_subtitle`.
4. Primary CTA: impl `Start your project` + Rocket icon → auth/dashboard route; deck `Scaffold a project` → in-page `#quickstart`, no icon. `en.json cta_get_started` + href in `Landing.tsx:110-115`.
5. `Read the docs` label matches; impl adds BookOpen icon (deck none). `Landing.tsx:116-121`.
6. CopyCommand: deck shows a visible text label `Copy` / `✓ Copied`; impl is icon-only + sr-only text. Add visible label in `CopyCommand.tsx:56-72` (keys `copy_command`="Copy command"/`command_copied`="Copied" exist; deck wording is shorter). Keep impl's wrapping — the deck's `nowrap; text-overflow:ellipsis` is exactly the mobile regression the component's docstring fixed.
7. Missing helper line under the terminal (`No account needed to run it locally…`). Add to `Landing.tsx` after line 124 + new key.
8. All six feature titles/descs differ (impl: `Per-module schema`, `Discovered at boot`, `Inertia + React`, `Async SQLModel`, `Built-in auth`, `make doctor`). Keys map 1:1 in `en.json landing.features.*`.
9. Card hover: impl `hover:border-primary-200`; deck full-primary border + `shadow-lg`. `Landing.tsx:143`. Card text sizes 16/14 vs deck 17/14.5 (minor).
10. Terminal `pre`: deck greys the `# n.` comment lines; impl renders the whole `QUICKSTART` template literal in slate-200. Split comments into muted spans, `Landing.tsx:24-35, 210-215`.
11. CTA strip: impl heading `Ready to ship modules?` → `Already running it?`; impl body has three auth-state variants → deck single `Open the admin UI to manage users, modules and background tasks.`; impl primary `Open Dashboard`/`Sign up`/`Log in` → deck `Sign in to the admin UI`; `GitHub →` label matches but deck styles it as a white outline, impl `ghost`. `en.json cta_*`, `Landing.tsx:221-256`.
12. Nav: deck single outline `Sign in`; impl `Log in` + conditional `Sign up`, or `Open Dashboard` when authed (`PublicLayout.tsx:73-88`). Deck locale control is a bordered `EN` chip; impl `LocaleSwitcher` is a Globe icon and returns `null` with one locale (`LocaleSwitcher.tsx:41`). Deck nav is opaque; impl is `bg-background/80 backdrop-blur` (cosmetic).
13. Footer: impl shows logo mark + app name + caption `© 2026 · MIT` and links `Docs · Changelog · GitHub`; deck `© 2026 simple_module_py` and `Docs · Changelog · License`. `BRAND_FOOTER_LINKS` in `brand.ts:45-49` (shared with the app shell — changing it affects both). Labels there are untranslated literals (documented blind spot).
14. Quickstart body: impl has an Oxford comma (`users, dashboard, and permissions`); deck doesn't. Trivial.

**5. Backend/props** — none needed. Note `host/routes.py:31` passes a page prop `isAuthenticated` that `Landing.tsx` never reads (it uses shared `auth.isAuthenticated`) — dead prop. If the deck's single "Sign in" CTA is adopted, the `signup.allowed` three-way branching can collapse.

**6. Ambiguities** — (a) "Django" in the badge is wrong for a FastAPI product; almost certainly a deck typo. (b) Should the primary CTA stay auth-aware or be a pure `#quickstart` anchor as drawn? (c) Deck never shows "Sign up" — hide it, or keep the `signup.allowed` conditional? (d) Is `EN` a switcher (always visible) or static? (e) `License` link target unspecified. (f) `Read the docs` href not given (impl → repo README).

---

## 08 — Error screens

**1. Route / files**
- No dedicated route. `framework/hosting/simple_module_hosting/_error_handlers.py::render_error_page` renders page `Error` for statuses `{401,403,404,419,422,429,500,503}` (`_INERTIA_ERROR_STATUSES`), from `http_exception_handler`, `not_found_error_handler`, `request_validation_error_handler`, `unhandled_exception_handler`. Props: `status`, `message`, `correlation_id` (uuid4 hex, from `_observability.py:49`), `login_url` (401/419 only), `maintenance`.
- `host/client_app/pages/Error.tsx` (no layout — full-bleed even when signed in), `packages/ui/src/components/ErrorScreen.tsx`, `packages/ui/src/components/CopyableId.tsx`.
- Copy: `host/locales/en.json error.*`; badge `packages/ui/locales/en.json errors.http_badge` = `HTTP {code}`.

**2. Deck structure** — deck caption: `One component. The status picks the numeral, the message and the single action offered.` Each is a centred bordered card (`--card`, radius 14, padding 40, shadow), 14px gap:
- **403**: numeral `403` 64px Sora, amber `#b45309`; h2 `No access`; p (max 280px) `Your role doesn't include <code>settings.manage</code>. Ask an admin to grant it.`; primary `Go home` (→ dashboard) + outline `Go back`.
- **404**: numeral in `--pri7`; `Not found`; `That page or record doesn't exist. It may have been deleted.`; `Go home` / `Go back`.
- **500**: numeral red `#dc2626`; `Something broke`; `The server hit an error. Quote this id if you report it.`; mono chip (sec bg, radius 8) `req_7f4c19ab · copy`; `Go home` / `Retry`.

**3. Already matches** — single `ErrorScreen` component; accent mapping 403→warning, 404→primary, 500→destructive is identical; numeral/title/description/actions order; correlation id with click-to-copy; Go home + Go back present; Sora display font.

**4. Deltas**
1. Numeral colour: `ErrorScreen.tsx:55-63` always uses a fixed emerald gradient regardless of `accent`; deck colours the numeral per status. Use `ACCENT_COLOR[accent]` (the blob already does).
2. Numeral size: impl `clamp(72px,12vw,120px)` vs deck 64px. `ErrorScreen.tsx:59`.
3. Impl renders an `HTTP 403` pill above the numeral (`ErrorScreen.tsx:45-54`); deck has none.
4. Container: deck is a bordered card; impl is a full-viewport page with an accent blob and no card. `ErrorScreen.tsx:37-44`.
5. Titles: impl `Forbidden` / `Page Not Found` / `Server Error` → `No access` / `Not found` / `Something broke`. `en.json error.forbidden_title, not_found_title, server_error_title`. Deck h2 is 21px; impl 2xl/3xl.
6. Descriptions: 403 impl `You don't have permission to access this page.` → deck names the missing permission in `<code>`; 404 impl `The page you're looking for doesn't exist or has been moved.` → `That page or record doesn't exist. It may have been deleted.`; 500 impl `Something went wrong on our end. Please try again later.` → `The server hit an error. Quote this id if you report it.` Note `Error.tsx:101` prefers the server `message` over catalog copy — e.g. `/admin` 403 shows `Administrator access required`, so the catalog text is only a fallback.
7. Button case: impl `Go Home` / `Go Back` → deck `Go home` / `Go back` (`en.json error.go_home/go_back`). Deck buttons have no icons; impl uses Home + LifeBuoy (`Error.tsx:141-150`).
8. 500 secondary action: deck `Retry` instead of `Go back`. Add status-conditional secondary + key `error.retry` in `Error.tsx`.
9. Correlation chip: deck only on 500, one mono chip reading `req_7f4c19ab · copy` (8-char id + inline "copy"); impl shows on every status, with a label line `Reference this ID if you contact support` above and a bordered chip containing the full 32-char hex + copy icon (`Error.tsx:118-131`, `CopyableId.tsx`). Use `CopyableId label={id.slice(0,8)}`; gate `details` on `status >= 500` if following deck; drop/shorten the label line.
10. `Go home` target: deck → dashboard; impl → `/` (`Error.tsx:142`). Shared `auth` props are available on the error page (`_error_handlers.py:136-138`), so it can be `/dashboard/` when authenticated.
11. Description measure: deck 14px/1.7 max 280px; impl `text-base max-w-md`.

**5. Backend/props needed** — To render `Your role doesn't include <code>settings.manage</code>`, the page needs the missing permission name; today only a free-text `message` arrives. Add e.g. `required_permission` to the render props in `_error_handlers.py:143-154`, populated from the permission-guard dependency (via `request.state` or structured `HTTPException.detail`). `Retry` is client-only (`router.reload()`/`location.reload()`). Short id and `req_` prefix are presentational.

**6. Ambiguities** — (a) caption says "single action" but every card has two buttons. (b) 403s are not always permission-based (role-gated `/admin`), so the `<code>` sentence needs a fallback. (c) `req_` prefix vs raw uuid; is `· copy` a label inside one chip-button or a separate control? (d) Show the id on 403/404 (impl) or 500 only (deck)? (e) 401/419/422/429/503/maintenance are not drawn — extend the deck rules to them. (f) Should a signed-in user's error page sit inside the sidebar shell (neither does today)?

---

## 28 — Mobile

**1. Route / files** — Deck caption: `Sidebar becomes a drawer; tables become cards. 390px wide, 44px minimum hit targets.` Four 390×720 frames map to:
- **Dashboard** → `/dashboard/`, `modules/dashboard/dashboard/pages/Home.tsx` + `components/ModuleTile.tsx`, `packages/ui/src/components/StatCard.tsx`, `AuthenticatedLayout`.
- **Drawer (open)** → `packages/ui/src/layouts/SidebarLayout.tsx` (mobile bar lines 128-167, overlay 169-177, `aside` 179-275), `SidebarUserMenu.tsx`, `AdminSectionLink.tsx`, themes in `AuthenticatedLayout.tsx`/`AdminLayout.tsx`.
- **Users list** → `/admin/users/`, `modules/users/users/pages/Users/Index.tsx`, `modules/users/users/admin/components/{UserRow,IndexFilters}.tsx`, `AdminLayout`.
- **Task detail** → `/admin/background-tasks/{id}`, `modules/background_tasks/background_tasks/pages/Detail.tsx`, `AdminLayout`.

**2. Deck structure**
- **Shell**: dark `#16191f` status bar (`9:41`, `▮▮▮` — device chrome, ignore) + 56px dark app bar: left `☰` (or `‹` on detail), centre-left page title in Sora 15 bold white (mono 14 for `generate_thumbnail`), right contextual slot: avatar `AD` (dashboard), emerald text action `+ Add` (users), nothing (detail). **No bottom nav, no breadcrumb, no locale control, no search.**
- **Drawer**: full-width dark panel replacing the screen; bar `✕` + `Acme Admin`; groups `Main` → `Dashboard` (active: solid `--pri` bg, white, radius 10), `Users`, `Permissions`, `Settings`; `Operations` → `Files`, `Background tasks`, `Audit log`. Items 15px/500, `13px 12px` padding (~46px rows), **no icons**. Pinned footer: avatar `AD` 34px + `admin` / `admin@example.com`.
- **Dashboard**: 2×2 stat cards, label above value (`Total users` 128, `Active 7d` 41, `Modules` 12, `Health` `OK` in pri7), label 12px muted, value 22px Sora. Card `System` → 2-col tiles: mono name + 7px dot only (`users`, `settings`, `audit_log` emerald; `bg_tasks` amber).
- **Users**: search box `Search…`; pills `All` (solid fg/bg inversion) `Active` `Invited` (outline); user cards: 40px initials avatar, email 14px/500, meta 12.5px `admin · active · 2h ago` / `editor · unverified` (amber) / `viewer · active · 3d`, trailing `›`.
- **Task detail**: row `failed` pill (red on red/10) + `attempt 2 of 3`; 2-col cards `Queue`→`media`, `Duration`→`12.4s`; dark `#0f172a` traceback block (`Traceback` grey, `file_storage/tasks.py:88`, `UnidentifiedImageError` salmon); full-width 50px primary `Retry task` at bottom.

**3. Already matches** — 56px dark mobile bar with hamburger (`h-[var(--app-chrome-h)]`=3.5rem); left-sliding drawer with scrim and `✕`; grouped nav; pinned user row with avatar/name/email at drawer foot (`SidebarUserMenu`); `AppTopbar` hidden below `lg`; no bottom nav; dashboard stats already `grid-cols-2` on phones and System tiles `grid-cols-2`; PageShell stacks title/actions on mobile; `FilterPills` and `relative-time` helpers already exist in `packages/ui`.

**4. Deltas**
1. **Bar title**: deck puts the page title in the bar; impl puts `BrandingMark` (app name) there and the title only in the PageShell h1. `SidebarLayout.tsx:154-161` — `usePageHeading(currentUrl)` is already available from `PageHeadingProvider`; render it, and let the brand live in the drawer header only.
2. **Bar right slot**: deck = avatar / `+ Add` / none; impl = `LocaleSwitcher` (`SidebarLayout.tsx:164-166`). Needs an actions slot reported from `PageShell` through `page-heading.tsx` context (compact label like `+ Add`), and locale relocated to the drawer footer.
3. **Back chevron** on detail pages (`‹` instead of `☰`): impl always hamburger. `PageShell.section` could double as the back target; `SidebarLayout.tsx:132-153`.
4. **Drawer geometry**: deck full-screen (390px) panel, header `✕ + app name`; impl 256px `w-64` side panel over a `bg-black/60` scrim (`SidebarLayout.tsx:181`). Change to `w-full sm:w-64` or similar.
5. **Hit targets (44px rule)**: nav rows are `py-2.5 text-sm` (~40px, `SidebarLayout.tsx:237`); hamburger/close/locale are `icon-sm` (32px); `Button size="sm"` is 32px, default 36px (`packages/ui/src/components/ui/button.tsx:21-28`). Deck rows ~46px, CTA 50px. Add `min-h-11` on `<lg` for nav rows and mobile-bar controls; consider `size="lg"` (40px) or a `min-h-11` override for primary mobile CTAs.
6. **Active item style**: deck solid emerald pill, white text, no icons, 15px; impl tinted `bg-primary-600/15 text-primary-300 border-l-2` with icons, 14px. `activeClass` in `AuthenticatedLayout.tsx:10` / `AdminLayout.tsx:11` (admin is red-tinted); icons in `SidebarLayout.tsx:242`.
7. **Drawer IA**: deck has one drawer with `Main` (Dashboard, Users, Permissions, Settings) + `Operations` (Files, Background tasks, Audit log). Impl has two menus: main sidebar = Dashboard, Files (`file_storage`, group `Content`) + `Administration` link; admin sidebar = `Access`→Users, `Appearance`→Branding, `System`→Settings, Feature flags, Background tasks, Audit log, Doctor + `Back to App`. No `Permissions` menu item exists (permissions lives under Users). Group labels come from `ui.nav_groups.*`. This is an IA decision, and the deck contradicts the `/admin` split CLAUDE.md mandates — recommend keeping the split and only restyling.
8. **Avatar initials**: deck two letters (`AD`, `DR`); impl single initial (`SidebarUserMenu.tsx:64`, `UserRow.tsx:20-26`). Minor.
9. **Dashboard stats**: `StatCard.tsx` renders icon + delta badge on top, 26px value, then 11px uppercase label *below*; deck: 12px label *above*, 22px value, no icon/badge. Labels differ: `Total Users`/`Active Users (7d)` vs `Total users`/`Active 7d` (`modules/dashboard/dashboard/locales/en.json`). Deck `OK` in emerald; impl plain.
10. **System tiles**: `ModuleTile.tsx` shows Box icon + name + dot + hover chevron; deck name + dot only. Hide icon `<sm`.
11. **Users list on phones**: impl keeps a `<Table>` and hides Role/Status (`hidden sm:table-cell`) and Last seen (`hidden lg:table-cell`, `UserRow.tsx:67-82`), so on a phone a row is avatar + name + email + pencil — role, status, last-seen are simply gone, not folded. Deck folds them into a meta line `role · status · 2h ago` on a fully tappable card with `›`. Fix in `UserRow.tsx` (meta line `sm:hidden`, row-as-link) or a card list branch in `Index.tsx:201-247`; use `packages/ui/src/lib/relative-time.ts`.
12. **Users filters**: impl search `Input` + three `Select`s (Status/Role/Verified, `IndexFilters.tsx`) + `Tabs` (Users/Roles) + `UserStats` 4 cards; deck search + pills `All / Active / Invited` and no stats/tabs. Swap to `FilterPills.tsx` below `sm`; decide whether `UserStats`/Tabs hide on mobile. Deck `Invited` = impl `verified=no` (the `StatusBadge` already labels this "Invited").
13. **`+ Add`**: impl renders full `Add people` button under the title via PageShell `actions`; deck moves it into the bar. Depends on delta 2; needs a short label key.
14. **Task detail**: impl = title + `Task execution {id}` + `Back to tasks`/`Retry task` `size="sm"` (32px) top-right, then Details card (10 `dl` rows), Args/Kwargs/Result/Traceback in light `bg-muted` `<pre>`s (`Detail.tsx:121-206`). Deck = status pill + `attempt 2 of 3`, two fact cards (Queue, Duration), dark slate traceback with coloured lines, full-width bottom `Retry task`. Reorder for `<lg`: status strip first, 2-col facts, traceback, bottom CTA (`sm:hidden` mirror of the dialog trigger). Task name is mono in the deck bar (delta 1).
15. **Admin bar colour**: deck `#16191f` for all screens; impl uses red-tinted `bg-admin-bg` on admin screens (`AdminLayout.tsx:7`). Decide.
16. **Locale on mobile**: deck none; impl keeps it in the bar (comment at `SidebarLayout.tsx:162-163` explains why). Move to drawer footer if the bar gains a title/action slot.

**5. Backend/props needed**
- Task detail `attempt 2 of 3`: `Execution` has `retries` but no `max_retries`; add to the view props/DTO in `modules/background_tasks`. `Duration` is computable client-side from `started_at`/`finished_at`.
- Users cards: role, status, `last_login_at` all already in `UserListItem` — no backend change.
- Bar title/action/back: frontend-only via `page-heading.tsx` context.

**6. Ambiguities** — (a) merge main + admin drawers as drawn, or keep the split? (b) `Acme Admin` = `branding.appName`? (c) `Invited` pill → `verified=no` or `status`? (d) whole user card tappable → `/admin/users/{id}`? (e) `attempt N of M` semantics (retries+1 of max+1?) and `12.4s` formatting; (f) should the dark traceback style also apply on desktop? (g) 44px targets — global button sizing change or mobile-only overrides? (h) admin bar colour neutral vs red-tinted.

---

## Overall summary (largest gap first)

1. **28 Mobile** — largest: bar needs page title + action/back slot instead of brand+locale, drawer full-width with pill-active/no-icon rows and 44px targets, users table must fold to cards (role/status currently vanish on phones), task detail needs a mobile-first reorder plus a `max_retries` prop; drawer IA in the deck conflicts with the mandated app/admin split.
2. **01 Landing** — medium: structure already 1:1; the work is ~15 copy swaps in `host/locales/en.json` (badge, h1, subtitle, all six features, CTA strip), a missing helper line, visible `Copy`/`✓ Copied` label, grey terminal comments, and nav/footer decisions (`Sign in` single button, `EN` chip, `License` link).
3. **08 Errors** — small/medium, all in two files: `ErrorScreen.tsx` (per-status numeral colour — currently always emerald — 64px size, card container, drop `HTTP n` pill) and `Error.tsx`/`en.json` (sentence-case titles/buttons, new descriptions, `Retry` on 500, short `req_` id chip only on 500, home → dashboard); the 403 permission-name sentence needs a new `required_permission` prop from `_error_handlers.py`.
4. Cross-cutting: `BRAND_FOOTER_LINKS` and `StatCard` are shared by public and app shells, so deck-driven changes there ripple beyond these three screens.
5. Nothing in the deck requires new routes; the only backend additions are `required_permission` (403) and `max_retries` (task detail).