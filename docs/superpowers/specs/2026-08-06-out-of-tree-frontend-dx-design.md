# Out-of-tree module JS/CSS DX — Design

**Goal:** Make the frontend half of a standalone module repo (a module living
outside this monorepo) work out of the box: correct editor/typecheck setup,
a CI-runnable proof that the module's TSX + CSS compile against the real host
toolchain, and a build path for `static_mounts()` assets.

**Date:** 2026-08-06
**Approach chosen:** Extend `smpy` with a `module` command group + fix the
`create-module` scaffold templates (Approach A). Rejected: template-only
`dev-host/` committed into each module repo (drifts from the framework);
separate `simple_module_devkit` package (release overhead with no benefit over
the existing CLI).

---

## Problem

The `create-module` scaffold and docs assume the monorepo:

1. `tsconfig.json.tpl` maps `@simple-module-py/ui/*` to `../../packages/ui/src/*`
   — a path that only exists inside this repo. Standalone repos get broken
   type-checking and editor IntelliSense out of the box.
2. There is no way to compile the module's frontend standalone. Pages import
   `@simple-module-py/ui/components/...` subpaths and ship `theme.css` /
   `styles.css` that only mean anything inside a host's Vite + Tailwind build —
   so the first signal that something is wrong arrives after publishing, inside
   a consuming host.
3. `docs/module-authoring.md` says "for production builds, ship a pre-bundled
   `static/dist`" — misleading: wheel modules' TSX pages are compiled by the
   *host's* Vite build (via `#module/<pkg>` aliases + `fs.allow`).
   `static/dist` + `static_mounts()` is only for assets *outside* that pipeline
   (vendor JS, widgets, images), and there is no tooling to produce one.
4. The module scaffold has no JS typecheck/lint scripts and its CI runs Python
   only.

Both `@simple-module-py/ui` and `@simple-module-py/tsconfig` are already
published to npm, versioned in lockstep with the framework — the raw materials
exist; the scaffold and CLI just don't use them.

## Deliverables

### 1. Scaffold fixes (editor/typecheck correctness)

`create-module` already distinguishes standalone vs in-repo (`include_ci`
logic, GH #210). The JS templates become variant-aware on the same switch:

- **`tsconfig.json` (standalone variant):** paths resolve via the installed
  npm package:
  `"@simple-module-py/ui/*": ["./node_modules/@simple-module-py/ui/src/*"]`
  (and the same for `@simple-module-py/i18n`). The in-repo variant keeps the
  current `../../packages/*` mapping.
- **`package.json` (standalone variant):** peerDependencies stay as the
  host-contract; add pinned devDependencies so `npm install` + `tsc` work in
  the repo: `@simple-module-py/ui`, `@simple-module-py/tsconfig`,
  `typescript`, `@types/react`, `@types/react-dom` — pinned with the existing
  `{{FRAMEWORK_VERSION}}` mechanism where applicable. Add
  `"scripts": {"typecheck": "tsc --noEmit"}`.
- **`ci.yml` (standalone):** add a JS job — setup-node, `npm ci`,
  `npm run typecheck`, then `uv run smpy module verify`.
  `simple_module_cli` joins the scaffold's `dev` extra.
- **`.gitignore`:** add `.smpy/`.

Rejected alternative: adding an `exports` map to the published
`@simple-module-py/ui` package would remove the need for `paths` everywhere,
but it touches the host's Vite alias machinery and every existing consumer —
out of scope; possible later refactor.

### 2. `smpy module verify`

New `smpy module` Typer group in `framework/cli`. `verify` proves the module's
TSX + `theme.css`/`styles.css` compile against the real host toolchain:

1. Scaffold (or reuse) an ephemeral host at `.smpy/verify-host/` using the
   existing `create-host` templates, with the module wired in as an editable
   path dependency via `[tool.uv.sources]`.
2. Run, in the host: `uv sync` → `npm install` (in `client_app/`) →
   `smpy host gen-pages` → `npm run build` (`tsc && vite build`).
3. Propagate the exit code — CI-friendly. Print the failing step's output.

Details:

- **Caching:** `.smpy/verify-host/` persists between runs (gitignored), so
  warm re-runs skip scaffolding and get fast idempotent `npm install`.
  `--fresh` deletes and rebuilds it.
- **Version:** the ephemeral host is pinned to the CLI's installed framework
  version via the existing `resolve_framework_version()` — verify passing ≈
  the module working in a freshly scaffolded host of that version.
- **No DB / no boot:** `gen-pages` only does discovery + file emission, so
  verify needs no database, no `.env`, no running server, and no auth module.
- **Preconditions:** run from the module repo root; error clearly if no
  `[project.entry-points.simple_module]` is found in `pyproject.toml`.

### 3. `smpy module build`

For `static_mounts()` assets only (vendor JS, widgets — outside the Inertia
page pipeline):

- **Convention:** sources in `<pkg>/assets_src/`, output to
  `<pkg>/static/dist/`.
- Reuses the verify-host's node toolchain (same bootstrap path as `verify`),
  generating a Vite **lib-mode** config on the fly — no Vite devDependency in
  the module repo.
- Warns if the module's `pyproject.toml` lacks the hatch `force-include` for
  `static/dist` (it is gitignored, so wheels would silently omit it).
- Errors clearly if `assets_src/` does not exist (the command is opt-in; most
  modules never need it).

## Testing

- Unit tests for the orchestration in `framework/cli/tests`, with subprocess
  boundaries (uv/npm invocations) mocked: scaffold reuse vs `--fresh`,
  editable-source wiring, precondition errors, exit-code propagation,
  force-include warning.
- One real end-to-end test (scaffold a module → `verify` green) behind the
  existing `e2e` marker, since it needs npm and network access.
- Template-variant tests: standalone vs in-repo emit the right
  `tsconfig.json` / `package.json` / `ci.yml`.

## Docs

- New "Developing out-of-tree" section in `docs/module-authoring.md`: the
  tsconfig/npm story, `verify` in CI, `build` for static assets.
- Fix the misleading "ship a pre-bundled `static/dist`" wording in the
  Frontend assets section: pages are built by the consuming host;
  `static/dist` is only for extra-pipeline assets.

## Out of scope (this round)

- A live preview/dev-server loop for out-of-tree modules (`smpy module dev`) —
  the largest remaining gap, deliberately deferred.
- `exports` map on the published npm packages.
- Any change to how in-repo (`modules/*`) development works.
