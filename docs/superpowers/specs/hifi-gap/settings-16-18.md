# Hi-Fi deck gap analysis — settings-16-18

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

Analysis complete. All reads were done directly; no files were modified.

# Settings screens — design-vs-implementation gap report

**Cross-cutting IA conflict (decide first).** The deck's nav item "Settings" lands on the raw override table (screen 16, crumb `Settings`), with module forms as a sub-page (screen 18, crumb `Settings / Modules / users`). The app deliberately did the opposite: `/admin/settings/` is the module forms and the raw store was demoted to `/admin/settings/store` (`/home/anto/Repos/simple_module_python/modules/settings/settings/constants.py` lines 50-56, `pages/routes.ts` comments, `endpoints/views.py` lines 73-77). Either revert that decision or keep the app IA and restyle each screen in place. Everything below assumes the latter.

---

## Screen 16 — Settings (raw overrides table)

**1. Route / files.** `/admin/settings/store` → `Settings/Browse` (`endpoints/views.py` `browse()` lines 68-83, props `settings: Setting[]` — full unpaginated list) → `/home/anto/Repos/simple_module_python/modules/settings/settings/pages/Browse.tsx`. Copy in `locales/en.json`.

**2. Deck structure.**
1. Header: h1 "Settings"; subtitle "Database overrides. Precedence: user beats tenant beats system beats env default."; right: outline "Per-module forms", primary "+ New override".
2. Toolbar: segmented scope tabs in a `--sec` container: "All 42" (active, card bg + shadow), "system 28", "tenant 9", "user 5"; flex-1 search box with magnifier, placeholder "Search keys…".
3. Table card (fills remaining height): header grid `90px 2fr 70px 1.4fr 130px` = "Scope", "Key", "Type", "Value", "Actions" (right); uppercase 11px, `--sec` bg.
4. Rows: lowercase scope pill (system `--pri7`/`--soft`; tenant `#2563eb`; user `#b45309`); key in JetBrains Mono, with scope_id as a muted 11.5px sub-line for tenant/user rows ("acme-co", "dana@example.com"); Type as muted short label "str"/"int"; Value in mono, with a 16px colour swatch before `#0f766e`; actions "Edit · Delete" (Edit `--pri7`, Delete `#dc2626`).
5. Footer pinned bottom: "Showing 1–20 of 42" left; "Previous" / "Next" outline buttons right. No empty state, no Description column.

**3. Already matches.** PageShell title + description; two header actions (outline → modules, primary → create); card-wrapped table with 11px uppercase header; scope badges in the same three tones; mono key/value; Edit (primary) / Delete (destructive) right-aligned; empty state (extra).

