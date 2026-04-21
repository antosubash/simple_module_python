# First public release `v0.0.1` — design

## Goal

Publish the `simple_module_python` framework to PyPI **and npm** so third parties can start new projects with a one-line `uvx simple-module new my-app` generator. This is the first public release: everything currently lives as workspace-linked packages in one monorepo.

## Scope

In scope for `v0.0.1`:

1. **PyPI publication of all 14 Python packages** (4 framework + 10 modules).
2. **npm publication of 3 JS packages** — `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig` — under the `@simple-module-py` npm org.
3. **Per-package metadata hygiene** across both ecosystems — real descriptions, keywords, classifiers/labels, URLs, license, and **substantive READMEs on every package** (17 total).
4. **`simple-module new <app>` CLI generator** that scaffolds a working app with `users + dashboard + permissions` pre-wired, consuming JS packages from npm as regular dependencies.
5. **Manual-dispatch GitHub Actions release workflow** using PyPI Trusted Publishing (OIDC) for Python and npm Trusted Publishers (OIDC, GA as of 2024) for JS — no long-lived tokens on either side.
6. **Lockstep version bump script** — one invocation bumps every `pyproject.toml` *and* every `package.json` atomically. All 17 packages move together.
7. **TestPyPI rehearsal workflow** to validate the pipeline before burning PyPI version numbers. (npm has no equivalent staging registry; we mitigate via a `--dry-run` pack step plus pre-publish lint.)
8. Repo-level prep — root `LICENSE`, `CHANGELOG.md`, release docs, README update.

Out of scope (deferred):

- A hosted docs site (Sphinx / Docusaurus / similar).
- Automated `CHANGELOG.md` generation.
- A separate `simple-module-template` package.
- Independent SemVer per package (revisit post-1.0).
- Version-compatibility matrix tooling (`pip check` / `npm ls` harness).
- Bundled build output for the JS packages (we ship source + types; see below).

## Key decisions

| # | Decision | Rationale |
|---|---|---|
| 1 | All 14 packages to PyPI, not a curated subset | User wants every module installable via `pip install simple-module-<name>`. |
| 2 | Lockstep versioning, all packages bump together | Framework internals are tightly coupled pre-1.0; independent SemVer would leak breakage. |
| 3 | Start at `0.0.1`; future bumps are patch until real releases dictate otherwise | Explicitly signals "we might still break things". |
| 4 | Manual-dispatch GH Actions + Trusted Publishing | No API tokens stored; release is reproducible and auditable. |
| 5 | Generator pre-wires users + dashboard + permissions | The 95% default — users can remove what they don't want. |
| 6 | Template ships inside `simple-module-hosting` | Reuses existing precedent (`simple_module_hosting/templates/` already hosts the module scaffolder). Keeps release matrix at 14. |
| 7 | **MIT** license across all 14 packages | Permissive, ubiquitous, no copyleft friction for downstream consumers. |
| 8 | JS packages publish to npm under `@simple-module-py` scope; generated app depends on them like any npm dep | Consistent dependency story across both ecosystems; users don't fork the UI library by default. Power users can still `npm pack` + vendor if they want shadcn-style ownership. |
| 9 | JS packages ship **source** (`.ts` / `.tsx`) + types, not bundled output | Consumers are always Vite-backed apps that will transpile TS anyway. Avoids adding a `tsup`/`rollup` build step and a `dist/` folder. Matches how Radix UI source-ships its primitives. |
| 10 | npm packages version in lockstep with Python — same version string across all 17 | One `0.0.1` means one release; operators don't have to reason about two version axes. |
| 11 | **Every package (all 17) MUST include `simple-module` as a keyword/tag** | Makes the whole family discoverable with a single search on PyPI (`?q=simple-module`) and npm (`?q=keywords:simple-module`). Enforced by `scripts/check_metadata.py` in `make lint`. |

## Open items (need confirmation before implementation plan)

- **PyPI account owner** — assumed `antosubash`. Confirm, then this user must create 14 Trusted Publisher configs on pypi.org + test.pypi.org.
- **npm org + account owner** — assumed the `@simple-module-py` npm org is owned by `antosubash` (or will be created by them). Trusted Publishers are configured per-package on npmjs.com pointing at the same GitHub repo + `release.yml` workflow.
- **GitHub repo URL** — assumed `https://github.com/antosubash/simple_module_python`. Used in `project.urls` (Python) and `repository.url` (npm).

