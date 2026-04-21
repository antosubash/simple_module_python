# simple-module-hosting

FastAPI + Inertia.js host runtime for the [simple_module](https://github.com/antosubash/simple_module_python) framework — builds the app, wires the middleware pipeline, exposes the `sm` / `simple-module` CLI, and ships the project scaffolder.

## Install

```bash
pip install simple-module-hosting
```

For a new project, most users run the generator instead:

```bash
uvx simple-module new my-app
```

## What it provides

- `create_app(settings)` — returns a fully-wired `FastAPI` instance with all discovered modules registered.
- Middleware pipeline (execution order): CorrelationId → RequestLogging → SecurityHeaders → Session → `<module middleware>` → Tenant (opt-in) → Locale → InertiaLayoutData → app.
- Inertia wiring — shared props (`auth`, `menus`, `i18n`), `InertiaDep`, page-route lookup.
- CLI entry points: both `sm` and `simple-module` are installed and alias the same Click tree.
- Scaffolders — `sm create-host`, `sm create-module`, `sm new` (greenfield app with users + dashboard + permissions pre-wired), `sm gen-pages`.

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

CLI:

```bash
simple-module new my-app        # scaffold a new project
simple-module doctor            # diagnostic codes (SM001-SM017)
simple-module gen-pages         # regenerate client_app/modules.generated.ts
```

`sm` works identically to `simple-module`.

## Depends on

- `simple-module-core`, `simple-module-db`
- `fastapi`, `fastapi-inertia`, `starlette`, `uvicorn`, `click`, `jinja2`, `httpx`

## License

MIT — see [LICENSE](https://github.com/antosubash/simple_module_python/blob/main/LICENSE).