**4. Deltas.**
1. Copy — `en.json` `browse.description` → "Database overrides. Precedence: user beats tenant beats system beats env default."; `modules.browse_link` ("View module settings", used only in Browse.tsx) → "Per-module forms"; `browse.new_button` → "New override" (Plus icon supplies the "+"). Drop the Box icon on the outline button (Browse.tsx line 59).
2. Missing scope filter tabs with counts — Browse.tsx. `FilterPills` (`packages/ui/src/components/FilterPills.tsx`, exported, currently unused) exists but renders outline pills, not the deck's segmented control; add a `variant="segmented"` or hand-roll. Needs `counts` prop.
3. Missing "Search keys…" input — Browse.tsx; follow `modules/users/users/pages/Users/Index.tsx` lines 82-118 (300 ms debounce, `router.get(..., { preserveState, preserveScroll })`).
4. Missing pagination footer — Browse.tsx + new keys `browse.showing` ("Showing {from}–{to} of {total}"), `browse.previous`, `browse.next`. Users list uses "Page X of Y" (`users.index.page_of`); deck wants range copy.
5. Columns: drop "Scope ID" and "Description" columns (Browse.tsx lines 89-91, 101-103, 115-117, 125-127); render `scope_id` as a sub-line under the key when non-empty.
6. Type cell: app shows "String"/"Integer" uppercase-tracked (`value_types.*`); deck shows muted lowercase "str"/"int". Add `value_types_short.*` keys or change cell class to `text-sm text-muted-foreground`.
7. Scope badge copy: app "System"/"Tenant"/"User" (`scopes.*`, shared with Create's select); deck lowercase. Add `lowercase` class on the badge.
8. Colour swatch for `#rrggbb` values (Browse.tsx line 122-124) — small `isHexColor` check.
9. Card should fill viewport with footer pinned (`mt-auto`); reuse `h-[calc(100vh-var(--app-chrome-h))]` from ModulesEdit.tsx line 41.
10. Actions separator "·" between Edit and Delete (cosmetic).

**5. Backend/props needed.** `browse()` in `endpoints/views.py` must accept `scope`, `q`, `page`, `per_page` and return `settings`, `pagination {page, per_page, total}`, `counts {all, system, tenant, user}`, `filters`. `SettingService` (`service.py`) has `list_all()` and `list_by_scope()` only — add a filtered/paginated query plus a per-scope count (group-by). Mirror `modules/users/users/admin/views.py` lines 42-83 (clamping, page overflow fix).

**6. Ambiguities.** Server- vs client-side filter/search/paging (deck's "of 42" with 20 rows implies server, 20/page). Segmented control vs pill style. Where Description goes (tooltip? dropped?). Whether "str/int" short labels are desired given `value_type` is "string". Swatch rule (any hex string vs `branding.*` keys only). Keep the existing empty state (deck has none). Delete confirmation: app uses `window.confirm`; the deck has a separate "Delete confirm" dialog screen (21) for Files — unclear if Settings should share it.

---

## Screen 17 — New override (Create)

**1. Route / files.** `/admin/settings/create` → `Settings/Create` (`views.py` `create_view()` + `_known_keys()` lines 92-117; prop `known_keys: [{key, type, description, module}]`) → `pages/Create.tsx`, `pages/components/KeyField.tsx`, `pages/components/ValueInput.tsx`. "On edit the key is locked" → `pages/Edit.tsx` at `/admin/settings/{id}/edit`.

**2. Deck structure.**
1. Header: h1 "New override"; subtitle "The value input follows the type. On edit the key is locked." No header action.
2. Grid `1.3fr 1fr`. Left card: (a) row "Scope" select ("system ▾") | "Scope ID" input, placeholder "Leave blank for system scope"; (b) "Key" mono input (focused: `--pri` border + 3px `--soft` ring) with dropdown: header "Registered by modules" (muted, `--sec` bg), rows key-left / meta-right: `users.smtp_host` — "str · env SM_USERS_SMTP_HOST" (highlighted), `users.smtp_port` — "int · default 587", `users.smtp_user` — "str"; (c) row `150px 1fr`: "Type" select ("string ▾") | "Value" mono input ("mail.example.com"); (d) "Description" textarea, 56px, placeholder "Why this override exists."; (e) footer right: outline "Cancel", primary "Save override".
3. Right card: h2 "Resolved value"; three rows — "this override" (pri border, soft bg) → `mail.example.com`; "env fallback" (opacity .7) → `localhost`; "module default" (opacity .7) → `""`; note "Saving takes effect on the next request — no restart needed."

**3. Already matches.** Scope select, Scope ID, Key with autocomplete that also sets the type, Type select, type-driven `ValueInput`, Description textarea, Cancel + submit, muted labels, key unknown-warning (extra). Edit.tsx locks scope/scope_id/key/type via disabled inputs.

**4. Deltas.**
1. Copy (`en.json`): `create.title` "New Setting" → "New override"; `create.head_title` likewise; new `create.description` = "The value input follows the type. On edit the key is locked." passed to PageShell `description` (Create.tsx line 46); `create.submit_button` "Create" → "Save override"; `form.scope_id_placeholder` → "Leave blank for system scope"; `form.description_placeholder` → "Why this override exists.".
2. Remove the duplicate PageShell-level "Cancel" (Create.tsx lines 48-52; same in Edit.tsx 47-51) — deck has Cancel only in the form footer.
3. Layout: single `max-w-2xl` card → `grid lg:grid-cols-[1.3fr_1fr] gap-4 items-start` (Create.tsx line 54).
4. Type|Value row: `sm:grid-cols-2` 50/50 → `grid-cols-[150px_1fr]` (Create.tsx lines 102-134).
5. Suggestion dropdown (KeyField.tsx lines 75-95): add header row "Registered by modules" (new key `form.suggestions_header`); switch rows to `flex justify-between` with meta right: "{type} · env {ENV_VAR}" / "{type} · default {default}" / "{type}" instead of "module · type — description".
6. Missing "Resolved value" panel — new `pages/components/ResolvedValue.tsx` (keeps Create.tsx under the 300-line cap). Rows: "this override" (live form value), "env fallback", "module default"; footer note (new key `create.no_restart_note`). Should flip to a restart warning when the chosen key's field has `requires_restart`.
7. `ValueInput.tsx` uses raw `<input className="border rounded w-full p-2">`/native `<select>` — swap to shared `Input`/`Textarea`/`Select` so radius/ring match the sibling fields; add `font-mono` to the string input (deck value is mono).

**5. Backend/props needed.** Extend `_known_keys()` (`views.py` lines 97-117) with `env_var`, `default` (via `jsonable_encoder`, masked for secrets — `_field_view` in `_module_settings.py` already masks), `env_set`, `env_value` (masked), `requires_restart`, `is_secret`. Also merge `app.state.settings.registry.all_definitions` (`contracts/registry.py` `SettingDefinition` with `default`, `value_type`, `description`) — currently only pydantic module settings are suggested. For tenant/user scopes the panel could also show existing lower-scope overrides via the existing `GET /api/settings/resolve/{key}` (`API_RESOLVE_PATH`, needs `settings.view`, which the page already requires).

**6. Ambiguities.** Meta rule in suggestion rows (env shown only when set? default only when non-empty?). "env fallback" is misleading for bundled modules whose settings classes declare no `env_prefix` and never read `SM_*` (`_module_settings.py` lines 47-58, 130-147) — show "not read", hide, or only show when `env_set`. Secrets in fallback/default rows must stay masked. Whether the panel appears on Edit too. Whether the deck's Value example text is a placeholder or a value.

---

## Screen 18 — Module settings (`users` settings form)

**1. Route / files.** `/admin/settings/` → `Settings/ModulesEdit` (`views.py` `modules_view()` lines 187-228; props `modules: ModuleView[]`, `testable: string[]`; `/admin/settings/modules` 308-redirects) → `pages/ModulesEdit.tsx`, `components/ModuleForm.tsx`, `FieldInput.tsx`, `FieldSource.tsx`, `TestConnectionButton.tsx`. Save `PUT /api/settings/modules/{pkg}`, revert `DELETE /api/settings/modules/{pkg}/{field}` (`endpoints/module_api.py`), test `POST /admin/settings/test-connection/{pkg}`.

**2. Deck structure.**
1. Left aside 230px, `--sec` bg: search "Search modules…"; items = mono package name + sub-line — active `users` "9 fields · 2 overridden" (`--soft` bg, `--pri7` text), others "6 fields" etc. (no icon bubble); bottom link "Browse raw overrides →".
2. Main pane header: h1 `<code>users</code> settings`; subtitle "Generated from the module's declared settings. Env fallback shown per field."; right: muted "2 unsaved" + primary "Save".
3. Card, rows grid `170px 1fr 210px` (label DM Sans 13/500 | control | trailing meta): `mailer` | select "smtp ▾" | mono "SM_USERS_MAILER · console"; `smtp_host` | mono input, pri border + ring | "overridden in DB · Revert" (`--pri7`); `smtp_port` | 120px number "587" | mono "SM_USERS_SMTP_PORT"; `smtp_password` | "••••••••••" with inline "Reveal" | "write-only · never returned"; `from_address` | mono input | "SM_USERS_FROM_ADDRESS"; `allow_signup` | toggle switch | "public /register is closed"; `invite_expiry_days` | 120px number "7", highlighted | "overridden in DB · Revert".
4. Card footer (`mt-auto`, border-top): outline "Test mailer connection" + "✓ Last test succeeded 4m ago" (`--pri7`).

**3. Already matches.** Full-height master/detail, search, mono module names + "N fields", active tint, bottom link to raw store; per-field env-var label + db/env/default source badges (`FieldSource`), masked secrets, number/bool/json controls, reset link, Save (dirty-gated), Test connection with per-check results, 422 error mapping, requires-restart badge, group headings.

**4. Deltas.**
1. Sidebar (ModulesEdit.tsx lines 56-86): show `m.package` not `m.module_name`; append "· {n} overridden" when `fields.filter(f => f.db_override).length > 0` (new plural key `modules.overridden_count`); drop the Box icon bubble; `w-72` → ~`w-[230px]`.
2. Copy: `modules.browse_free_form_link` → "Browse raw overrides →"; `modules.search_placeholder` → "Search modules…"; `modules.description` (stale "Read-only view…", unused) → "Generated from the module's declared settings. Env fallback shown per field."; `modules.source_db` → "overridden in DB"; `modules_form.reset_to_default` → "Revert"; `modules.test_connection` → "Test {name} connection".
3. Header: move out of the Card into the main pane (ModuleForm.tsx lines 105-121 → ModulesEdit.tsx); h1 `<code>{package}</code> settings` (key `modules.heading` "{package} settings"), subtitle, "{count} unsaved" (new plural key) from `modifiedFields.size` — lift dirty state or expose via callback.
4. Row layout (ModuleForm.tsx lines 129-162): 2-col `1fr 2fr` with stacked label/description/badge/source → 3-col `170px 1fr 210px`; label class `font-mono text-xs` → `text-[13px] font-medium`; trailing column = `FieldSource` reworked to: default → mono "ENV_VAR · default"; db → "overridden in DB · Revert" (Revert = `onReset`); secret → "write-only · never returned" (new key); bool → description as hint.
5. Revert visibility bug vs deck: shown when `value != default` (line 127) — appears for env-sourced diffs and hides when a DB override equals the default. Gate on `f.db_override`.
6. Highlight overridden inputs (`border-primary ring-[3px] ring-primary/10` when `db_override`).
7. `FieldInput.tsx`: bool checkbox → `Switch` (`packages/ui/src/components/ui/switch.tsx`); int/float `w-[120px]`; raw `<input>` → shared `Input`/`Textarea`; secret "Set new value" button → inline link inside the box.
8. Enum-like strings (`mailer` has `pattern="^(console|smtp)$"`, `modules/users/users/settings.py` line 64) render as a select in the deck; app has a text input.
9. Test connection: move `TestConnectionButton` from the header to a card footer (`mt-auto border-t pt-4`); name the check; add "✓ Last test succeeded 4m ago" / failure line (new keys + relative time).
10. Groups: deck is flat; app renders `General`, `Google OAuth`, … h3s (users has ~40 fields, deck shows 7 curated).

**5. Backend/props needed.** `testable` → `dict[package, list[check_name]]` (`views.py` `_testable_packages`) so the button reads "Test mailer connection" (`CHECK_MAILER`, `modules/users/users/module.py` lines 246-256). Last-test timestamp/result: nothing persists it today — either sessionStorage client-side or an in-memory map on `app.state.settings`. `choices` per field for select rendering: `_field_view` (`_module_settings.py` lines 150-176) would need to read `info.metadata` pattern or `json_schema_extra["choices"]`. Override counts and defaults are already in props.

**6. Ambiguities.** "Reveal" contradicts the deck's own "write-only · never returned" and the server mask — keep set-new-value semantics, relabel. Where `description` goes (trailing hint vs under label vs tooltip). Flat vs grouped fields. "ENV · default" rule is inconsistent in the deck (`mailer` shows "· console", `smtp_port` omits "· 587"). Whether "2 unsaved" counts dirty fields (likely). Env badge honesty caveat as in screen 17.

---

## Overall ranking (largest gap first)

1. **18 — Module settings**: structural row refactor (2→3 columns), header relocation, Switch/select controls, revert semantics fix, test-connection footer with last-result, several new props. Biggest surface.
2. **16 — Settings table**: three missing features (scope tabs with counts, search, pagination) all needing new backend query/props; column and copy changes are easy.
3. **17 — New override**: mostly copy/layout plus one new panel ("Resolved value") whose data needs `_known_keys` enrichment; smallest gap but has the trickiest semantic question (env fallback honesty).