# {{HOST_NAME}}

A SimpleModule application, scaffolded by `sm new`.

## Layout

```
{{HOST_NAME}}/
├── host/              # FastAPI host application (workspace member)
│   ├── main.py
│   ├── client_app/    # Inertia.js + React + Vite frontend
│   ├── alembic.ini
│   └── migrations/
└── modules/           # Your feature modules (each is a uv + npm workspace member)
    └── hello/         # Sample module — copy and rename to add your own.
```

## Quick start

```bash
# Install Python + JS deps (uv workspace + npm workspace)
make install

# Copy and customize env
cp .env.example .env

# Apply DB migrations
make migrate

# Run API + UI together
make dev
```

The API listens on http://localhost:8000 and Vite on http://localhost:5173.

## Adding a module

```bash
# Workspace mode — drops a new module under modules/<name>/
uv run sm create-module my-feature --dest modules/my-feature

# Wire it into the host
#   1) Add `simple_module_my_feature` to host/pyproject.toml dependencies
#   2) Add `simple_module_my_feature = { workspace = true }` to host's
#      [tool.uv.sources] (so uv resolves it from the workspace, not PyPI)
#   3) make install && make migration msg="add my-feature" && make migrate
```

## How the workspace fits together

- **uv workspace** (`pyproject.toml` here): members are `host` and every
  directory under `modules/*`. `uv sync --all-packages` installs them all
  in editable mode against the host's venv.
- **npm workspace** (`package.json` here): `host/client_app` and every
  module's frontend assets share one hoisted `node_modules`. Vite walks
  up from each `.tsx` file and finds React, Inertia, and shared UI
  packages without per-module aliasing.

## Falling back to a flat layout

If you only consume published modules (no in-repo authoring), regenerate
with `sm new <name> --flat` to skip the `modules/` tree entirely.