## Architecture

### 1. Package metadata hygiene (Workstream 1)

Every published `pyproject.toml` conforms to this template:

```toml
[project]
name = "simple-module-<name>"
version = "0.0.1"
description = "<one-sentence description of what this package does>"
readme = "README.md"
license = "MIT"
license-files = ["LICENSE"]
requires-python = ">=3.12"
authors = [{ name = "Anto Subash", email = "antosubash@live.com" }]
keywords = ["simple-module", "fastapi", "modular-monolith", "inertia", "sqlmodel", "<domain>"]  # "simple-module" is REQUIRED on every package
classifiers = [
    "Development Status :: 3 - Alpha",
    "Framework :: FastAPI",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Operating System :: OS Independent",
    "Programming Language :: Python :: 3",
    "Programming Language :: Python :: 3.12",
    "Topic :: Internet :: WWW/HTTP",
    "Topic :: Software Development :: Libraries :: Application Frameworks",
    "Typing :: Typed",
]
dependencies = [
    # PyPI-shaped deps with exact pins for inter-package simple-module-* deps
    "simple-module-core==0.0.1",
    # ... third-party deps unchanged
]

[project.urls]
Homepage = "https://github.com/antosubash/simple_module_python"
Repository = "https://github.com/antosubash/simple_module_python"
Issues = "https://github.com/antosubash/simple_module_python/issues"
Changelog = "https://github.com/antosubash/simple_module_python/blob/main/CHANGELOG.md"

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["<import_name>"]

[tool.uv.sources]
# Workspace sources remain — uv ignores these when building for PyPI.
simple-module-core = { workspace = true }
```

A root `LICENSE` (MIT, copyright "2026 Anto Subash") is the single source of truth. Each package references it via `license-files` so the license is force-included in wheels — Hatchling resolves `../../LICENSE` at build time.

### 2. Per-package READMEs (Workstream 2 — first-class deliverable)

Every one of the **17 packages** (14 Python + 3 npm) gets a dedicated `README.md` in its package root. READMEs are short, substantive, and concrete — not filler. Shared template (adapted slightly for Python vs JS):

```markdown
# simple-module-<name>

<One-paragraph description: what problem this package solves and where it fits in the simple_module framework.>

Part of [simple_module_python](https://github.com/antosubash/simple_module_python), a modular-monolith framework for Python.

## Install

```bash
pip install simple-module-<name>
```

Most users don't install this directly — it's pulled in by `simple-module new` or as a dependency of another module.

## What it provides

- <Bullet: concrete capability 1>
- <Bullet: concrete capability 2>
- <Bullet: concrete capability 3>

## Usage

<One minimal code example or CLI invocation showing the primary use case. No more than 20 lines.>

## Depends on

- `simple-module-core` (and any others)

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
```

Per-package specifics below. Each README is ~60–120 lines. The "Usage" snippet must be **runnable** as-is — no pseudocode.

| Package | README must cover |
|---|---|
| `simple-module-core` | `ModuleBase` + `ModuleMeta` example, lifecycle hook list, entry-points declaration snippet, `discover_modules()` mention. |
| `simple-module-db` | `create_module_base(name)` example, standard mixins (`AuditMixin`, `SoftDeleteMixin`, `MultiTenantMixin`, `VersionedMixin`), auto-commit-on-flush rule. |
| `simple-module-hosting` | `create_app(settings)` minimal `main.py` snippet, middleware pipeline overview, `sm` / `simple-module` CLI commands (`new`, `doctor`) and note that both names work. |
| `simple-module-testing` | Automatic fixture loading via `pytest11` entry point, the fixtures provided (`app`, `client`, `db_session`, `authenticated_client`, `settings`). |
| `simple-module-users` | Email+password auth, admin invite flow, `SM_USERS_*` settings, `sm-users create-admin` CLI. |
| `simple-module-dashboard` | Adds `/dashboard` landing page for authenticated users, menu entry registration. |
| `simple-module-permissions` | RBAC primitives, `@require_permission` decorator, admin UI. |
| `simple-module-auth` | Session middleware, login/logout primitives (note: distinct from `users` — clarify in the README). |
| `simple-module-background-tasks` | Task queue primitives, how to register background jobs. |
| `simple-module-file-storage` | Upload endpoints, S3/local backend switching via `SM_FILE_STORAGE_*`. |
| `simple-module-datasets` | Geospatial/tabular dataset upload module — use cases, supported formats. |
| `simple-module-feature-flags` | Per-tenant flag overrides, consumer API. |
| `simple-module-products` | Example CRUD module — explicitly labelled as a reference / demo. |
| `simple-module-settings` | Runtime settings UI, where modules plug settings panels. |
| `@simple-module-py/ui` | shadcn-derived React components (`Button`, `Card`, `Form`, layouts). Peer-deps on React 19. Example: `import { Button } from "@simple-module-py/ui"`. |
| `@simple-module-py/i18n` | `i18next` + `react-i18next` glue for framework i18n. Hook API, namespace conventions, how modules register locales. |
| `@simple-module-py/tsconfig` | Shared `base.json` TS config. Install + `extends: "@simple-module-py/tsconfig/base.json"` in consumer `tsconfig.json`. |

