# Warn when `smpy new` runs from an outdated CLI (#899)

## Problem

A new app pins every `simple_module_*` package to the running CLI's own version
(`pins.resolve_framework_version`). `uvx --from simple_module_cli` reuses a tool that was
installed earlier with `uv tool install`, and `--refresh` doesn't change that. So an old
tool scaffolds an old app, and nothing says so.

## Design

- `simple_module_cli/_version_check.py`:
  - `newer_release(current)` reuses `pypi.fetch_latest` with its own 3-second fetcher. It
    returns the newer stable version, or `None`. It also returns `None` for the
    `0.0.0` editable placeholder and on any `OSError`/`ValueError`: offline, timeouts,
    bad JSON.
  - `warn_if_outdated` prints a warning to stderr that names `uv tool upgrade
    simple_module_cli` and `uvx --from simple_module_cli@latest`. It never blocks the
    scaffold.
- `smpy new` calls it right after validating the name.
- `framework/cli/tests/conftest.py` gets an autouse fixture that makes the fetcher raise,
  so no CLI test touches the network.
- Docs:
  - `README.md` and `framework/cli/README.md` use `@latest`;
  - the installation and quickstart guides say how to upgrade.

Rejected: an env var to opt out. The check is quiet whenever it can't run, and repo rules
discourage new env-var configuration.

## Testing

- Unit tests:
  - a newer version is reported;
  - the same version, a newer local one and the placeholder are not;
  - every failure type is skipped.
- CLI tests: `smpy new` warns and still scaffolds, and is silent when PyPI is unreachable.
- Against the real PyPI: `0.0.36` reports 0.0.44, and `0.0.44` reports nothing (0.16 s).
