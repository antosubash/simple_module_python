# A fresh app passes its own `make lint` (#896)

## Goal and scope

`smpy new bookshelf -y && make lint` must pass with no edits, and so must the app after
`smpy create-module <any name>` and after `make migration`. Reproduced on `main` with the
local CLI:

| Gate | Failure | Cause |
|---|---|---|
| `ruff format --check` | the initial-schema revision would be reformatted | Alembic writes single-quoted, unwrapped code |
| `ruff check` | 33 × E501, W291, I001 in that revision | same, plus `Revises: ` trailing space and the `${imports}` line in `script.py.mako` |
| `ruff check` after `create-module bookmarks` | I001 in `module.py` | the template lists `PERM_GROUP` before `PERM_<PKG>_*`, which is sorted only when the package name sorts after `group` (`hello` does, `bookmarks` does not) |
| `ty check` (any ty 0.0.90–0.0.100) | `unused-ignore-comment` on `model_config = ConfigDict(...)  # ty: ignore[invalid-assignment]` | the app's ty config turns `invalid-assignment` off, so the ignore never applies; the framework repo turns it on, which is why the template has it |
| `ty check` with ty 0.0.100 | `renamed-rule`: `unresolved-attribute` is now `missing-attribute` | the scaffold pins `ty>=0.0.29`, so a new app gets the newest ty |

Out of scope: #872 (`path_separator` in `alembic.ini`), the Vite warnings (#900), the
layout (#897), and bumping the framework repo's own ty.

## Approach

1. **Revisions: an Alembic `post_write_hooks` entry**, in the scaffold's `host/alembic.ini`
   and in this repo's `host/alembic.ini`. It runs `python -m ruff check --select I --fix`
   and then `python -m ruff format` on each new revision. Ruff picks up the project's own
   config from the file's location. Only the isort rules get `--fix`, so the hook never
   deletes the unused `sa`/`op` imports in an empty handwritten revision, which the
   author is about to fill in.
   - Rejected: excluding `host/migrations/versions/` from ruff. Every revision would pass,
     but hand-edited revisions would no longer be linted, and this repo lints its own.
2. **`module.py` constants import: sorted when rendered.** A new `{{CONSTANTS_IMPORTS}}`
   placeholder renders the names sorted the way ruff's isort sorts them (case-insensitive),
   so `PERM_GROUP` lands in the right place for every package name.
   - Rejected: renaming `PERM_GROUP`. Every module in this repo uses that name.
3. **ty:**
   - The ignore comment moves behind a `{{MODEL_CONFIG_TY_IGNORE}}` placeholder: empty for
     apps, `  # ty: ignore[invalid-assignment]` for `framework_repo=True`.
   - The scaffold pins ty to the tested range `ty>=0.0.90,<0.0.100`, from one
     `TY_REQUIREMENT` constant used by both the workspace root template and
     `_app_project_manifests`.
   - Rejected: renaming the rule to `missing-attribute`. Every ty before 0.0.100 would
     then warn about an unknown rule, the framework repo included (it is on 0.0.90).

## Decisions made

- The upper bound is the version that renamed the rule. 0.0.90, 0.0.97 and 0.0.99 were
  run against a fresh app and are clean once the ignore comment is gone. A test asserts
  that the ty in this repo's `uv.lock` satisfies `TY_REQUIREMENT`. A Dependabot bump past
  the range then fails that test, so the scaffold gets updated in the same PR.
- The hook uses Alembic's `module` runner (`sys.executable -m ruff`), so it runs the
  project venv's ruff. Both scaffold layouts have ruff in the default dev group. Without
  ruff, Alembic raises `Could not find module ruff` after the file is written; that is
  acceptable for a dev-only command.
- Existing apps are left alone. The CHANGELOG entry gives the `[post_write_hooks]`
  block to paste into their `host/alembic.ini`.
- `script.py.mako` itself is unchanged; the hook normalizes its output.

## Testing

- `test_cli_new_scaffold_layout.py`: the existing "passes its own ruff" test also runs
  `create-module` for `bookmarks` (sorts before `group`) and `zebra` (after) before
  running `ruff format --check` and `ruff check`.
- A plain `alembic revision` against a `--no-install` scaffold, run with the test
  interpreter, which has ruff: the revision passes `ruff format --check` and
  `ruff check --select I,W`.
- Unit tests:
  - the placeholder renders with and without `framework_repo`;
  - `TY_REQUIREMENT` admits the version in `uv.lock`;
  - both manifests use it.
- Real check in /vf: `smpy new` with install from the worktree CLI, then
  `create-module bookmarks`, `make migration`, and `make lint` (ruff and ty) pass.
  `make new-module` in this repo still passes `make lint`, and this repo's
  `make migration` output passes ruff.

## Risks

- `smpy new` bootstraps the first revision with `uv run --project host alembic`. If that
  environment lacks ruff, the hook raises after the revision is written, and the
  bootstrap fails. The real `smpy new` check covers this. The fallback is to bootstrap
  without hooks and format explicitly.
