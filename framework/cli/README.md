# simple_module_cli

Standalone scaffolder for the [SimpleModule framework](https://github.com/antosubash/simple_module_python).

## Install

```bash
pip install simple_module_cli
# or, to keep the CLI in its own venv:
pipx install simple_module_cli
# or, to run it without installing:
uvx --from simple_module_cli smpy new my-app
```

The package depends only on `typer` and `tomlkit` — installing it does **not** pull in FastAPI, SQLModel, or any other framework runtime.

## Usage

```bash
smpy new my-app                       # interactive wizard
smpy new my-app --yes --preset full   # all built-in modules + background jobs
smpy create-module my_feature         # scaffold a publishable module package
smpy create-host bare-host            # scaffold a bare host (no opinionated wiring)
```

Built-in commands: `smpy new`, `smpy create-host`, `smpy create-module`, `smpy package-update`, and `smpy skills {list,add,update}`.

When other framework packages are installed, they contribute additional subcommands via the `simple_module_cli.cli_plugins` entry-point group:

| Package | Commands |
|---|---|
| `simple_module_hosting` | `smpy host gen-pages`, `smpy host sync-js-deps` |
| `simple_module_users`   | `smpy users create-admin` |
| `simple_module_settings` | `smpy settings import-from-env` |

## License

MIT — see [LICENSE](LICENSE).
