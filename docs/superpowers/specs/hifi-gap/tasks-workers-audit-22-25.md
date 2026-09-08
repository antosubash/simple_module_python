# Hi-Fi deck gap analysis — tasks-workers-audit-22-25

Generated 2026-09-02 from the cached deck (fetched 2026-08-19) vs main @ a8ab6bb. Read-only findings; decisions live in ../2026-09-03-hifi-pages-design.md.

I have everything needed; no further reads are required. Here is the gap analysis.

# Design-vs-implementation gap analysis — Ops screens 22–25

Path legend (all absolute):
- `BT` = `/home/anto/Repos/simple_module_python/modules/background_tasks/background_tasks`
- `AL` = `/home/anto/Repos/simple_module_python/modules/audit_log/audit_log`
- `UI` = `/home/anto/Repos/simple_module_python/packages/ui/src`

Note on the deck: none of these four screens use `sc-for`; they are static samples, so `script.js` only contributes navigation (`goTasks`, `goTaskDetail`, `goWorkers`, `goConfirm`). The task-detail "Retry task" button navigates to screen 21 (`/tmp/hifi/screens/21-confirm.html`, third card), which I treat as the retry dialog design.

---

## 22 — Background tasks (`/tmp/hifi/screens/22-tasks.html`)

**1. Route + files.** `GET /admin/background-tasks/` → `BT/endpoints/views.py::index` → `BT/pages/Index.tsx` with `BT/pages/components/{StatusStrip,WorkerHealthBanner,ExecutionRow,TasksEmpty,RetryConfirmDialog}.tsx`, `BT/pages/constants.ts`, `BT/pages/retry.ts`, `BT/locales/en.json`.

**2. Design structure.**
1. Header: h1 "Background tasks"; sub "Monitor executions and retry failed or stuck jobs". Top-right outline buttons: "Workers", "Retry all failed".
2. Stat strip, 5 equal cards, label above value (12.5px muted / 25px Sora bold): "Queued" 12, "Running" 3, "Succeeded 24h" 840, "Failed" 7 (red tint bg `rgba(220,38,38,.06)`, red border, red label+value), "Stuck" 2 (amber `#b45309` tint). No active/selected state drawn.
3. Toolbar, one row: search (flex:1, icon, "Search by task name…") | segmented control on `--sec`: "All" · "Failed" (active = card bg + shadow) · "Running" · "Stuck" | dropdown "Queue: all ▾".
4. Table card, header on `--sec` uppercase 11px: "Task" 2.2fr | "Status" 110px | "Queue" 100px | "Queued" 1fr | "Duration" 100px | "Actions" 90px right. Rows: task name as `<code>` JetBrains Mono `--pri7`; lowercase status pill (`failed` red, `stuck` amber, `running` blue `#2563eb`, `success` `--pri7` on `--soft`); queue muted; queued relative ("9m ago", "just now"); duration "12.4s" or "—"; action = text link "Retry" in `--pri7` for failed/stuck, empty otherwise. Whole row clickable → detail, hover bg `--sec`.
5. Footer inside card (border-top): "Showing 1–20 of 231" left; "Previous" / "Next" outline right.
No banner between strip and toolbar.

**3. Already matches.** Search box + exact placeholder; StatusStrip exists and is clickable with red alarm on failed/stuck; Workers button; Task/Status/Queue/Queued/Duration/Actions columns; per-row retry gated on failed/stuck + `background_tasks.manage`; retry confirm; Previous/Next; richer empty states.

