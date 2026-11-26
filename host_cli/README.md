# smdev

The dev host's own command line, generated from its bundled OpenAPI schema by
`simple_module_remote`. In a checkout run `uv run smdev --help`; elsewhere install
it with `uv tool install ./host_cli` (and put `~/.local/bin` on `PATH`).
See `docs/guide/project-cli.md`.

Regenerate the schema after an API change with `make cli-schema`.
