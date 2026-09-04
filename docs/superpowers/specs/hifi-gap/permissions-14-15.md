# Hi-Fi deck gap analysis — permissions-14-15

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

I have everything I need. Here is the gap analysis.

---

# Screen 14 — `14-role.html` "Edit role: editor"

## 1. Route + files
- View: `GET /admin/permissions/roles/{role_id}/edit` → `Permissions/RoleEdit`; save: `PUT /admin/permissions/roles/{role_id}` (303 → `/admin/users/`). Both in `/home/anto/Repos/simple_module_python/modules/permissions/permissions/endpoints/views.py`.
- Page: `/home/anto/Repos/simple_module_python/modules/permissions/permissions/pages/RoleEdit.tsx` (props `{ role: {id,name,description}, assigned: string[], groups: {name, permissions[]}[] }`).
- Copy: `/home/anto/Repos/simple_module_python/modules/permissions/permissions/locales/en.json` (`edit.*`, `filters.*`).
- Entry link: `modules/users/users/admin/components/RolesTab.tsx` (pencil icon).

## 2. Design structure (deck, top → bottom)
1. Header: h1 `Edit role: editor` (Sora 27px); subtitle `Can manage content and invite people, but not change system settings.` (= role description, muted).
2. Header actions, in order: `Reset` (outline, muted text), `Cancel` (outline), `Save role` (filled primary, bold). No icons, all enabled.
3. Toolbar row: 280px search with placeholder `Filter modules or permissions…`; outline pill button `Granted only`; right-aligned `**9** of 24 granted` (number bold, rest muted) + 130×6px progress bar, flat `--pri` fill (38%).
4. Content: **2-column grid** (`repeat(2,1fr)`, gap 14) of module cards, radius 13px, shadow. Card header (bg `--sec`): a 17px **tri-state checkbox** (`–` = partial, `✓` = all, empty = none), module name in JetBrains Mono (`users`, `file_storage`, `settings`, `audit_log`), right muted count `2 / 4` (spaces around slash).
5. Card body: 2-column grid of rows: 34×20 pill switch (primary when on; `--sec` + border when off) then `code` key. Key text is muted when off. Left column has border-right; all but last row border-bottom; odd count gets an empty padded cell (`audit_log`).
6. No footer, no sticky bar, no unsaved-changes indicator visible.

## 3. Already matches
Role description as subtitle; search box left + `{n} of {total} granted` + progress bar right; per-card mono name and count; Switch + `<code>` row in a 2-col grid with matching border logic; `Save`/`Reset` disabled-when-clean is a superset of the deck.

## 4. Deltas
1. **Title copy** — `edit.title` "Edit permissions for {role}" → `Edit role: {role}` (`en.json`).
2. **Action labels/order/icon** — currently `Discard` · `Save changes`(+Check icon) · `Back`(ghost). Deck: `Reset` · `Cancel` · `Save role`, no icon, Cancel as outline. Change `edit.reset_button`→"Reset", `edit.cancel_link`→"Cancel", `edit.submit_button`→"Save role" (`en.json`); reorder and drop `<Check>` / make Cancel `variant="outline"` in `RoleEdit.tsx`.
3. **Single column → 2-column card grid** — `flex flex-col gap-3` → `grid gap-3.5 lg:grid-cols-2 items-start` (`RoleEdit.tsx`).
4. **Card header control** — replace Package icon + ghost `Select all`/`Clear` button with a tri-state `Checkbox` (`packages/ui/src/components/ui/checkbox.tsx`, Radix supports `checked="indeterminate"`) at the *left* of the name; wire to existing `toggleGroup`. Add `aria-label` key (e.g. `edit.toggle_group_label`) in `en.json`; `select_all_group`/`clear_group` keys become unused.
5. **Count format** — `{granted}/{total}` → `{granted} / {total}` (`RoleEdit.tsx`).
6. **Search scope + placeholder** — deck filters `modules or permissions`; current matches group name only and placeholder is the shared "Filter modules…". Add a role-specific key (`edit.filter_placeholder`: "Filter modules or permissions…") and extend `filtered` to also keep groups whose keys match, narrowing rows inside a group (`RoleEdit.tsx`, `en.json`).
7. **Missing `Granted only` toggle** — add an outline toggle button (new key `edit.granted_only`) that hides unchecked rows / empty groups (`RoleEdit.tsx`, `en.json`).
8. **Summary emphasis** — bold the granted number (`<b>` inside the `granted_summary` interpolation or split the key); progress bar fill flat `bg-primary` instead of gradient (`RoleEdit.tsx`).
9. **Off-state key muted** — `<code>` should get `text-muted-foreground` when not checked (`RoleEdit.tsx`).
10. **Remove footer badge row** `N / M permissions enabled` — not in deck (`RoleEdit.tsx`; `edit.permissions_enabled` unused).
11. **Odd-count trailing cell** — add an empty cell for odd `permissions.length` so the last row's border-right renders like the deck (`RoleEdit.tsx`, cosmetic).
12. **Leave-guard** — neither deck nor page has one; `Users/Edit.tsx` already implements `router.on('before')` + `beforeunload`. Recommend porting it for consistency (`RoleEdit.tsx`, new `edit.leave_warning` key). Optional.

