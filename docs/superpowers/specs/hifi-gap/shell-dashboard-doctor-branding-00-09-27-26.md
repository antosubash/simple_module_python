# Hi-Fi deck gap analysis — shell-dashboard-doctor-branding-00-09-27-26

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

I have everything needed. Here is the gap analysis.

---

# Design-vs-implementation gap analysis: App shell, Dashboard, Doctor, Branding

Repo root: `/home/anto/Repos/simple_module_python` (paths below are relative to it unless absolute). Deck tokens already match the app: `packages/ui/src/styles/globals.css` is themed "Emerald (SimpleModulePython HiFi)" with Sora / DM Sans / JetBrains Mono and a primary ramp anchored on #059669, so nothing below is a token-level delta.

## Cross-cutting finding (fix first)

**Regression: Branding and Feature flags menu entries fell out of the admin sidebar.** PR #274 (2744cf3) set `section=MenuSection.ADMIN_SIDEBAR` on both; the i18n PR #280 (9ad996d) removed the `MenuSection` import, the `section=` line, and Branding's `order=105`:

- `modules/branding/branding/module.py` lines 64–75 — no `section=`, no `order=` → defaults to `SIDEBAR`, order 0, so the **app** sidebar now shows "Appearance › Branding" as its first group.
- `modules/feature_flags/feature_flags/module.py` lines 43–56 — same, lands in app sidebar under "System".

Both pages render in `AdminLayout` (menuKey `adminSidebar`), so their own sidebar no longer lists them: no active highlight, breadcrumb has no section, and `/admin` overview cards omit them. Restore `section=MenuSection.ADMIN_SIDEBAR` (+ `order=105` for Branding) and add a registry test. No test currently asserts the section for either module.

---

## 00 — App shell

**1. Routes/files.** Every authenticated page. `packages/ui/src/layouts/SidebarLayout.tsx` (shell), `AuthenticatedLayout.tsx` (app theme), `AdminLayout.tsx` (red admin theme + "Admin Panel" badge + "Back to App"), `SidebarUserMenu.tsx`, `AdminSectionLink.tsx`; `packages/ui/src/components/{AppTopbar,CommandPalette,LocaleSwitcher,NavIcon,BrandingMark,BrandingFooter,BrandingBanner}.tsx`; menus from `framework/core/simple_module_core/menu.py` + each module's `register_menu_items`; copy `packages/ui/locales/en.json`.

**2. Design structure.**
1. 256px sidebar, `--side` #16191f, 1px white/6% right border.
2. 64px brand row: 30px rounded-9 emerald badge "S" + wordmark "simple_module_py" (Sora 700 14.5px).
3. Nav, padding 16px 12px. Groups "Main" [Dashboard (active), Users, Permissions, Settings], "Operations" [Feature flags, Files, Background tasks, Audit log], "System" [Branding, Doctor]. Group header 11px 700 uppercase .09em #8c93a1. Item: 17px icon, 14px 500 label, padding 10px 12px, radius 10; active = solid `--pri` bg + white; inactive #b7bdc8.
4. User row (top border): 34px circle #2c313b with initials "AD"; "admin" 13.5px; "admin@example.com" 11.5px muted, ellipsis; "▾".
5. 56px topbar, bg card, bottom border, padding 0 28px: crumb 13px muted left ("Dashboard", "Users / dana@example.com"); right: "Search  ⌘K" bordered pill, "EN" bordered pill, "Log out" bordered button.
6. Content fills the rest; no footer inside the frame.

**3. Already matches.** `w-64` near-black sidebar; `h-16` brand row with `BrandingMark`; grouped nav with uppercase muted headers; avatar row with name/email + chevron opening a dropdown; 56px topbar (`--app-chrome-h:3.5rem`) bg-card with 13px breadcrumb (section from registry + PageShell leaf — "Users / admin@example.com" works) and "Search ⌘K" trigger; ⌘K palette; fonts/colours.