### 2b. npm package metadata hygiene (Workstream 2b)

All three JS packages currently have `"private": true` and minimal metadata. Each needs the following shape:

```jsonc
{
  "name": "@simple-module-py/<name>",
  "version": "0.0.1",
  "description": "<one-sentence description>",
  "keywords": ["simple-module", "<domain>"],    // "simple-module" is REQUIRED on every package
  "homepage": "https://github.com/antosubash/simple_module_python#readme",
  "bugs": "https://github.com/antosubash/simple_module_python/issues",
  "repository": {
    "type": "git",
    "url": "git+https://github.com/antosubash/simple_module_python.git",
    "directory": "packages/<name>"
  },
  "license": "MIT",
  "author": "Anto Subash <antosubash@live.com>",
  "type": "module",
  "main": "src/index.ts",
  "types": "src/index.ts",
  "exports": {
    ".": {
      "types": "./src/index.ts",
      "default": "./src/index.ts"
    },
    "./*": "./src/*"
  },
  "files": ["src", "README.md", "LICENSE"],
  "publishConfig": { "access": "public" },
  "peerDependencies": { "react": "^19.0.0" },   // ui + i18n only
  "dependencies": { /* runtime deps */ },
  "devDependencies": { /* build + lint */ }
}
```

Specifics per package:

- **`@simple-module-py/tsconfig`** — already close. Add `version`, `license`, `repository`, `homepage`, `publishConfig.access=public`, drop `"private": true`. Files stay `["base.json"]`. No React dep.
- **`@simple-module-py/i18n`** — move `react`, `react-i18next`, `i18next` from `dependencies` to `peerDependencies` where appropriate (React must be a peer to avoid duplicate-React bugs; i18next stays runtime).
- **`@simple-module-py/ui`** — move `react` to `peerDependencies`. Replace the `"@simple-module-py/i18n": "*"` workspace wildcard with an exact `"0.0.1"` pin (rewritten by the bump script on every release).

**Shipping source, not built output.** The packages export `.ts` / `.tsx` directly. Vite (and any modern bundler) handles TypeScript transparently. This means:

- No `tsup` / `rollup` / `tsc --emit` build step.
- `files` includes `src/` so `.ts` sources are in the tarball.
- Consumers' `tsconfig.json` must have `"allowJs": false` (default) and resolve `.ts` via bundler — already the case with Vite.

### 3. `sm` / `simple-module` CLI generator (Workstream 3)

New `new` subcommand on the existing Click CLI in `simple_module_hosting/cli.py`.

**Both `sm` and `simple-module` work as CLI entry points** — they are aliases for the same underlying command. This is declared in `framework/hosting/pyproject.toml`:

```toml
[project.scripts]
sm = "simple_module_hosting.cli:main"
simple-module = "simple_module_hosting.cli:main"
```

`sm` stays as the short form for daily use; `simple-module` is the discoverable long form that matches the package namespace (what users first encounter on PyPI). Both expose the full command tree — `new`, `doctor`, future subcommands — identically.

**Interactive:** `simple-module new my-app` *or* `sm new my-app`
**Scripted:** `simple-module new my-app --db sqlite --no-tenancy --yes`

Flags:

- `--db {sqlite|postgres}` (default: prompt; CI uses sqlite)
- `--tenancy / --no-tenancy` (default: off)
- `--yes / -y` — accept defaults, no prompts
- `--no-install` — skip `uv sync` / `npm install` / `alembic upgrade head` post-generate

