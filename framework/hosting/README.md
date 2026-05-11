# simple_module_hosting

FastAPI + Inertia.js host runtime for the [simple_module](https://github.com/antosubash/simple_module_python) framework — builds the app, wires the middleware pipeline, and contributes the `smpy host` plugin to the standalone `smpy` CLI.

## Install

```bash
pip install simple_module_hosting
```

For a new project, most users run the generator instead (shipped by the standalone `simple_module_cli` distribution):

```bash
uvx --from simple_module_cli smpy new my-app
```

## What it provides

- `create_app(settings)` — returns a fully-wired `FastAPI` instance with all discovered modules registered.
- Middleware pipeline (execution order): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → Locale → InertiaLayoutData → app.
- Inertia wiring — shared props (`auth`, `menus`, `i18n`), `InertiaDep`, page-route lookup.
- `smpy host` plugin — `smpy host gen-pages` regenerates the frontend pages manifest; `smpy host sync-js-deps` installs JS deps declared by installed modules. The `smpy` binary itself comes from `simple_module_cli`.

## Usage

Minimal `main.py`:

```python
from simple_module_hosting import create_app
from simple_module_hosting.settings import Settings

settings = Settings()           # reads SM_* env vars
app = create_app(settings)      # discovers + registers every installed module

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

CLI (after also installing `simple_module_cli`):

```bash
smpy host gen-pages             # regenerate client_app/modules.generated.ts
smpy host sync-js-deps          # sync module JS deps into client_app/node_modules
```

## Depends on

- `simple_module_core`, `simple_module_db`
- `fastapi`, `fastapi-inertia`, `starlette`, `uvicorn`, `click`, `jinja2`, `httpx`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
