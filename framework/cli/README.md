# simple_module_cli

Standalone scaffolder for the [SimpleModule framework](https://github.com/antosubash/simple_module_python).

## Install

```bash
pip install simple_module_cli
# or, to keep the CLI in its own venv:
pipx install simple_module_cli
# or, to run it without installing:
uvx --from simple_module_cli sm new my-app
```

The package depends only on `typer` and `tomlkit` — installing it does **not** pull in FastAPI, SQLModel, or any other framework runtime.

## Usage

```bash
sm new my-app                       # interactive wizard
sm new my-app --yes --preset full   # all built-in modules + background jobs
sm create-module my_feature         # scaffold a publishable module package
sm create-host bare-host            # scaffold a bare host (no opinionated wiring)
```

Built-in commands: `sm new`, `sm create-host`, `sm create-module`.

When other framework packages are installed, they contribute additional subcommands via the `simple_module_cli.cli_plugins` entry-point group:

| Package | Commands |
|---|---|
| `simple_module_hosting` | `sm host gen-pages`, `sm host sync-js-deps` |
| `simple_module_users`   | `sm users create-admin` |
| `simple_module_settings` | `sm settings import-from-env` |

## License

MIT — see [LICENSE](LICENSE).
