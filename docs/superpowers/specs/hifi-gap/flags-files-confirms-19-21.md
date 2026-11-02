# Hi-Fi deck gap analysis — flags-files-confirms-19-21

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

## Gap analysis: Feature flags (19), File storage (20), Destructive confirms (21)

Read-only; no files modified. Deck copy is quoted verbatim.

---

### Screen 19 — Feature flags (`/tmp/hifi/screens/19-flags.html`)

**1. Route + files**
- Route `GET /admin/feature-flags/` (`?tenant_id=`), actions `POST /admin/feature-flags/{name}/toggle|clear` — `/home/anto/Repos/simple_module_python/modules/feature_flags/feature_flags/endpoints/views.py`
- Page `/home/anto/Repos/simple_module_python/modules/feature_flags/feature_flags/pages/Browse.tsx`, `pages/components/TenantPicker.tsx`, `pages/components/ToggleConfirmDialog.tsx`, `locales/en.json`, `module.py`

**2. Design structure**
1. H1 `Feature flags`; sub `Runtime toggles. A tenant override wins over the system value.`
2. Scope card: label `Scope` + segmented control `system | acme-co | globex` (active = raised white chip); helper `Viewing overrides for tenant <code>acme-co</code> — unset flags follow the system value.`; right-aligned link `View change history →`
3. Table card, uppercase 11px headers: `Name | Description | System | Effective | Actions`
   - Name: mono flag name; overridden rows add an outlined emerald pill `override` and get a soft-emerald row background
   - Description: muted, `—` when empty
   - System: lowercase `on` / `off`
   - Effective: 38x22 toggle + `Enabled` (weight 500) / `Disabled` (muted)
   - Actions: emerald text link `Clear override` on overridden rows; muted lowercase `following system` otherwise
4. Card footer: `Every toggle is written to the audit log with the actor and the previous value.`
5. No empty state, no row count, no confirm dialog shown.

**3. Already matches**
PageShell title/description; tenant scoping via `?tenant_id`; mono flag name; override badge; Switch + Enabled/Disabled; Clear override on overridden rows only; "following system" fallback; uppercase-tracked table headers; `description || '—'`. Data-wise `FeatureFlagView` already carries `system_enabled`. Audit capture is already real: `FeatureFlagOverride` uses `AuditMixin`, and `framework/db/simple_module_db/audit.py` diffs every flush, so the footer claim is true today when `audit_log` is installed.