**4. Deltas.**
1. Copy: `index.title` "Background Tasks" → "Background tasks"; `index.description` → "Monitor executions and retry failed or stuck jobs" (`BT/locales/en.json`).
2. Header actions: move "Workers" from the toolbar into `PageShell actions`; add "Retry all failed" (new key + endpoint) (`Index.tsx`).
3. Strip tiles: impl has 6 (Failed, Stuck, Retrying, Running, Pending, Success), value-above-label, `text-lg`. Deck: 5 in order Queued(pending) / Running / Succeeded 24h / Failed / Stuck, label-above-value, card styling, Failed tile fully red-tinted and Stuck amber-tinted (not only the number). Edit `TILES`, layout and tint classes in `StatusStrip.tsx`; add labels "Queued", "Succeeded 24h" to `en.json`.
4. Status filter: replace the 8-option `Select` with a segmented control "All / Failed / Running / Stuck". `UI/components/FilterPills.tsx` is pill-style, not segmented — extend it with a `variant="segmented"` or add a component. (`Index.tsx`)
5. Add "Queue: all ▾" dropdown (needs backend, §5). (`Index.tsx`)
6. Toolbar layout: single row, search `flex-1` (drop `max-w-sm`), filters right. (`Index.tsx`)
7. Table header: apply the audit `TH` treatment (`bg-secondary/40`, 11px uppercase tracking) — `Index.tsx`.
8. Drop the "Worker" column (deck has 6 columns); `COLUMN_COUNT` 7→6 (`Index.tsx`, `ExecutionRow.tsx`). Or keep hidden below xl — decide.
9. Task name: `<code>` `font-mono text-primary-700`; remove the red `exception_type` subline (deck has none) (`ExecutionRow.tsx`).
10. Status pills: `STATUS_BADGE_VARIANT` maps failed+stuck→`destructive`, running+success→`secondary`. Replace with a per-status class map (red/amber/blue/emerald tints, borderless, like `ACTION_BADGE` in audit) in `constants.ts`; deck labels are lowercase.
11. Queued cell: relative age via `relativeAge` from `UI/lib/relative-time.ts` (add a `days_ago` bucket in `UI/locales/en.json` — deck shows "3h ago", but multi-day rows exist) instead of `formatTs` (`ExecutionRow.tsx`).
12. Duration: deck shows "—" for running/stuck; impl shows live elapsed. Decide.
13. Actions: text button "Retry" (`table.retry` key already exists) instead of ghost icon; render nothing instead of "—" (`ExecutionRow.tsx`).
14. Row click → `router.visit(detail)` + `cursor-pointer hover:bg-secondary/40`; `stopPropagation` on the retry trigger (`ExecutionRow.tsx`).
15. Pagination: move inside the card as a footer, always visible, "Showing {from}–{to} of {total}" (add key, mirror `audit_log.browse.showing`) instead of centered "Page x of y" shown only when >1 page (`Index.tsx`, `en.json`).

**5. Backend/props needed.**
- "Succeeded 24h": `service.status_counts` counts all-time per status. Add a windowed count (`status=success AND finished_at >= now-24h`) in `BT/service.py`, expose as e.g. `status_counts.success_24h` from `views.py::index`.
- Queue filter: `service.list(queue=…)` + `status_counts(queue=…)`, `queue: str | None = Query()` in `views.py::index`, plus a `queues: list[str]` prop (distinct queues) for the dropdown.
- "Retry all failed": no endpoint. `BT/endpoints/api_admin.py` only has `POST /executions/{id}/retry`. Add a bulk retry (service method + endpoint + toast keys), permission `background_tasks.manage`.

**6. Ambiguities.**
- Are stat cards clickable filters (impl) or informational (deck shows no active state)? If both, "Queued"/"Succeeded 24h" tiles select statuses the segmented control cannot express.
- Does "Retry all failed" include `stuck`? Current filter/queue only, or everything? No confirm dialog is drawn.
- "Succeeded 24h" window basis (`finished_at` vs `queued_at`).
- Queue list source: DB distinct, worker `active_queues`, or settings.
- Retrying/Revoked statuses appear nowhere in the deck — hidden or folded?
- The WorkerHealthBanner is absent from the deck; keep as an undrawn conditional state?
- Lowercase status labels vs the repo's capitalised i18n convention (global decision).

---

## 23 — Task detail (`/tmp/hifi/screens/23-taskdetail.html` + `21-confirm.html` card 3)

**1. Route + files.** `GET /admin/background-tasks/{execution_id}` → `views.py::detail` → `BT/pages/Detail.tsx`, `BT/pages/components/RetryConfirmDialog.tsx`, `BT/pages/retry.ts`, `BT/contracts/schemas.py::TaskExecutionDetail`.