Implementation:

- Template at `framework/hosting/simple_module_hosting/templates/app/` with Jinja substitution on `__APP_NAME__`, `__SECRET_KEY__`, `__DB_URL__`, `__TENANCY__`.
- `__SECRET_KEY__` auto-filled with `secrets.token_urlsafe(32)` at generation time.
- Template discovery uses `importlib.resources` so it works both in editable-install (dev) and wheel-installed contexts.
- Post-generate, optionally runs `uv sync` + `npm install` + `alembic upgrade head` in the new directory (controllable via `--no-install`).

**Template contents:**

```
my-app/
├── pyproject.toml          # deps: hosting + users + dashboard + permissions + testing[dev]
├── main.py                 # create_app() + uvicorn entry point
├── alembic.ini
├── migrations/
│   ├── env.py              # build_module_metadata() boilerplate
│   └── versions/           # empty; first migration generated by user
├── .env.example            # populated with generated SECRET_KEY, DB URL
├── Makefile                # install, dev, test, lint, migrate, migration
├── README.md               # links to framework docs
├── package.json            # deps: @simple-module-py/ui, @simple-module-py/i18n, @simple-module-py/tsconfig
├── tsconfig.json           # extends "@simple-module-py/tsconfig/base.json"
└── client_app/             # Vite + Inertia root, Tailwind, shadcn bootstrap
    ├── main.tsx
    ├── pages/Home.tsx
    ├── vite.config.ts
    └── tsconfig.json
```

The `packages/` folder from the monorepo is **not** vendored. The generated app consumes `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig` straight from npm, pinned to the same version as the Python packages it was generated with. This keeps the scaffold small and puts upgrades on a single track (`npm update && uv sync`). A user who wants to own UI components can `cp -r node_modules/@simple-module-py/ui/src packages/ui-local` post-generate — documented in the generator's output README.

### 4. Version bump script (Workstream 4)

`scripts/bump_version.py`:

```
usage: bump_version.py <new_version> [--check] [--dry-run]
```

Behavior — Python side:

- Walks all 14 `pyproject.toml` files.
- Uses `tomlkit` to preserve formatting and comments.
- Rewrites `project.version` to `<new_version>`.
- Rewrites every `simple-module-*` entry in `project.dependencies` to `==<new_version>`.

Behavior — JS side:

- Walks all 3 `packages/*/package.json` files.
- Uses `json` (stdlib) with a custom writer that preserves trailing newlines; key order is stable because `json.dumps(..., indent=2, sort_keys=False)` preserves insertion order and Python 3.7+ `dict` is ordered.
- Rewrites `version` to `<new_version>`.
- Rewrites every `@simple-module-py/*` entry in `dependencies` / `devDependencies` / `peerDependencies` to exactly `<new_version>`.
- Leaves `package-lock.json` alone; CI regenerates it via `npm install` during build.

Cross-cutting:

- In `--check` mode, exits non-zero if any of the 17 files is out of sync with `<new_version>`. Used in CI as a safety check.
- In `--dry-run` mode, prints a unified diff for each file without writing.
- Exit code 0 only if every file was updated successfully; any parse error aborts and reverts (write to temp + rename atomically).

Makefile target: `make release-check version=X.Y.Z` — runs `--check` locally.

### 5. Release workflow (Workstream 5)

`.github/workflows/release.yml` — `workflow_dispatch`:

```yaml
on:
  workflow_dispatch:
    inputs:
      version:
        description: "Version to release (e.g., 0.0.1)"
        required: true
        type: string
      target:
        description: "PyPI target"
        type: choice
        options: [pypi, testpypi]
        default: pypi
```

Steps:

1. Checkout `main`.
2. Install `uv` and Node.js 20+.
3. Validate `version` input matches `\d+\.\d+\.\d+`.
4. Run `python scripts/bump_version.py $VERSION` — bumps both 14 `pyproject.toml` and 3 `package.json` files.
5. `npm install` — regenerate `package-lock.json` at the new versions; fail if it produces a non-trivial diff beyond the version bumps.
6. Commit and tag (`git tag v$VERSION`) — bot identity.
7. Push commit + tag directly to `main` (branch protection admin bypass for the GitHub Actions bot).
8. **Build phase (parallel):**
   - `uv build --all-packages` → `dist-py/*.whl` + `dist-py/*.tar.gz`.
   - For each of 3 npm packages: `npm pack --pack-destination dist-npm packages/<name>` → `dist-npm/simple-module-<name>-$VERSION.tgz`. This also runs `npm publish --dry-run` equivalent validation.
