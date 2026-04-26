# simple-module-cli

Standalone scaffolder for the [SimpleModule framework](https://github.com/antosubash/simple_module_python).

```bash
pip install simple-module-cli   # or: pipx install simple-module-cli
sm new my-app                   # interactive wizard
sm new my-app --yes --preset full
```

Provides three built-in commands: `sm new`, `sm create-host`, `sm create-module`.

When other framework packages are installed, they contribute additional subcommands via the `simple_module_cli.cli_plugins` entry-point group:

| Package | Commands |
|---|---|
| `simple_module_hosting` | `sm host gen-pages`, `sm host sync-js-deps` |
| `simple_module_users`   | `sm users create-admin` |
| `simple_module_settings` | `sm settings import-from-env` |

## License

MIT — see [LICENSE](LICENSE).