**2. Design structure.**
1. Header: h1 = `<code>files.generate_thumbnail</code>` (Sora 24 wrapping Mono 22) with inline red pill "failed"; subline mono muted "execution 8f21c9de-4b17-4a90-9ac2-1f0d7e55e311 · attempt 2 of 3". Right: outline "← Back to executions", primary "↻ Retry task".
2. Grid `320px 1fr`, gap 18.
3. Left card, h2 "Details", label/value rows 13px: "Queue" media · "Worker" `celery@w2` (mono) · "Celery id" `c1a4…8de2` (mono, shortened) · "Queued at" 09:41:02 · "Started at" 09:41:05 · "Finished at" 09:41:17 · "Duration" 12.4s · "Heartbeat" — · "Retried from" `3b91c07a…` (mono, `--pri7` link). Footer pinned to bottom (border-top): label "Exception", value `PIL.UnidentifiedImageError` red mono.
4. Right, top row two cards side by side: "Arguments" → `[ "a91f2c" ]`; "Keyword arguments" → `{ "size": 512 }` (one-line code on `--sec`, 8px radius, muted).
5. "Traceback" card (flex:1): header with "Copy" text link `--pri7`; `<pre>` dark `#0f172a` bg, `#dfe3ea` text, 12.5px/1.8 mono, final exception line in `#f8a9a0`. Deck annotation (not UI copy): "A Result card appears above the traceback when a run returns one."
6. Confirm (screen 21): ↻ icon in soft-emerald 40px square; h2 "Retry files.generate_thumbnail?"; body "A new execution is queued with the same arguments. This one has already been retried once."; mono box `args ["a91f2c"] · kwargs {"size": 512}`; buttons "Cancel" / "Queue retry" (primary).

**3. Already matches.** Title = task_name; Back + Retry in `PageShell actions`; retry gating; Details rows Queue/Worker/Celery id/Queued/Started/Finished/Heartbeat/Exception/Retried-from (8-char link); Arguments / Keyword arguments / conditional Result / Traceback cards; dialog title "Retry {name}?", args/kwargs shown, Cancel; toast + navigate to new row.

**4. Deltas.**
1. Title as mono `<code>`: `PageShell.title` is `string` (feeds breadcrumb via `useReportPageHeading`). Add `titleClassName`/`titleAdornment` props to `UI/components/PageShell.tsx`; pass `font-mono` (`Detail.tsx`).
2. Status pill inline with the title (deck) instead of a "Status" row inside Details; delete that row (`Detail.tsx`).
3. Subline: `detail.description` "Task execution {id}" → "execution {id} · attempt {attempt} of {max}", mono muted; needs `max_retries` (§5) (`en.json`, `Detail.tsx`).
4. `detail.back_button` "Back to tasks" → "Back to executions" (`en.json`).
5. Details: add "Duration" row (move `formatDuration` from `ExecutionRow.tsx` to `constants.ts`); remove "Retries" row; reorder to deck order (`Detail.tsx`).
6. Worker as `<code>`; Celery id shortened `first4…last4` (impl full, `break-all`) — consider `CopyableId`; Retried-from link `text-primary-700` (`Detail.tsx`).
7. Exception → bottom footer block (`mt-auto border-t`, label above, red mono value) rather than a plain row (`Detail.tsx`).
8. Timestamps: deck time-only "09:41:02"; impl `toLocaleString()`. Decide.
9. Args/Kwargs side by side (`grid-cols-2`), single-line code on `bg-secondary` (impl stacked, 2-space JSON in `bg-muted`); card titles Sora 14px (`Detail.tsx`).
10. Traceback: dark terminal `<pre>`, last line highlighted, "Copy" action with copied feedback (clipboard pattern from `UI/components/CopyableId.tsx`), new key `detail.copy`. Extract to `BT/pages/components/TracebackCard.tsx` — `Detail.tsx` is 213 lines against the 300 cap.
11. Grid `lg:grid-cols-[320px_1fr]` instead of `lg:grid-cols-3` (`Detail.tsx`).
12. Dialog: `retry_dialog.description` → "A new execution is queued with the same arguments." + pluralised "This one has already been retried {count} time(s)." (pass `retries`); `retry_dialog.confirm` "Retry task" → "Queue retry"; payload as one line `args … · kwargs …` in a bordered `bg-secondary` box; add the ↻ icon tile above the title (`RetryConfirmDialog.tsx`, `en.json`).

