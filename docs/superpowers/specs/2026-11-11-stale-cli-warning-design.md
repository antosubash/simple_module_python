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
    `0.0.0` editable placeholder (`pins.PLACEHOLDER_VERSION`), for a running version that
    is a pre-release, dev or local build (not what PyPI ships), and on any exception:
    offline, timeouts, bad JSON or an unexpected payload shape. The 3-second fetcher is
    `partial(pypi.default_fetcher, timeout=3)`.
  - `warn_if_outdated` prints a warning to stderr that names `uv tool upgrade
    simple_module_cli` (or `pipx upgrade`) and `uvx --from simple_module_cli@latest`. It never blocks the
    scaffold.
- `smpy new` calls it right after validating the name.
- `framework/cli/tests/conftest.py` gets an autouse fixture that makes the fetcher raise,
  so no CLI test touches the network.
- Docs:
  - `README.md`, `framework/cli/README.md`, `framework/hosting/README.md` and the host
    landing page copy command (`Landing.tsx`) use `@latest`;
  - the installation and quickstart guides, `docs/index.md` and
    `docs/reference/make-commands.md` say how to upgrade.

Rejected: an env var to opt out. The check is quiet whenever it can't run, and repo rules
discourage new env-var configuration.

## Testing

- Unit tests:
  - a newer version is reported;
  - the same version, a newer local one, the placeholder, and a pre-release, dev or local
    running version are not;
  - every failure type is skipped.
- CLI tests: `smpy new` warns and still scaffolds, and is silent when PyPI is unreachable.
- Against the real PyPI: `0.0.36` reports 0.0.44, and `0.0.44` reports nothing (0.16 s).
