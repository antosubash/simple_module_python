# PyPI release `v0.0.1` — design

## Goal

Publish the `simple_module_python` framework to PyPI so third parties can start new projects with a one-line `uvx simple-module new my-app` generator. This is the first public release: everything currently lives as workspace-linked packages in one monorepo.

## Scope

In scope for `v0.0.1`:

1. PyPI publication of **all 14 Python packages** (4 framework + 10 modules).
2. **Per-package metadata hygiene** — real descriptions, keywords, classifiers, URLs, license, and **substantive READMEs on every package**.
3. **`simple-module new <app>` CLI generator** that scaffolds a working app with `users + dashboard + permissions` pre-wired.
4. **Manual-dispatch GitHub Actions release workflow** using PyPI Trusted Publishing (OIDC) — no long-lived tokens.
5. **Lockstep version bump script** — one invocation bumps every `pyproject.toml` atomically.
6. **TestPyPI rehearsal workflow** to validate the pipeline before burning PyPI version numbers.
7. Repo-level prep — root `LICENSE`, `CHANGELOG.md`, release docs, README update.

Out of scope (deferred):

- Publishing `packages/ui`, `packages/i18n`, `packages/tsconfig` to npm (they vendor into generated apps instead).
- A hosted docs site (Sphinx / Docusaurus / similar).
- Automated `CHANGELOG.md` generation.
- A separate `simple-module-template` package.
- Independent SemVer per package (revisit post-1.0).
- Version-compatibility matrix tooling (`pip check` harness).

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
| 8 | JS packages vendor into generated app; not published to npm this release | Reduces surface area; the user owns and can edit those files like shadcn. |

## Open items (need confirmation before implementation plan)

- **PyPI account owner** — assumed `antosubash` based on current `pyproject.toml` authors. Confirm, then this user must log into pypi.org and create 14 Trusted Publisher configs (one per project name).
- **GitHub repo URL** — assumed `https://github.com/antosubash/simple_module_python`. Used in `project.urls`. Confirm or provide.

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
keywords = ["fastapi", "modular-monolith", "inertia", "sqlmodel", "<domain>"]
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

Every one of the 14 packages gets a dedicated `README.md` in its package root. READMEs are short, substantive, and concrete — not filler. Shared template:

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
├── package.json            # npm workspaces for vendored packages
├── client_app/             # Vite + Inertia root, Tailwind, shadcn bootstrap
│   ├── main.tsx
│   ├── pages/Home.tsx
│   ├── vite.config.ts
│   └── tsconfig.json
└── packages/               # vendored from monorepo — user owns these
    ├── ui/
    ├── i18n/
    └── tsconfig/