**5. Backend/props.** `max_retries` from `app.state.background_tasks` settings (`BackgroundTasksSettings.max_retries`, `BT/settings.py`) added to the `views.py::detail` payload. Everything else (`retries`, `retried_from_id`, `heartbeat_at`, `traceback`, `result`) already ships.

**6. Ambiguities.**
- "attempt 2 of 3": is attempt `retries + 1`? Is "3" the module-wide `max_retries` or a per-task Celery option (only the former exists)?
- Time-only timestamps hide the date for older executions — same-day-only rule, or full date in tooltip?
- "Copy" copies the traceback only, or traceback + exception header?
- Dialog sentence when `retries == 0` — omit, or "not been retried yet"?
- Should the Celery id be copyable (`CopyableId`) or just shortened text?

---

## 24 — Workers (`/tmp/hifi/screens/24-workers.html`)

**1. Route + files.** `GET /admin/background-tasks/workers` → `views.py::workers` → `BT/pages/Workers.tsx`; refresh via `GET /api/background_tasks/admin/workers` (`BT/endpoints/api_admin.py`); data from `BT/worker_inspector.py`, `BT/contracts/schemas.py::WorkerInfo/WorkerSnapshot`.

**2. Design structure.**
1. Header: h1 "Workers"; sub "Celery workers connected to the broker". Right cluster: muted "Last updated 09:44:10", outline "↻ Refresh", outline "← Executions".
2. Fleet grid 2 columns. Card: 10px dot (`--pri` online / `--muted` offline), `celery@w1` mono 15px, subline "celery 5.4.0 (opalescent) · uptime 4d 2h" (offline: "celery 5.4.0 · last heartbeat 6m ago"), pill "Online" (`--pri7` on `--soft`) / "Offline" (muted on `--sec`); offline card `opacity:.75`. Stats 4-col: "Active" 3 · "Pool" 4 · "Processed" 1,208 · "Queues" mono outlined chips (`default`, `media`); values 19px Sora bold; offline: Active 0, Pool —, Processed —.
3. Documented empty states (dashed boxes): "Empty state — broker unreachable" — "Shown instead of the fleet when the broker connection fails, with the error text and the setting to check." code `SM_BG_TASKS_BROKER_URL=redis://localhost:6379/0`. "Empty state — no workers connected" — "Broker is reachable but nothing is consuming. Offers the command to start one locally." code `$ python run_worker.py --queues default,media`.

**3. Already matches.** Title/description; Refresh with spinner; Back button; updated-age + stale badge; WorkerCard dot/hostname/software/Online-Offline badge; Active/Pool/Processed/Queues with "—" for nulls and chip badges; broker-unreachable card with error + `SM_BG_TASKS_BROKER_URL`; no-workers card with a run command.

**4. Deltas.**
1. Move "Last updated" + "↻ Refresh" + "← Executions" into `PageShell actions`; rename `workers.back_button` to "Executions" (`Workers.tsx`, `en.json`).
2. "Last updated 09:44:10" absolute vs impl "Updated 2m ago" + Stale badge + primary Refresh when stale. Decide (see §6).
3. Fleet `grid gap-4 md:grid-cols-2` (impl single column) (`Workers.tsx`).
4. Hostname as `<code>` mono; subline `"{software} · uptime {x}"` / `"{software} · last heartbeat {ago}"` (impl only `software`). Software string: inspector emits `"py-celery:5.4.0"` — deck wants "celery 5.4.0" (`worker_inspector.py::_build_worker_info` or card).
5. Dot `bg-primary` not `bg-green-500`; offline card `opacity-75` (`Workers.tsx`).
6. Online/Offline pill tints (`text-primary-700 bg-primary-600/10` / `text-muted-foreground bg-secondary`) instead of `secondary`/`outline` (`Workers.tsx`).
7. Stat values `font-[var(--font-display)] text-lg font-bold`, `total_processed.toLocaleString()` (`Workers.tsx`).
8. Queue chips `font-mono rounded-full` (`Workers.tsx`).
9. Broker-unreachable: show a code block `SM_BG_TASKS_BROKER_URL=<value>` and a red title; impl only names the env var in prose (`Workers.tsx`, needs §5).
10. No-workers command: impl prints `uv run python scripts/run_worker.py`, which is wrong — `scripts/run_worker.py` has no `main`; per its docstring the command is `uv run celery -A scripts.run_worker:celery worker -l info`. Deck's `python run_worker.py --queues default,media` also doesn't exist. Fix the literal either way; append `-Q <queues>` (`Workers.tsx`).
11. Empty-state visual: dashed 1.5px border box with title/paragraph/code vs impl `Card p-6` icon+text — optionally via `UI/components/EmptyState.tsx` (`Workers.tsx`).

