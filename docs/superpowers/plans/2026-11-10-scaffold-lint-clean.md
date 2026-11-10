# Plan: a fresh app passes its own `make lint` (#896)

Design: `docs/superpowers/specs/2026-11-10-scaffold-lint-clean-design.md`.

1. **ty pin** (independent). Test first: `TY_REQUIREMENT` admits the ty version in
   `uv.lock`, and both the workspace root template and `_APP_PY_DEV_DEPS` use it. Add
   `TY_REQUIREMENT` to `scaffolding.py`, a `{{TY_REQUIREMENT}}` placeholder in
   `templates/workspace/pyproject.toml.tpl`, and use it in `_app_project_manifests.py`.
2. **ty ignore comment** (independent). Test first: `create_module` renders no ignore
   comment by default and `# ty: ignore[invalid-assignment]` with `framework_repo=True`.
   Add the `{{MODEL_CONFIG_TY_IGNORE}}` placeholder in `contracts/schemas.py.tpl`.
3. **Sorted constants import** (independent). Test first: `create_module("bookmarks")`
   and `create_module("zebra")` produce a `module.py` that passes `ruff check --select I`.
   Add the `{{CONSTANTS_IMPORTS}}` placeholder in `module.py.tpl`, rendered by
   `sorted(..., key=str.lower)`.
4. **Alembic write hook**. Test first: a plain `alembic revision` in a `--no-install`
   scaffold passes `ruff format --check` and `ruff check --select I,W`. Add
   `[post_write_hooks]` to `templates/host/alembic.ini` and `host/alembic.ini`.
5. **End-to-end and docs**.
   - Extend the "passes its own ruff" test with `create-module bookmarks`/`zebra`.
   - Update `docs/database/migrations.md` and add a CHANGELOG Fixed entry.
   - Real `smpy new` + `create-module` + `make migration` + `make lint`.
   - `make new-module` sanity check.

Done check for every task: its targeted tests pass, `ruff`, and `ty` pass.