```

### 4. Version bump script (Workstream 4)

`scripts/bump_version.py`:

```
usage: bump_version.py <new_version> [--check] [--dry-run]
```

Behavior:

- Walks all 14 `pyproject.toml` files.
- Uses `tomlkit` to preserve formatting and comments.
- Rewrites `project.version` to `<new_version>`.
- Rewrites every `simple-module-*` entry in `project.dependencies` to `==<new_version>`.
- In `--check` mode, exits non-zero if any file is out of sync with `<new_version>`. Used in CI as a safety check.
- In `--dry-run` mode, prints the diff without writing.

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
2. Install `uv`.
3. Validate `version` input matches `\d+\.\d+\.\d+`.
4. Run `python scripts/bump_version.py $VERSION`.
5. Commit and tag (`git tag v$VERSION`) — bot identity.
6. Push commit + tag directly to `main` (branch protection admin bypass for the GitHub Actions bot).
7. `uv build --all-packages` → produces `dist/*.whl` + `dist/*.tar.gz` for all 14 packages.
8. **Matrix job** — one publish job per package using `pypa/gh-action-pypi-publish@release/v1`. Matrix distributes artifacts by package name. Each job uses the project's Trusted Publisher config.
9. **Smoke-test job** (runs after publish):
   - `pipx install simple-module-hosting==$VERSION` (from the target PyPI/TestPyPI).
   - `simple-module new /tmp/smoke --yes --db sqlite --no-tenancy`.
   - `cd /tmp/smoke && make install && make test`.
   - Fails the workflow if any step errors.
10. Create a GitHub Release on the tag with a link to the CHANGELOG entry.

Separate file `.github/workflows/release-test.yml` targets TestPyPI only — same workflow body, different Trusted Publisher context. The main `release.yml` `target` input makes this somewhat redundant, so we consolidate into one file and use the `target` input to branch.

### 6. PyPI Trusted Publisher setup (Workstream 6, manual)

One-time setup documented in `docs/release.md`. For each of the 14 project names, on pypi.org and test.pypi.org:

- Register the project name (create an empty "pending publisher" before the first upload).
- Add a GitHub Actions Trusted Publisher: repo = `antosubash/simple_module_python`, workflow = `release.yml`, environment = `pypi` (or `testpypi`).
- Two GitHub Environments (`pypi`, `testpypi`) exist in repo settings; the publish jobs reference the right one.

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
pyproject.toml × 14  →  uv build --all-packages  →  dist/*.whl + dist/*.tar.gz  →  PyPI (per-project Trusted Publisher)
                                                                                ↓
                                                                        pipx install simple-module-hosting
                                                                                ↓
                                                                        sm new /tmp/smoke  →  make test ✅
```

## Error handling

- **Bump script failure** (malformed `pyproject.toml`) — script aborts with line number; no files modified (write to temp + rename).
- **PyPI rejects upload** (version already exists) — publish job fails; prior publish jobs that succeeded are immutable on PyPI. Operator bumps the patch version and re-runs. The `release.yml` exits non-zero so the tag can be removed.
- **Smoke test fails** — workflow fails; packages are already on PyPI and cannot be unpublished. Operator yanks the release via PyPI UI and bumps to the next patch. This is an accepted limitation of PyPI; the TestPyPI rehearsal workflow is the mitigation.
- **Trusted Publisher misconfigured** — fails with a clear error from the PyPA action. Operator fixes the pypi.org config and re-runs.

## Testing

1. **Bump script unit tests** — `scripts/tests/test_bump_version.py` with fixtures covering: bump succeeds, dependency pins rewrite, `--check` mode, malformed TOML, missing simple-module-* dep stays absent, simple-module-* with existing pin gets rewritten.
2. **Local dry run** — `make release-check version=0.0.1` confirms the bump is idempotent.
3. **TestPyPI rehearsal** — run `release.yml` with `target=testpypi` against version `0.0.1a0` (PEP 440 pre-release). Verifies the entire workflow end-to-end on a sacrificial version. This must pass before the real PyPI run.
4. **Smoke job** as part of the workflow itself — `sm new` + `make test` in the generated app.
5. **Per-package README smoke** — `scripts/check_readmes.py` verifies every published package has a `README.md` > 500 bytes and contains the required H1 + "Install" + "Usage" sections. Runs in `make lint`.

## Build order

This is also the phasing for the implementation plan:

1. **Metadata hygiene + READMEs** (Workstreams 1 + 2) — every `pyproject.toml` gets real description, classifiers, URLs, license fields; every package gets a real `README.md`; root `LICENSE` added.
2. **Bump script + tests** (Workstream 4) — unit-tested in isolation before any workflow depends on it.
3. **`sm new` CLI + template** (Workstream 3) — must work locally (`uv run sm new /tmp/foo`) before the smoke test can rely on it.
4. **TestPyPI workflow** (Workstream 5, `target=testpypi`) — publish `0.0.1a0` end-to-end, verify smoke test passes.
5. **Trusted Publisher setup on PyPI** (Workstream 6, manual) — operator does this between step 4 and step 6.
6. **Real PyPI release** — run `release.yml` with `target=pypi`, version `0.0.1`.
7. **Docs + CHANGELOG + README updates** (Workstream 7) — can happen in parallel with step 3, lands before step 6.

Each step can be validated independently before moving to the next.