**5. Backend/props.**
- `uptime_seconds` on `WorkerInfo` from `stats()["uptime"]` (`schemas.py`, `worker_inspector.py`, mirror in `pages/constants.ts`).
- "last heartbeat" for offline workers: inspect cannot report anything for a worker that didn't reply; needs persisted last-seen per hostname (events or a Redis/DB record). New state, not a field tweak.
- Broker URL (credentials redacted) in the `views.py::workers` payload and the API snapshot for the unreachable state.
- Known queue list for the run command (settings `task_default_queue` + DB distinct).

**6. Ambiguities.**
- Absolute vs relative freshness label; keep the Stale badge?
- Release codename "(opalescent)" isn't in `stats()` (`sw_ident`/`sw_ver`/`sw_sys` only) — drop or derive from `celery.__version__`?
- Sort order (online first?).
- Offline "Active 0" vs "—".
- Which start command is canonical.

---

## 25 — Audit log (`/tmp/hifi/screens/25-audit.html`)

**1. Route + files.** `GET /admin/audit-log/` → `AL/endpoints/views.py::browse` → `AL/pages/Browse.tsx`, `AL/pages/components/{FilterBar,EntryCells,Correlation,BrowseEmpty}.tsx`, `AL/resolve.py`, `AL/service.py`, `AL/locales/en.json`, registry `/home/anto/Repos/simple_module_python/framework/core/simple_module_core/audit_links.py`.

**2. Design structure.**
1. Header: h1 "Audit log"; sub "Field-level change history across all modules". Right: outline "Export CSV".
2. Filter card, grid `1fr 1fr 1fr 1fr auto` items-end, labels 12.5px muted above fields: "Entity type" (select, `users_user ▾`), "Action" (select, `updated ▾`), "Actor" (input, placeholder "Anyone"), "Date range" (single field "01 Aug – 19 Aug"); "Apply" primary + "Clear" outline.
3. Table card, header on `--sec` uppercase: "Time" 150px | "Action" 110px | "Entity" 1.4fr | "Actor" 1fr | "Changes" 1.9fr; rows `align-items:start`. Time mono muted "19 Aug 14:02:11". Action lowercase pill (`updated` blue, `deleted` red, `created` `--pri7`/`--soft`). Entity: row display name link `--pri7` ("Sam Okafor", "users.smtp_host", "rob@example.com") + small muted type tag ("users_user", "settings_setting"); unlinked ("seed.sql" `files_file`) plain. Actor: name link or muted "system". Changes: mono lines `field old → new` (field `--fg`, rest muted): "is_active true → false", "disabled_at null → 2026-08-19", `value "" → "mail.example.com"`, "source env → db", then link "+2 more fields"; deleted → "no changes recorded"; created → "7 fields set".
4. Footer in card: "Showing 1–50 of 2,431" + "Previous"/"Next".
No correlation link/banner drawn.

**3. Already matches.** Closest of the four: `TH` header styling on `bg-secondary/40`; colour-coded action badges; entity links via registry; resolved actor names linked; "System" for null actor; changes `field old→new` with show-more/less, "{count} fields set", "—" for deletes; "Showing {from}–{to} of {total} entries" + Previous/Next; Apply/Clear; filtered/unfiltered empty states.

