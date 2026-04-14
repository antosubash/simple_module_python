# simple-module-{{MODULE_SLUG}}

The `{{MODULE_NAME}}` module for SimpleModule hosts.

## Installation

```bash
pip install simple-module-{{MODULE_SLUG}}
```

A host that installs this package picks it up automatically via
`entry_points`. No additional wiring is required.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Frontend assets (optional)

If this module ships TSX pages:

1. Drop them in `{{PACKAGE_NAME}}/pages/` (the scaffold created the
   directory). One file per Inertia page — e.g. `Browse.tsx`,
   `Detail.tsx`.
2. Build them with your bundler of choice (Vite/esbuild/etc.) into
   `{{PACKAGE_NAME}}/static/dist/`. This directory is **gitignored** —
   only the wheel carries it.
3. Before releasing (`uv build`), rebuild the assets. Your
   `publish.yml` CI should run the bundler before `uv build`; add
   a step after "Install project + dev deps" such as
   `npm ci && npm run build`.

Hosts mount the bundle automatically at
`/modules/{{MODULE_SLUG}}/static` — the generated
`{{MODULE_NAME}}Module.static_mounts()` method returns the directory
when it exists, an empty dict otherwise (so dev without a build step
doesn't fail).

## Continuous integration

Two workflows live under `.github/workflows/`:

- **`ci.yml`** — runs on every push to `main` and on every pull request.
  Installs deps, runs `ruff check`, then `pytest`.
- **`publish.yml`** — runs only when a tag matching `v*` is pushed.
  Re-runs tests, builds the wheel + sdist, and uploads to PyPI via
  trusted publishing (no API token).

## Publishing

One-time PyPI setup (do this before your first release):

1. Create the project's Trusted Publisher entry at
   <https://pypi.org/manage/account/publishing/>:
   - PyPI project name: `simple-module-{{MODULE_SLUG}}`
   - Owner / Repository: your GitHub org + this repo
   - Workflow filename: `publish.yml`
   - Environment (recommended): `pypi`
2. On GitHub → Settings → Environments, create `pypi`. Add required
   reviewers if you want a manual approval gate before every release.

Every release after that is three commands:

```bash
# 1) bump the version in pyproject.toml, commit
# 2) tag
git tag v0.2.0
git push --tags
# 3) done — the publish workflow uploads to PyPI
```

No `PYPI_API_TOKEN` secret exists anywhere. Trusted publishing mints a
short-lived OIDC token scoped to this repo + workflow + environment.

## API-version contract

The `Meta.requires_framework` field declares which `simple-module-core`
versions this module supports. Update the spec on each framework major
bump after verifying compatibility.