9. **Python publish matrix** — one job per Python package using `pypa/gh-action-pypi-publish@release/v1`. Each job uses the project's Trusted Publisher config; target PyPI or TestPyPI based on the workflow input.
10. **npm publish matrix** — one job per npm package using `npm publish --provenance --access public`. Authentication via npm Trusted Publishers (OIDC, no `NPM_TOKEN`). If `target=testpypi`, the npm jobs are **skipped** (there is no TestNpm) and logged as skipped.
11. **Smoke-test job** (runs after publish, `target=pypi` only):
    - `pipx install simple-module-hosting==$VERSION`.
    - `simple-module new /tmp/smoke --yes --db sqlite --no-tenancy`.
    - `cd /tmp/smoke && make install && make test` — exercises both `uv sync` (Python deps from PyPI) and `npm install` (JS deps from npm).
    - Fails the workflow if any step errors.
12. Create a GitHub Release on the tag with a link to the CHANGELOG entry.

Separate file `.github/workflows/release-test.yml` targets TestPyPI only — same workflow body, different Trusted Publisher context. The main `release.yml` `target` input makes this somewhat redundant, so we consolidate into one file and use the `target` input to branch.

### 6. Trusted Publisher setup (Workstream 6, manual)

One-time setup documented in `docs/release.md`.

**PyPI + TestPyPI** — for each of the 14 project names, on pypi.org and test.pypi.org:

- Register the project name (create an empty "pending publisher" before the first upload).
- Add a GitHub Actions Trusted Publisher: repo = `antosubash/simple_module_python`, workflow = `release.yml`, environment = `pypi` (or `testpypi`).

**npm** — on npmjs.com:

- Create the `@simple-module-py` scope (org) if it does not exist.
- For each of `@simple-module-py/ui`, `@simple-module-py/i18n`, `@simple-module-py/tsconfig`: publish an initial empty stub manually *or* use npm's [pending-publisher support](https://docs.npmjs.com/trusted-publishers) where supported, then add a GitHub Actions Trusted Publisher: repo = `antosubash/simple_module_python`, workflow file = `.github/workflows/release.yml`, environment = `npm`.
- Three GitHub Environments (`pypi`, `testpypi`, `npm`) exist in repo settings; the publish jobs reference the right one.

### 7. Repo-level prep (Workstream 7)

- **Root `LICENSE`** — MIT, "Copyright (c) 2026 Anto Subash".
- **Root `README.md`** — add a "Use in a new project" section at the top showing `uvx simple-module new my-app` and linking to per-module READMEs.
- **Root `CHANGELOG.md`** — seeded with a `0.0.1 — Initial PyPI release` entry that enumerates shipped packages.
- **`docs/release.md`** — PyPI onboarding walkthrough + "how to cut a release".
- **Remove stale fields** in every `pyproject.toml`: `description = "Add your description here"` placeholders currently in 3 of 4 framework packages.

## Data flow

There is no runtime data flow in this work — it's build- and release-time.

Build-time flow:

```
pyproject.toml × 14  ─┐
                      ├─→  scripts/bump_version.py $VERSION  ─→  commit + tag
package.json    × 3   ─┘                                              │
                                                                      ▼
                               uv build --all-packages   →   dist-py/*.whl + *.tar.gz   →   PyPI  (Trusted Publisher × 14)
                               npm pack packages/*        →   dist-npm/*.tgz             →   npm   (Trusted Publisher × 3)
                                                                                                  │
                                                                                                  ▼
                                       pipx install simple-module-hosting==$VERSION
                                                    │
                                                    ▼
                                       sm new /tmp/smoke  →  make install  (uv sync + npm install)  →  make test ✅
```

## Error handling