**4. Deltas.**
1. Copy: `browse.title` → "Audit log"; `browse.description` → "Field-level change history across all modules" (`en.json`).
2. "Export CSV" in `PageShell actions` — missing (`Browse.tsx`, new key, §5).
3. FilterBar → `grid sm:grid-cols-2 lg:grid-cols-[1fr_1fr_1fr_1fr_auto] items-end`, labels `text-xs text-muted-foreground` above inputs (`FilterBar.tsx`).
4. Labels: "Entity Type" → "Entity type"; "User ID" → "Actor"; placeholder → "Anyone"; From/To `datetime-local` pair → one "Date range" popover (`UI/components/ui/calendar.tsx` + `popover.tsx` exist; react-day-picker 10 is installed) (`FilterBar.tsx`, `en.json`).
5. Clear button `variant="outline"` not `ghost` (`FilterBar.tsx`).
6. Table labels: "Timestamp" → "Time", "User" → "Actor" (`en.json`).
7. Time cell: `d MMM HH:mm:ss` via `Intl.DateTimeFormat`, `font-mono text-xs` (impl `toLocaleString()` sans) (`Browse.tsx`).
8. Action pill: borderless tints, `created` on emerald (`text-primary-700 bg-primary-600/10`) instead of Tailwind green; lowercase per deck (`ACTION_BADGE` in `Browse.tsx`).
9. Entity cell: deck = resolved row display name as the link + muted *table-name* tag; impl = kind label ("User") + short id. Needs §5 (`EntryCells.tsx`).
10. Actor "system" lowercase (`changes.system_user`) (`en.json`).
11. Changes: spaces around the arrow (`true → false`, impl glues `true→false`); render `null` and `""` distinctly via `JSON.stringify` (impl coerces null to `""`); field `text-foreground` not `font-semibold`; `changes.show_more` "Show {count} more…" → "+{count} more fields"; `changes.no_changes` "—" → "no changes recorded" (`Browse.tsx::ChangesList`, `en.json`). Consider extracting `ChangesList` — `Browse.tsx` is 264/300 lines.
12. Show-more threshold 3 (impl) vs 2 (deck).
13. Pagination inside the card footer, always shown, `total.toLocaleString()` ("2,431") (`Browse.tsx`).
14. `align-top` on every cell, not just Time (`Browse.tsx`).
15. Correlation link/banner not in deck — keep or demote (§6).

**5. Backend/props.**
- CSV export: `AL/endpoints/api.py` has only `GET /`. Add a streaming CSV endpoint honouring the same filters (`service.py` iterator + `csv`), permission `audit_log.view`.
- Entity display names: registry only maps class name → URL template + kind label. Add a per-`AuditLink` batch label resolver (or `register_audit_labels` hook), call it from `views.py::browse`, emit `entity.display`; add table name (`__tablename__`) for the tag (`audit_links.py`, `resolve.py`, module `register_audit_links` in users/settings/background_tasks).
- Actor filter: `service.list_entries` does `user_id ==` exact. Resolve name/email → user ids in `views.py` (or accept both: UUID → exact, else `ilike` on users).
- Date range: `from_date`/`to_date` already accepted; if the picker is date-only, treat `to_date` as end-of-day in `views.py`.
- Entity-type dropdown values: `distinct_entity_types()` returns class names ("User"); deck shows `users_user`.

**6. Ambiguities.**
- Lowercase raw values (pills, "system") vs repo i18n capitalisation.
- Type tag: table name, class name, or translated label.
- Export scope (current filter / page / all) and how `changes` is flattened.
- Date range with or without time.
- Actor search semantics (contains on name/email vs exact id).
- Where the correlation pivot lives if not under Time.

---

## Overall ranking (largest gap first)

1. **22 Background tasks** — strip redesign (5 tiles incl. "Succeeded 24h", tinted alarm cards), segmented filter + queue dropdown, "Retry all failed", clickable rows, mono names, tinted pills, relative times, in-card pagination; three backend additions (24h count, queue filter, bulk retry).
2. **23 Task detail** — near-complete restructure: mono title + inline pill + attempt subline (needs `PageShell` extension and `max_retries`), Details reorder/duration/exception footer, side-by-side args/kwargs, terminal traceback with copy + highlight, dialog copy/icon/CTA. Backend need is one prop.
3. **25 Audit log** — visually closest already, but two real backend features (entity display names, CSV export, actor-by-name filter) plus filter-bar grid, date-range picker, and a dozen copy/format changes.
4. **24 Workers** — mostly styling and header placement; one schema field (uptime); "last heartbeat" for offline workers needs new persisted state; the current start-worker command literal is wrong and should be fixed regardless.