**4. Deltas**
1. Copy — `locales/en.json`: `browse.title` "Feature Flags" → `Feature flags`; `browse.description` → `Runtime toggles. A tenant override wins over the system value.`; `browse.viewing_tenant` → `Viewing overrides for tenant {tenant_id} — unset flags follow the system value.` (render tenant in `<code>`); `table.name` "Flag" → `Name`; `table.overridden` "Override active" → `override`; `table.following_system` → lowercase `following system`.
2. Scope picker — replace the `Select` + "Other tenant…" form in `TenantPicker.tsx` with a segmented control (`FilterPills`-style, but the deck's chip style is raised-white-on-secondary, not outlined pills) reading `Scope` and listing `system` + `tenants`. Keep a way to type a new tenant id (see ambiguity 1).
3. Columns — `Browse.tsx`: rename `Default` → `System` and show `system_enabled ?? default_enabled` as lowercase `on`/`off` (new keys `table.on`/`table.off`); rename `Status` → `Effective`; drop the `System: {value}` sub-line under the switch (it becomes the column).
4. Actions cell — replace the `RotateCcw` icon-only ghost button with a text `Button variant="link"` reading `Clear override`.
5. Overridden row background — add `bg-primary/5` (deck `var(--soft)`) to `TableRow` when `flag.overridden`; badge should be `variant="outline"` with emerald border/text, not `secondary`.
6. Footer — add a `CardFooter`/`<p>` under the table with new key `browse.audit_note`.
7. Scope card — move `TenantPicker` helper text inline (same row) and add `View change history →` as a `Link` to `/admin/audit-log/?entity_type=FeatureFlagOverride` (that query param already exists in `modules/audit_log/audit_log/endpoints/views.py`). Add `register_audit_links` to `module.py` so audit rows link back.
8. Remove the right-aligned `{count} flags` line (not in deck).
9. Keep the existing empty state (deck omits it; needed for zero registered flags).

**5. Backend/props needed**
None for the table. Optional: `audit_log_url` prop (or gate the link on the `audit_log` module being installed, mirroring `has_permissions_module` in users).

**6. Ambiguities**
1. Deck lists a closed set of tenants; there is no tenant registry — `tenants` only contains tenants with overrides. Where does "name a new tenant" live?
2. In system scope, what does the `System` column show — the code default? (Likely yes; then `Effective` = system override or default.)
3. Deck shows no toggle confirm; keep `ToggleConfirmDialog` (recommended — it guards the "for everyone" case) and restyle via the shared dialog below.
4. "previous value" on a first-time override is `created` (no prior row) in the audit trail; the inherited value is not recorded.

---

### Screen 20 — File storage (`/tmp/hifi/screens/20-files.html`)

**1. Route + files**
- `GET /file-storage/` (`?q=&content_type=&page=`) — `/home/anto/Repos/simple_module_python/modules/file_storage/file_storage/endpoints/views.py`; JSON `/api/file-storage/{upload,files/{id},files/{id}/download}` — `endpoints/api.py`
- `pages/Browse.tsx`, `pages/components/{FileFilterBar,UploadDropzone,UploadProgressRows}.tsx`, `pages/upload-queue.ts`, `pages/constants.ts`, `locales/en.json`, `service.py`, `settings.py`

**2. Design structure**
1. H1 `File storage`; sub `Backend s3 · 1.2 GB of 5 GB used · 25 MB per file`; header actions: outline `Delete selected`, primary `Upload files`
2. Dashed emerald dropzone strip: `Drop files here` + `or click to browse · pdf, png, csv, sql · max 25 MB`
3. Card `Uploads in progress` / `Stays put while you filter or page the table`; rows: name (190px) + progress bar + `64%` + `✕`; failed row: `Failed — exceeds the 25 MB limit` + link `Retry` + `✕`
4. Filter row: search `Search filenames…`; dropdown `Type: image/png (12) ▾`; dropdown `Uploaded by ▾`
5. Table card, uppercase headers: `[checkbox] | Filename | Type | Size | Uploaded by | When | Actions`; selected row soft-emerald; uploader values `sam`, `system`, `— unknown`; When = `2h ago`, `yesterday`, `3d ago`, `1w ago`; Actions = emerald text link `Download`
6. Card footer: `1 selected · showing 1–20 of 74` + `Previous` / `Next` buttons

**3. Already matches**
Search (debounced) + content-type facet select with counts and family grouping; XHR progress per file; failed rows persist until dismissed with `X`; jobs survive filter/page navigation (`preserveState`); per-row Download; filename/type/size columns; `—` for unknown uploader; Previous/Next; filter-aware empty states (keep).

**4. Deltas**
1. Header copy — `en.json`: `browse.title` "Files" → `File storage`; `browse.upload_button` "Upload file" → `Upload files`; `filters.search_placeholder` → `Search filenames…`; `table.filename` "Name" → `Filename`.
2. Header subtitle — `Browse.tsx`: render `Backend {backend} · {used} of {quota} used · {max} per file` from new props (see §5).
3. Dropzone — `UploadDropzone.tsx` is a button with a hidden input; add a real drag-and-drop strip (`onDragOver/onDrop`, click-to-browse) with `Drop files here` and `or click to browse · {types} · max {size}`. Keep the header `Upload files` button; both call `start`.
4. Uploads card — move `UploadProgressRows` out of the table into its own `Card` titled `Uploads in progress` with subtitle; give in-flight rows a `✕` cancel (wire `xhr.abort()` in `upload-queue.ts`; currently abort is only listened to), and failed rows a `Retry` (queue needs to keep the `File` object per job).
5. Failure reason — `upload-queue.ts` discards the response; parse `detail.message` from the 413/415 body (`api.py` already returns `file_storage.errors.too_large` / `bad_type`) and show `Failed — {reason}` instead of the generic `Upload failed`.
6. Type filter trigger — show `Type: {value} ({count})` when a value is set (`FileFilterBar.tsx`).
7. `Uploaded by` filter — new dropdown; `service.list_files` already accepts `created_by`, but `views.py` does not expose it and there is no uploader facet.
8. Uploader display — the cell currently prints a raw UUID (`uploaded_by = created_by`). Resolve to `full_name || email` server-side (precedent: `modules/audit_log/audit_log/resolve.py::resolve_actors`; note it imports `users.models` directly — check `make doctor` coupling rules).
9. `When` column — add relative time. `created_at` is already in props and the key `table.uploaded_at` exists but is unused. No relative-time helper exists anywhere; add one in `packages/ui` (`Intl.RelativeTimeFormat`).
10. Selection + bulk delete — add `Checkbox` column, `Delete selected` header button, selected-row highlight, footer `{n} selected · showing {from}–{to} of {total}`. Needs a bulk endpoint (§5).
11. Footer/pagination — move Previous/Next into the card footer and always show the range text (currently centered under the card, only when `totalPages > 1`, reads `Page X of Y`).
12. Actions — deck shows only a `Download` text link; delete moves to bulk. Header styling: add the uppercase-tracked classes the flags table already uses.
13. Delete confirm — see screen 21.

**5. Backend/props needed**
- `browse` view: `backend` (settings.backend), `max_file_size_bytes`, `allowed_content_types`, `used_bytes` (needs `SUM(size_bytes)` — nothing exists), `quota_bytes` (no setting exists; would be new in `settings.py`), `uploaders` facet, `uploaded_by` filter passthrough, resolved uploader labels.
- Bulk delete endpoint (`POST /api/file-storage/files/delete` or `DELETE` with ids); only single-file delete exists.

**6. Ambiguities**
1. Quota: there is no storage quota concept; "5 GB" must be a new setting or the segment dropped.
2. `pdf, png, csv, sql` implies a whitelist; default `allowed_content_types=None` (any). Copy when unrestricted?
3. Deck default max is `25 MB`; code default is 100 MB — display only, or change the default?
4. `system` vs `— unknown` uploader: no "system" actor exists; both are `created_by=None` today.
5. Deck's "Delete selected" leads to a single-file confirm; see 21.
6. Deck places Files under the "Ops" admin nav; the module mounts at `/file-storage/` in `AuthenticatedLayout`, group "Content". Moving it means `/admin/files` + `AdminLayout` + `ADMIN_SIDEBAR` together (CLAUDE.md rule).

---

### Screen 21 — Destructive confirms (`/tmp/hifi/screens/21-confirm.html`)

**1. Routes + files**
- File delete: inline `AlertDialog` in `file_storage/pages/Browse.tsx` (lines 190–222) + `locales/en.json#delete_dialog`
- User delete: `/home/anto/Repos/simple_module_python/modules/users/users/pages/Users/components/DangerZone.tsx` + `users/locales/en.json#danger_zone`
- Retry: `/home/anto/Repos/simple_module_python/modules/background_tasks/background_tasks/pages/components/RetryConfirmDialog.tsx` + `locales/en.json#retry_dialog`
- Primitive: `/home/anto/Repos/simple_module_python/packages/ui/src/components/ui/alert-dialog.tsx` (has `AlertDialogMedia`, `AlertDialogAction variant`)

**2. Design structure** (all three: 40px rounded icon tile above a left-aligned Sora title, muted body, right-aligned `Cancel` outline + filled action)
- A. trash glyph in red/10 tile; title `Delete “q3-report.pdf”?`; body `This removes the file from the s3 backend. Links already shared will stop working immediately.`; action `Delete file` (red)
- B. warning glyph red tile; title `Delete sam@example.com?`; body `Sessions end at once and the account cannot be restored. Audit entries are kept.`; label `Type the email to confirm`; mono input placeholder `sam@example.com`; action `Delete user` (red)
- C. circular-arrow glyph in emerald-soft tile; title `Retry files.generate_thumbnail?`; body `A new execution is queued with the same arguments. This one has already been retried once.`; mono secondary box `args ["a91f2c"] · kwargs {"size": 512}`; action `Queue retry` (emerald)

**3. Already matches**
All three exist as `AlertDialog`s with title-echoing name/email/task; user delete already has type-to-confirm gated `disabled={!confirmed}`; retry already renders args/kwargs in mono; `Cancel` everywhere.

**4. Deltas**
1. File delete (`file_storage/en.json`): title uses curly quotes `“{name}”`; description → `This removes the file from the {backend} backend. Links already shared will stop working immediately.`; confirm `Delete` → `Delete file`. In `Browse.tsx` use `AlertDialogAction variant="destructive"` instead of the className override; `backend` is already in the Inertia payload (`StoredFileOut.backend`) but missing from the TSX `StoredFile` interface.
2. User delete (`DangerZone.tsx` / `users/en.json`): `confirm_body` → `Sessions end at once and the account cannot be restored. Audit entries are kept.`; prompt → single key `Type the email to confirm`; input `font-mono`; **the action button is currently default (emerald) — must be `variant="destructive"`**; add icon tile.
3. Retry (`RetryConfirmDialog.tsx` / `background_tasks/en.json`): description → `A new execution is queued with the same arguments.` + conditional `This one has already been retried once.` (needs `retries` prop — available on `Execution`); collapse the `<dl>` into one mono box `args {args} · kwargs {kwargs}` on `bg-secondary`; confirm `Retry task` → `Queue retry`; add emerald icon tile. Keep the `no_args` branch (deck doesn't cover it).
4. Shared component — yes, one `ConfirmActionDialog` in `packages/ui/src/components/` (exported from `packages/ui/src/index.ts`) covers all three plus `ToggleConfirmDialog`: props `tone: 'destructive' | 'primary'`, `icon: LucideIcon`, `title`, `description`, `children` (slot for the type-to-confirm block or the args box), `confirmLabel`, `cancelLabel`, `onConfirm`, `confirmDisabled`, `busy`, and either `trigger` or `open/onOpenChange` (flags uses controlled, the others use trigger). Optional `confirmText` prop renders the mono input and gates the action. Labels must be props: `packages/ui` already imports `@simple-module-py/i18n`, but no shared `ui.*.cancel` key exists (only `ui.sidebar.close`), and the untranslated-string check forbids literals.

**5. Backend/props needed**
None. `backend` (file), `email` (user), `retries`/`args`/`kwargs` (task) are all already delivered.

**6. Ambiguities**
1. "retried once" — derive from `retries === 1`, `retries >= 1`, or `retried_from_id != null`? Copy for 2+ retries?
2. Deck's mono box shows args inline; long payloads (Detail page uses a `<pre>`) need a truncation rule.
3. User type-to-confirm currently matches case-insensitively; keep?
4. Deck tiles use emoji glyphs; map to lucide `Trash2` / `TriangleAlert` / `RefreshCcw`.
5. Which action opens the file confirm: the row (single) or `Delete selected` (bulk needs a count-based title)?

---

### Overall ranking by gap size

1. **File storage (20)** — largest: new dropzone, separate uploads card with cancel/retry and real failure reasons, checkbox selection + bulk delete + footer, `Uploaded by` filter and name resolution, `When` relative-time column, backend/quota subtitle. Needs new view props, an aggregate, a bulk endpoint, possibly a quota setting and a route/layout move.
2. **Feature flags (19)** — medium: segmented scope control, column rename/reshuffle (`System` as its own column), text `Clear override`, row highlight, audit footer + history link, copy pass. No backend work.
3. **Destructive confirms (21)** — smallest per dialog but cross-cutting: copy changes, one real bug (user-delete action button not destructive), a conditional retry sentence, and the opportunity to fold four ad-hoc dialogs into one shared `packages/ui` component.