## 5. Backend/props needed
None. `role.description`, `assigned`, `groups` suffice; "Granted only" and key-level search are client-side.

## 6. Ambiguities
- Brief mentions a "save bar", but this deck file has no sticky bar — actions live in the page header only. Decide whether to keep header actions (as now) or add a sticky bottom bar on dirty.
- Deck group names are lowercase slugs (`file_storage`); the registry returns display names (`Users`, `Feature Flags`, `Files`, `Background Tasks`). Either render `group.name` as-is or derive the slug from the key prefix.
- Deck's `Reset`/`Save role` are always enabled; keep the current dirty-gating or match the deck.
- After save the server 303s to `/admin/users/`; deck doesn't say whether Save stays on the page.
- `Cancel` target: `/admin/users/` (current) vs the Roles tab specifically.

---

# Screen 15 — `15-grants.html` "Permissions — sam@example.com"

## 1. Route + files
- View: `GET /admin/permissions/users/{user_id}/edit` → `Permissions/UserEdit`; save `PUT /admin/permissions/users/{user_id}` (303 → `/admin/users/`). `endpoints/views.py`.
- Page: `/home/anto/Repos/simple_module_python/modules/permissions/permissions/pages/UserEdit.tsx`; row: `/home/anto/Repos/simple_module_python/modules/permissions/permissions/pages/components/PermissionRow.tsx`.
- Props: `{ user:{id,email,full_name}, roles[], direct[], inherited[], inherited_by: Record<key, role[]>, groups[] }`.
- Copy: `en.json` `user_edit.*`. Entry: `modules/users/users/pages/Users/components/RolesCard.tsx`.

## 2. Design structure
1. Header: h1 `Permissions — sam@example.com`; subtitle `Sam Okafor · effective permissions combine role grants and direct grants`.
2. Actions: `Cancel` (outline), `Save grants` (filled). No Reset/Discard, no icons.
3. Stats: 3-col grid of plain cards, **label on top** (muted 12.5px, sentence case), no icons:
   - `Roles` → pill `editor` (primary border, `--soft` bg, `--pri7` text).
   - `Direct grants` → `2` (Sora 25px bold).
   - `Effective` → `11` + muted `/ 24`.
4. Toolbar: 280px search `Filter modules…`; legend: primary square `direct grant`, blue square (`rgba(37,99,235,.25)`/`#2563eb` border) `from role`. No count/progress.
5. 2-column card grid. Card header: mono module name + muted `3 effective / 4` (no icon, no checkbox).
6. Card body: **single-column list**, rows separated by border-bottom: `[switch] [code key flex:1] [right badge]`.
   - Role-inherited: switch OFF, blue pill `granted by editor`.
   - Direct: switch ON, green pill `direct` (`--pri7` on `--soft`, no border).
   - Not held: switch OFF, key muted, no badge.

## 3. Already matches
Three-card summary with Roles badges / direct count / effective `n / total`; search with `Filter modules…`; mono group name + count; per-row switch that controls only the direct grant; role-source badge fed by `inherited_by`; disabled Save when clean.