**4. Deltas.**
1. *Two shells vs one.* Deck puts Branding/Doctor in the same emerald shell; app splits app sidebar ([Dashboard], "Content" [Files], "Administration" link) and a **red-tinted** admin sidebar ("ADMIN PANEL" badge; "Access" [Users], "Appearance" [Branding], "System" [Feature Flags, Background tasks, Settings, Audit log, Doctor], "Back to App"). Registry-driven, likely keep — but decide whether `AdminLayout.tsx` `THEME` (red `bg-admin-bg`, red accent/badge) should be re-tinted to the deck's charcoal/emerald.
2. *Nav contents/labels.* Deck groups Main/Operations/System, lists Permissions. Registry-driven, likely keep (PR #271 explicitly declined to follow the deck). Label casing: "Feature Flags" (`modules/feature_flags/feature_flags/constants.py` MENU_LABEL / locale) vs deck "Feature flags".
3. *Section regression* — see cross-cutting.
4. *Active item style.* Deck solid `--pri` + white; app `bg-primary-600/15 text-primary-300 border-l-2 border-primary-400` (`AuthenticatedLayout.tsx` THEME.activeClass; red equivalent in `AdminLayout.tsx`). Icons 20px stroke 1.5 (`NavIcon.tsx`) vs deck 17px stroke 1.8.
5. *"Log out" button missing from topbar.* Only reachable via avatar dropdown / ⌘K "Account". Add to `AppTopbar.tsx`, driven by the `userDropdown` POST item (`users.nav.logout` reads "Logout"; deck says "Log out").
6. *"EN" pill.* `LocaleSwitcher.tsx` renders a Globe icon button and returns `null` when `supportedLocales.length <= 1` — host default is `["en"]` (`framework/hosting/simple_module_hosting/host_settings.py:33`), so a default install shows no locale control at all. Deck shows a text pill "EN" always.
7. *Avatar.* Deck two-letter initials on neutral #2c313b; app single initial on `bg-primary-700` / `bg-red-700` with ring (`SidebarUserMenu.tsx:62–66`).
8. *Footer.* App renders `BrandingFooter` ("© 2026 · MIT", Docs/Changelog/GitHub) under every page (`SidebarLayout.tsx:286`); deck frame has none.
9. Minor: topbar `px-6` (24px) vs 28px; "Search" trigger has an icon + `<kbd>`; wordmark `text-lg` vs 14.5px.

**5. Backend/props.** None beyond the `section=` fix.

**6. Ambiguities.** Duplicate vs move "Log out"; what the pill shows with one locale; admin shell colour; whether Permissions ever gets an index page.

---

## 09 — Dashboard

**1. Routes/files.** `/dashboard/` → `modules/dashboard/dashboard/endpoints/views.py::dashboard` → `pages/Home.tsx`, `pages/components/ModuleTile.tsx`, `pages/components/DemoPlaceholders.tsx` (DEV only); data `stats.py`; copy `locales/en.json` `home.*`; shared `packages/ui/src/components/{StatCard,SectionTitle,PageShell}.tsx`.

**2. Design structure.**
1. Padding 30px 34px, gap 22. h1 "Dashboard" (Sora 700 27px); "System overview for this workspace".
2. Four stat cards (radius 14, padding 18px 20px): row 1 = label (13px 500 muted) left, 32px soft-emerald icon square right; row 2 = value (Sora 700 30px) with delta as inline coloured text. "Total users" 128 "+6 this month" (muted) · "Active users" 41 "↑ 7d" (pri7) · "Modules" 12 "all loaded" (muted) · "Health" OK "all good" (pri7).
3. "System" card fills remaining height: h2 "System" + right mono "Python 3.12.4 · 12 modules · all checks healthy". 4-col tile grid (radius 12, padding 14): row 1 mono name + 8px dot (pri / #d97706 / muted); row 2 status "loaded · healthy" | "loaded · degraded" | "loaded · no checks" + action "Open" (pri7) | "No view" (muted). Degraded tile bg `--soft`; no-view tile opacity .55, cursor not-allowed; hover border `--pri`.
4. Nothing else on the page.

**3. Already matches.** PageShell heading; four StatCards with the same icons; Health card logic ("OK"/"{n} alert", "all good"/"see Doctor"); System card with h2 + mono meta; 4-col grid of mono-named tiles with health dots; unreachable tiles rendered inert (permission-aware `menuTarget`).

**4. Deltas.**
1. Copy (`locales/en.json`): `home.description` "Overview of your application" → "System overview for this workspace"; "Total Users" → "Total users"; "Active Users (7d)" → "Active users".
2. `StatCard.tsx` layout is inverted vs deck: icon top-left + delta `Badge` top-right, value, uppercase 11px label underneath. Deck: label top-left, icon top-right, value with delta as plain coloured text. Shared component — change affects Doctor and other modules.
3. Missing deltas: "+6 this month" on Total users (needs backend, see §5); "all loaded" on Modules (static key). Active-users delta is a Badge, deck is inline pri7 text.
4. System meta lacks the third segment "· all checks healthy" (`home.system_meta`); derive from `system_info.health_checks`.
5. `ModuleTile.tsx` is a single row (Box icon + name + 6px dot + hover chevron). Deck is two rows with status text and an explicit "Open"/"No view" label, soft bg for degraded, dimmed not-allowed for no-view, 8px dot, hover border-primary. New keys: `loaded_healthy`, `loaded_degraded`, `loaded_no_checks`, `open`, `no_view`.
6. `DemoPlaceholders.tsx` (Recent activity / Needs attention / Team online, DEV-gated, hardcoded names) is not in the deck; deck's System card takes the full remaining height.
7. Minor: `SectionTitle` accent bar not in deck; grid `gap-2` vs 12px; Card radius 12 vs 14.

**5. Backend/props.** `stats.py`: add `users_created_this_month` (User has `AuditMixin.created_at`, `modules/users/users/models/user.py:32`) and pass through in `views.py`. Everything else derivable client-side. Note the 30s process-wide cache.

**6. Ambiguities.** Meta wording when a check is degraded; "Open" target for partly-admin modules (Users → `/admin/users/`); whether the no-view tile stays a non-link `div` (recommended); delete or keep DemoPlaceholders.

---

## 27 — Doctor

**1. Routes/files.** `/admin/doctor/` → `modules/dashboard/dashboard/endpoints/views.py::doctor` (`admin_router`, `_require_admin`) → `pages/Doctor.tsx`; **all check/migration/dev-server/env rows come from fixtures** in `pages/components/doctor-data.ts`; copy `locales/en.json` `doctor.*`; menu `module.py` (ADMIN_SIDEBAR, System, order 220). Backend that exists: `app.state.migration` = `{current_revision, head_revision, is_current, pending_count}` (`framework/hosting/simple_module_hosting/migrations.py`); `run_diagnostics()` (`framework/core/simple_module_core/diagnostics/_runner.py`) runs **dev-only at boot** and its result is printed then discarded (`app_builder.py:133–140`).

**2. Design structure.**
1. h1 "Doctor"; "The same checks as `make doctor` — static analysis, migrations, dev server, module health." Actions: "Copy report" (outline), "↻ Re-run checks" (primary).
2. Stats (radius 12, label 12.5px, value Sora 25px): "Checks passing" `7` + muted `/ 8`; "Modules loaded" 12; "Pending migrations" 1 as an amber-tinted card (bg rgba(180,83,9,.06), border .35, text #b45309); "Python" 3.12.4.
3. Grid 1.6fr/1fr. Left: "Static checks" — "✓ Orphan pages — every page has a route … pass", "✓ Module metadata complete … pass", warn box "!" "Migration drift in audit_log" / "Model changes are not yet in a migration file. Run `make migrations`." / "Fix"; "✓ Locale consistency across modules … pass"; "✓ Permission registry has no duplicates … pass". Then "Recent migrations" with link actions "Generate" / "Apply pending"; rows `a3f1` `users` add invite table applied · `b7c2` `audit_log` index on entity_type, entity_id pending · `c081` `file_storage` add checksum column applied.
4. Right: "Dev server" + "running" pill; rows `vite :5050`, `api :8000`, `worker celery@w1`. Then a dark terminal panel: "$ make doctor", "checking modules… 12 loaded", "checking pages… 26 routed", "warn: audit_log has unmigrated model changes" (yellow), "✓ 7 of 8 checks passed" (green).

**3. Already matches.** Overall shape: PageShell with two header actions incl. Re-run, 4-stat row, 2:1 grid, Static checks with pass/warn rows, Recent migrations with Generate/Apply and id/module/message/status rows, Dev server with "running", a dark mono panel on the right, AdminLayout.

**4. Deltas.**
1. Data is fictional (STATIC_CHECKS cites `modules/billing/router.py:14`; MIGRATIONS 0021–0024 billing/orders; DEV_SERVER says Vite `:5173` but `Makefile` uses 5050; ENV_VARS). Wire to real data (§5).
2. `doctor.description` → deck sentence with `<code>make doctor</code>`.
3. Actions: "Re-run" + "make doctor" (Terminal icon) → "Copy report" + "↻ Re-run checks". Neither app button has an `onClick`.
4. Stats: "Checks passed" → "Checks passing" with split `7 / 8`; "Modules" → "Modules loaded"; "Pending mig." → "Pending migrations" with a tinted-card variant (add `tone` to `StatCard.tsx`); 4th card "Health" → "Python" (`python_version` already in props). No delta badges in the deck.
5. `CheckRow`: deck pass rows are one line "✓ label … pass"; only warn rows expand into an amber box with helper + "Fix". App renders name + hint + Badge on every row. Deck labels map to SM003/004, SM001, SM011, SM013–016; **no "permission duplicates" diagnostic exists** in `diagnostics/`.
6. Migrations: "Apply" → "Apply pending", link-style actions not ghost icon buttons; drop the "when" column; status as coloured text; 4-char id.
7. Remove "Installed modules" (real data — decide), "Run a command", "Environment" cards; replace with the terminal transcript panel driven by props.
8. Dev server values as mono text, rows `vite / api / worker`.
9. Grid `2fr_1fr` → `1.6fr_1fr` (minor).

**5. Backend/props needed** (new `dashboard/doctor.py` + view props):
- `checks[]` {code, label, status, module, message, suggestion, file} — call `run_diagnostics(modules, migration_state=app.state.migration, i18n_*)` per request or persist the boot result on `app.state.sm`. Note diagnostics are skipped outside development and the AST checks need the source tree.
- `migrations[]` — Alembic `ScriptDirectory.walk_revisions()` (short id, `branch_labels` = module, `doc`, applied = at/below `current_revision`); add to `hosting/migrations.py`. `check_migrations` raises at boot when behind head, so `pending_count` is 0 at runtime — the deck's "Pending migrations 1" is only reachable as SM011 model drift.
- `dev_server` — vite/api ports from settings; worker name needs Celery inspect (background_tasks already polls the fleet; cross-module).
- "Re-run checks" → `router.reload()` if computed per request, or a POST; "Copy report" client-side.

**6. Ambiguities.** Per-request analysis cost vs boot snapshot; what "Fix" does; whether "Generate"/"Apply pending" execute Alembic from a web request (risky) or copy commands; "Dev server" panel in production; what "/ 8" counts; "Copy report" format.

---

## 26 — Branding

**1. Routes/files.** `/admin/branding/` → `modules/branding/branding/endpoints/views.py::manage` → `pages/Manage.tsx`; `components/{BannerField,BrandingPreview,DesignPackField,ImageField,PresetField}.tsx`; API `endpoints/api.py`; `settings.py`, `presets.py`, `shared_props.py`; copy `locales/en.json` `manage.*`.

**2. Design structure.**
1. h1 "Branding"; "Name, colour, logos, banner and footer — applied to every page, including the anonymous ones." Right: "4 unsaved changes" (amber), "Discard", "Publish branding".
2. Grid 1.15fr/1fr. Form card (no header): row "App name" ("Acme Admin") + "Primary colour" (38px swatch + mono "#0f766e"); "Presets" chips emerald #0f766e (active), slate #475569, indigo #4f46e5, amber #b45309; "Announcement banner" input ("Maintenance window Sunday 02:00–04:00 UTC") + "info ▾"; "Logo · dark logo · favicon" three dashed dropzones (1fr 1fr 92px): "logo.svg ✕", dark "upload", "ico"; "Footer" input "© 2026 Acme Corp" + chips "Privacy · /privacy ✕", "Status · status.acme.co ✕", "+ add link"; foot: "One Publish applies text, images and footer together." · "Design pack: emerald ▾".
3. "Live preview" card with segmented [App | Sign-in | Email]; frame = banner strip in the primary colour, 74px mini sidebar ("Acme", one active bar), 22px topbar strip, heading + 3 cards + primary button, footer strip "© 2026 Acme Corp · Privacy · Status"; caption "Preview covers the app shell, the sign-in card and transactional email headers — no reload needed to see a change."

**3. Already matches.** Title; form + preview two-column in AdminLayout; app-name input; swatch + mono hex; preset chips with dots; banner input + severity select; logo / dark logo / favicon slots with dark surface for the dark logo; design-pack selector; live preview from form state with banner, mini sidebar (real menu labels), content mock + primary button.

**4. Deltas.**
1. `manage.description` → deck sentence (only mention "footer" if 8 is accepted).
2. No dirty count / "Discard" / "Publish branding" in the header; app has one "Save changes"/"Saving…" at the bottom. Add dirty tracking vs props in `Manage.tsx`, use PageShell `actions`, keys `unsaved_changes_one/_other`, `discard`, `publish`.
3. `Manage.tsx:140–143` repeats title + description in `CardHeader`; deck has none.
4. Grid `lg:grid-cols-3` (2:1) → `lg:grid-cols-[1.15fr_1fr]`.
5. App name + Primary colour side by side; label "Application name" → "App name"; deck has no per-field helper texts (app has six) and no "Remove" ghost next to the colour.
6. Presets: deck 4 lowercase chips; app 7 Title-case (`presets.py`, values #10b981/#6366f1/#f59e0b/#64748b differ from deck). Active style `border-foreground bg-secondary` vs deck `--pri` border + soft bg. Deck stages presets into "unsaved changes"; app POSTs immediately (`PresetField.tsx` comment says deliberate).
7. Images: three stacked `ImageField` rows (thumbnail + Upload/Replace/Remove + help) vs one row of three dashed dropzones with inline ✕. Deck's "logo.svg" is invalid — SVG is rejected server-side (`images.py`).
8. **Footer editor absent.** Implemented in #237 and removed in #273/#275 ("fix: remove footer from the branding" — `FooterEditor.tsx`, `contracts/footer.py`, settings fields, shared prop all deleted). Footer is hardcoded in `packages/ui/src/lib/brand.ts` (Docs/Changelog/GitHub, "© {year} · MIT"). Reviving is a full feature; needs a product decision.
9. Design pack: full labelled Select mid-form → compact "Design pack: emerald ▾" in the form foot; keep "None (base tokens)".
10. "One Publish applies text, images and footer together." implies staged uploads; app uploads on file pick with a `router.reload()` each.
11. Preview: "Preview" → "Live preview"; add App/Sign-in/Email tabs (Sign-in and Email mocks are new); add topbar strip and footer strip; banner in deck uses the brand colour whereas `BrandingBanner.tsx`/`BrandingPreview.tsx` use semantic severity colours (documented as deliberate); add the caption; second logo tile not in deck.
12. Three "emerald" defaults: deck `--pri` #059669, deck example #0f766e, app `DEFAULT_SWATCH`/preset #10b981 (`Manage.tsx:24`, `presets.py:55`).
13. Menu section regression (cross-cutting).

**5. Backend/props.** Footer text + links (settings, DTO, PUT, shared prop, `BrandingFooter` consumer) only if 8 is accepted; staged presets need `PresetField` to set local state; Sign-in/Email previews need no new props.

**6. Ambiguities.** Stage vs apply-now for presets and images (and what "Discard" does to an uploaded image); banner colour = brand vs severity; keep helper texts; footer revival vs update the deck; what the "Email" tab shows.

---

## Overall summary (largest gap first)

1. **Doctor** — entire screen runs on fixtures; needs a diagnostics/migrations/dev-server backend, restructured cards, tinted stat variant, terminal transcript, and copy rewrite.
2. **Branding** — footer editor was deliberately removed (product call), plus publish/discard/dirty flow, dropzone images, staged presets, preview tabs, and the menu-section regression.
3. **Dashboard** — moderate: shared `StatCard` layout inversion, two-row `ModuleTile` with status/action copy, "+N this month" stat, meta segment.
4. **App shell** — small: solid active nav, topbar "Log out" + always-visible locale pill, two-letter neutral avatar, footer presence, and whether the red admin theme stays.
5. **Do first, cross-cutting** — restore `section=MenuSection.ADMIN_SIDEBAR` in `modules/branding/branding/module.py` and `modules/feature_flags/feature_flags/module.py` (dropped by 9ad996d), unify the emerald default, and change `StatCard` once since three screens depend on it.