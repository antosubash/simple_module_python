# simple_module_cli

Standalone scaffolder for the [SimpleModule framework](https://github.com/antosubash/simple_module_python).

## Install

```bash
pip install simple_module_cli
# or, to keep the CLI in its own venv:
pipx install simple_module_cli
# or, to run it without installing:
uvx --from simple_module_cli@latest smpy new my-app
```

The standalone CLI depends on `typer`, `tomlkit`, `packaging`, and `PyYAML`. The Docker worker command uses PyYAML to validate Compose environment entries while preserving the original formatting.

## Usage

```bash
uv run smpy new my-app                       # interactive wizard
uv run smpy new my-app --yes --preset full   # all built-in modules + background jobs
uv run smpy create-module my_feature         # scaffold a publishable module package
uv run smpy create-host bare-host            # scaffold a bare host (no opinionated wiring)
```

Built-in commands: `uv run smpy new`, `uv run smpy create-host`, `uv run smpy create-module`, `uv run smpy update`, and `uv run smpy skills {list,add,update}`.

`uv run smpy update` handles PyPI and git pins, syncs lockfiles and generates the
frontend. `package-update` remains a deprecated alias until 0.0.50. Creating a
module inside an app workspace also wires and installs it; then use
`uv run smpy migrations new <module> -m "init"`, review, `make migrate` and restart.

When other framework packages are installed, they contribute additional subcommands via the `simple_module_cli.cli_plugins` entry-point group:

| Package | Commands |
|---|---|
| `simple_module_hosting` | `uv run smpy host gen-pages`, `uv run smpy host sync-js-deps` |
| `simple_module_users`   | `uv run smpy users create-admin` |
| `simple_module_settings` | `uv run smpy settings import-from-env` |

## License

MIT — see [LICENSE](LICENSE).
