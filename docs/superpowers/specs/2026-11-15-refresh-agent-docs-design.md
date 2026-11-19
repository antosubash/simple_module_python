# Refresh AGENTS.md, CLAUDE.md and README (with a demo GIF)

## Goal and scope

Bring the three entry-point docs back in line with the code at `main@ab178587`, add a tool-neutral
`AGENTS.md`, and put a short demo GIF at the top of the README.

In scope: `AGENTS.md` (new), `CLAUDE.md`, `README.md`, a reproducible GIF recorder script, the
committed GIF, the doc-path checker, and the handful of comments that cite CLAUDE.md sections.

Out of scope: the VitePress docs (`docs/**`) beyond what a moved reference needs, `skills/**`
(none of them cites CLAUDE.md or AGENTS.md), and generating agent files for `smpy new` apps.

## Approach

**`AGENTS.md` is the canonical agent guide; `CLAUDE.md` imports it.** Codex, Cursor, OpenCode and
other agents read `AGENTS.md`; Claude Code reads `CLAUDE.md` and follows its `@AGENTS.md` import.
`CLAUDE.md` keeps only what is Claude Code specific: the `Agent` tool model routing and the Codex
subagent rules from "Working in parallel".

Rejected:
- Symlink `CLAUDE.md -> AGENTS.md`: symlinks break on Windows checkouts and leave no place for
  Claude-only rules.
- Two full copies: they drift, which is the problem this change fixes.

## Design

### AGENTS.md (moved from CLAUDE.md, fixed and trimmed)

Fixes, all verified against the code:
- `make lint` row and CI paragraph: add the locale, doc-path, test-sleep and raw-fetch checks, the
  `docs-build` job, and `alembic check` inside `ci-doctor`.
- Doctor vs dev boot: a dev boot adds `SM012`/`SM031`; `SM025` runs at boot in every environment.
- `make new-module` also runs `smpy openapi gen-types`, so `pages/api.generated.ts` is in the
  commit list.
- "Full list" of make targets points at the root `Makefile`; `docs/reference/make-commands.md`
  covers the scaffolded app's Makefile.
- Middleware order: add Sentry context (when enabled) and the fixed-tenant Tenant middleware when
  `default_tenant` is set.
- Module layout: `models/`, `task_config.py`, `cli.py` are allowed roots; extra root dirs only via
  `DOMAIN_AREAS` in `host/tests/test_module_layout.py`.
- Package count `~23` PyPI packages.

Trims (history and API detail that already lives in the linked docs), keeping every "do/don't"
rule:
- Migrations: drop the root/head SHA list and mislabel history; keep "where, `upgrade heads`,
  `--head <label>@head`, update `test_migration_graph.py` on a new root or head".
- Configuration: keep env → DB → default, no new env vars, `merge_host_settings()`,
  `register_module_settings`; the failure-mode detail stays in `docs/framework/settings.md`.
- Hook bullets, CORS/RateLimit prose, Inertia shared-prop detail, scaffolder internals: one line
  each plus the doc link.

Target: about 400 lines (from 590).

### CLAUDE.md

```
@AGENTS.md

## Claude Code specifics
- Working in parallel: subagent model routing (haiku/sonnet/opus), Codex as a subagent.
```

### README.md

Restructured for someone landing on the repo:
1. One-paragraph pitch, the demo GIF, badges are not added (none exist today).
2. **Build an app**: `uvx --from simple_module_cli@latest smpy new my-app`; first page is the
   `/setup` wizard until an admin exists; presets (`minimal|standard|full`, `--with`); `smpy add`.
3. **Bundled modules**: a table of the 17 modules, one line each.
4. **Work on the framework**: quickstart that states `make dev` needs the sibling
   `../dev-services` stack, and the SQLite-only path (`make dev-api` + `make dev-ui`).
5. Docker (kept, `SM_APP_PORT` sentence fixed).
6. Create a module: `make migration LABEL=orders msg=…` and `branch_labels` on the first revision.
7. Commands table: corrected `make lint`, adds `gen-pages`, `gen-i18n`, `gen-api-types`,
   `test-py`/`test-js`/`test-e2e`, `test-py-pg`, `worker`/`beat`.
8. Configuration: `SM_SECRET_KEY` unset → generated and stored in the DB; env-only bootstrap list
   corrected (`SM_DATABASE_URL`, `SM_ENVIRONMENT`, `SM_SECRET_KEY`, `SM_VITE_DEV_URL`, `SM_DEBUG`,
   `SM_MODULES_ENABLED`, `SM_REDIS_URL`); pool/log/proxy knobs are DB settings that env overrides;
   link `docs/reference/env-vars.md`.
9. Auth providers: the Keycloak caveat names only `permissions` (and `api_tokens`, optional) as
   needing `users`; signup is the "Allow signup" setting, no restart.
10. Architecture: middleware order replaced by a link to `docs/framework/middleware.md` plus the
    short chain; diagnostics list extended.
11. Contributing / for AI agents: `AGENTS.md`, `skills/` and `smpy skills add`; `make lint` runs
    every CI check locally.

### Demo GIF

- `scripts/record_readme_demo.py`: Playwright (already a dev dependency) against a running
  server, 1280×800 viewport, `record_video_dir`. Flow, ~20 s: sign in → dashboard → admin users
  list → a module CRUD page (feature flags: create one) → branding: change the primary colour and
  watch the UI re-theme → doctor panel. Then `ffmpeg` palettegen/paletteuse to a 960-px-wide,
  12 fps GIF.
- Output committed at `docs/assets/readme-demo.gif`, budget ≤ 5 MB. README embeds it by relative
  path, so it renders on GitHub.
- The script takes `--base-url`, `--email`, `--password`, `--out`; the recipe (spare ports, SQLite
  file DB, `smpy users create-admin`) is in its docstring.

### Tooling

- `scripts/check_doc_paths.py` also scans `AGENTS.md`.
- Comments that cite CLAUDE.md sections (middleware-order test, lifespan test, dashboard
  `doctor.py` "§ Diagnostic codes", `docs/framework/invalidation.md`) point at `AGENTS.md`.

## Decisions made

- AGENTS.md canonical + `@AGENTS.md` import in CLAUDE.md (above).
- Moderate trim (~590 → ~400 lines), not a rewrite: every rule stays, history goes.
- GIF content and location as above; no README screenshots beyond the GIF.
- The recorder script is committed (reproducible GIF), but not run in CI.
- No AGENTS.md for scaffolded apps in this change.

## Testing

- `make lint` (doc-path check now covers AGENTS.md; ruff formats Python fences in the docs).
- Unit test for `check_doc_paths.sources()` including `AGENTS.md`, if the checker has a test file;
  otherwise the lint run is the check.
- The recorder script runs once end to end against a live SQLite stack to produce the GIF; I look
  at the frames before committing.
- No browser QA of app pages: nothing in the app changes.

## Risks

- Claude Code's `@AGENTS.md` import must resolve from the repo root. I can't open a fresh session
  from here to watch it load, so it relies on the documented import syntax; `claude` sessions in
  the worktree after the change are the check.
- GIF size: if over budget, drop to 10 fps / 800 px or shorten the flow.