## 4. Deltas
1. **Title** — `user_edit.title` "Permissions for {email}" → `Permissions — {email}` (`en.json`).
2. **Subtitle** — deck is `{full_name} · effective permissions combine role grants and direct grants`; current shows *either* full name *or* the fallback. New key e.g. `user_edit.subtitle` "{name} · effective permissions combine role grants and direct grants" (`en.json`, `UserEdit.tsx`); decide fallback when `full_name` is null.
3. **Actions** — currently `Back`(ghost) · `Discard` · `Save changes`(+icon). Deck: `Cancel`(outline) · `Save grants`. Rename `cancel_link`→"Cancel", `submit_button`→"Save grants"; drop Check icon; drop Discard (or keep, see §6) (`UserEdit.tsx`, `en.json`).
4. **Stat cards** — deck has label-top, no icon, normal-case labels; current uses `StatCard` (icon, big value, uppercase label below) and a hand-rolled Roles card with the same shape. Either add a `variant="plain"` to `packages/ui/src/components/StatCard.tsx` or build a small local `PlainStat` in `pages/components/` and use it for all three (`UserEdit.tsx`).
5. **Stat labels** — `direct_summary` "Direct" → `Direct grants`; `Effective` value should render `11` with muted `/ 24` suffix rather than one string (`en.json`, `UserEdit.tsx`).
6. **Legend missing** — add `direct grant` / `from role` swatches next to the search (new keys `user_edit.legend_direct`, `user_edit.legend_role`; `UserEdit.tsx`).
7. **2-column card grid** — `flex flex-col` → `grid lg:grid-cols-2 items-start` (`UserEdit.tsx`).
8. **Card header** — remove the Package icon; count copy `{granted}/{total}` → `{n} effective / {total}` (new key `user_edit.group_effective`; `UserEdit.tsx`, `en.json`).
9. **Row layout** — deck is a single-column list with switch on the **left**, key `flex-1`, badge on the right, `border-b` between rows. Current is a 2-col grid with leading effective circle (Check/Minus), key, badge, switch on the **right**. Restructure `PermissionRow.tsx`: drop the indicator span (`effective_yes/no` keys unused), move Switch first, keep `title`/`aria-label`; drop the `sm:border-r` grid classes in `UserEdit.tsx`.
10. **Badge copy/style** — `via {role}` → `granted by {role}` (`user_edit.via_role`); deck blue pill has tinted border. Add a **`direct`** badge (new key `user_edit.direct_badge`, `border-0 bg-primary/10 text-primary-700`) for keys the switch holds on (`PermissionRow.tsx`, `en.json`).
11. **Not-held key muted** — already done via `effective ? … : text-muted-foreground`; keep.
12. **Leave-guard** — same optional port from `Users/Edit.tsx` as screen 14.

## 5. Backend/props needed
None; `full_name`, `roles`, `direct`, `inherited_by`, `groups` cover every element.

## 6. Ambiguities
- Key held **both** directly and via role: deck has no example. Show both badges, or `direct` only? Current shows `via role` + switch on.
- Multiple granting roles: deck shows one name; current appends ` +N`. Decide `granted by editor, admin` vs `+N`.
- Row ordering in the deck (`users.read, users.write, users.invite, users.delete`) is neither alphabetical nor registry order — possibly "held first". Registry returns sorted keys; decide whether to reorder.
- Whether to keep a Discard/Reset button (deck omits it; screen 14 has one).
- `Cancel` target: `/admin/users/` (current) vs back to `/admin/users/{id}/edit` where the "Manage permissions" link originates.
- No unsaved-changes bar in the deck despite the brief; same decision as screen 14.
- Post-save redirect to the users list vs staying on the page.

---

## Overall summary (largest gap first)
1. **15-grants (UserEdit)** — larger gap: row anatomy inverted (switch left, no effective indicator, new `direct` badge, `granted by` copy, single-column list), stat cards need a new plain variant + relabel, legend missing, 2-col grid, title/subtitle/action copy. Touches `UserEdit.tsx`, `PermissionRow.tsx`, `StatCard.tsx` (or new local component), `en.json`.
2. **14-role (RoleEdit)** — moderate: 2-col grid, tri-state header checkbox replacing icon + Select all/Clear, `Granted only` filter, key-level search, remove footer badge, copy for title/buttons. Touches `RoleEdit.tsx`, `en.json`.

No backend or prop changes are required for either screen; all deltas are frontend + locale.