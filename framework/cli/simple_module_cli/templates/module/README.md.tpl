# simple_module_{{PACKAGE_NAME}}

The `{{MODULE_NAME}}` module for SimpleModule hosts.

## Installation

```bash
pip install simple_module_{{PACKAGE_NAME}}
```

A host that installs this package picks it up automatically via
`entry_points`. No additional wiring is required.

## Development

```bash
uv sync --extra dev
uv run pytest
```

## Inertia pages

The pages read their text from `{{PACKAGE_NAME}}/locales/en.json`. Inside an
app they use `t(keys.{{PACKAGE_NAME}}.…)`; the host's `make gen-i18n` (also run
by `make install`, `make build` and each dev boot) adds this module to `keys`.
A standalone module repo has no host to generate them, so its scaffolded pages
use literal English: once the module is installed in an app, switch a string
to `t(keys.{{PACKAGE_NAME}}.browse.title)` and the like.

Place TSX pages in `{{PACKAGE_NAME}}/pages/`, one file per Inertia page.
The host discovers and bundles these sources in its own frontend build.
Module releases need no prebundling or `static/dist/` output for Inertia pages.

## Styling (optional)

This module can ship CSS that lands in the host's Tailwind build with no
wiring on the host side. Create either file beside `pages/` and it is
picked up automatically — the scaffold deliberately does not create them
empty, since a file that is always imported but usually empty is noise:

- `{{PACKAGE_NAME}}/theme.css` — `@theme` tokens, `@custom-variant`,
  `@font-face`. Imported **unlayered**, because a `@theme` block inside a
  cascade layer registers nothing.
- `{{PACKAGE_NAME}}/styles.css` — component rules, keyframes, vendor CSS.
  Imported into **`layer(components)`**, so these rules always lose to a
  Tailwind utility and a consuming app can still override them.

Putting a construct in the wrong file builds fine but cascades in a way you
probably did not intend, so `make doctor` warns: `SM022` for `@theme` in
`styles.css`, `SM023` for an unlayered rule in `theme.css`.

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
   - PyPI project name: `simple_module_{{PACKAGE_NAME}}`
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

The `Meta.requires_framework` field declares which `simple_module_core`
versions this module supports. Update the spec on each framework major
bump after verifying compatibility.

## Source layout

`core/` holds constants. With `--with-settings`, it also holds DB-backed
settings and the app-state container; otherwise these files and the
`register_settings` hook are omitted.
`web/` holds dependencies, the CRUD service and `endpoints/{api,views}.py`.
Keep models, contracts, pages and locales at the package root; reusable
frontend code belongs in `ui/{components,hooks,utils}/` when needed.
Area initializers contain only a docstring. Python tests mirror
`tests/<area>/<feature>/`, have no `__init__.py`, and use unique
`test_{{PACKAGE_NAME}}_*.py` basenames. Shared fixtures go in `tests/conftest.py`;
JS tests belong in `tests-js/`.