- **Bump script failure** (malformed `pyproject.toml` or `package.json`) — script aborts with file + line number; no files modified (write to temp + rename; either all 17 files get updated or none do).
- **PyPI rejects upload** (version already exists) — publish job fails; prior publish jobs that succeeded are immutable on PyPI. Operator bumps the patch version and re-runs. The `release.yml` exits non-zero so the tag can be removed.
- **npm rejects upload** (version already exists) — same as PyPI. npm permits `npm unpublish` within 72 hours of publish for emergency rollback, but the lockstep policy is "bump to next patch" for consistency with PyPI.
- **Partial publish (PyPI succeeded, npm failed or vice versa)** — the workflow fails loudly. The operator fixes the cause (usually Trusted Publisher config), then bumps to the next patch and re-runs. Prior-registry uploads stay at the previous version; we do not attempt to recover a mixed-version release. Documented as a known-fragile edge case in `docs/release.md`.
- **Smoke test fails** — workflow fails; packages are already published and cannot be unpublished (PyPI) or only within a 72-hour window (npm). Operator yanks the PyPI release and unpublishes the npm packages if within window, then bumps to the next patch. This is an accepted cost; the TestPyPI rehearsal + `npm pack` smoke are the mitigations.
- **Trusted Publisher misconfigured** — fails with a clear error from the PyPA / npm publish action. Operator fixes the registry config and re-runs.

## Testing

1. **Bump script unit tests** — `scripts/tests/test_bump_version.py` with fixtures covering: Python bump succeeds, Python dep pins rewrite, npm version bump succeeds, `@simple-module-py/*` deps rewrite across `dependencies` / `devDependencies` / `peerDependencies`, `--check` mode, malformed TOML / JSON aborts cleanly, unrelated third-party deps stay untouched.
2. **Local dry run** — `make release-check version=0.0.1` confirms the bump is idempotent across all 17 files.
3. **TestPyPI + local `npm pack` rehearsal** — run `release.yml` with `target=testpypi` against version `0.0.1a0` (PEP 440 pre-release). Python side publishes to TestPyPI end-to-end; npm side runs `npm pack --dry-run` on every JS package and uploads the resulting `.tgz` tarballs as workflow artifacts so they can be inspected (or `npm install`ed from a file path) without burning an npm version. This must pass before the real run.
4. **Smoke job** as part of the workflow itself (real run only) — `sm new` + `make test` + `npm install` in the generated app, verifying both PyPI and npm packages resolve.
5. **Per-package README smoke** — `scripts/check_readmes.py` verifies every one of the 17 published packages has a `README.md` > 500 bytes and contains the required H1 + "Install" + "Usage" sections. Runs in `make lint`.
6. **Per-package metadata smoke** — `scripts/check_metadata.py` verifies every one of the 17 packages has:
   - A non-placeholder `description` (not "Add your description here").
   - `"simple-module"` in `keywords`.
   - `license = "MIT"` (Python) or `"license": "MIT"` (npm).
   - A `repository` / `[project.urls].Repository` pointing at the canonical GitHub URL.
   - For npm: `publishConfig.access == "public"` and `"private"` unset or `false`.
   Exits non-zero on any violation. Runs in `make lint`.
7. **npm pack-and-install smoke (local)** — `scripts/smoke_npm_packs.sh` runs `npm pack` on all 3 JS packages and installs them into a temp directory with a minimal Vite app, verifying the published tarballs actually work. Runs before the release workflow is triggered.

## Build order

This is also the phasing for the implementation plan:

1. **Metadata hygiene + READMEs** (Workstreams 1 + 2 + 2b) — every `pyproject.toml` and `package.json` gets real description, classifiers/keywords, URLs, license fields; every one of the 17 packages gets a real `README.md`; root `LICENSE` added.
2. **Bump script + tests** (Workstream 4) — unit-tested in isolation before any workflow depends on it. Covers both TOML and JSON sides.
3. **`sm new` CLI + template** (Workstream 3) — must work locally (`uv run sm new /tmp/foo`) before the smoke test can rely on it. Template references `@simple-module-py/*` npm packages by version.
4. **Local npm pack smoke + TestPyPI rehearsal** (Workstream 5, `target=testpypi`) — publish `0.0.1a0` to TestPyPI + `npm pack` all JS packages locally; inspect artifacts.
5. **Trusted Publisher setup** (Workstream 6, manual) — operator configures PyPI + TestPyPI + npm. Happens between step 4 and step 6.
6. **Real release** — run `release.yml` with `target=pypi`, version `0.0.1`. Publishes 14 Python + 3 npm packages, runs smoke.
7. **Docs + CHANGELOG + README updates** (Workstream 7) — can happen in parallel with step 3, lands before step 6.

Each step can be validated independently before moving to the next.
