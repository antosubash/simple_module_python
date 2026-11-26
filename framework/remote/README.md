# simple_module_remote

Client-only engine for a per-project command line over a simple_module app's
REST API. It reads the app's OpenAPI schema, generates one command per
operation, and handles environments, credentials, HTTP and output formatting.
It never imports the server framework: it talks to a running app over HTTP only.

## What it provides

- Named environments (`url`, optional `tenant`, `protected`) stored in a
  per-CLI user config file, merged over an optional defaults file shipped with
  the project.
- Environment selection by flag, `<CLI>_ENV` or the saved current environment.
- Request safety rules: only `/api/` paths, no credentials in URLs, plain
  `http://` refused except for loopback hosts.

## Install

```bash
uv add simple_module_remote
```

## Usage

The package is an engine, not a command. A project wraps it in its own CLI
entry point, naming the CLI so that config lives in `~/.config/<cli>/` and
environment variables use the `<CLI>_` prefix.

```python
from simple_module_remote.config.environments import load_config, select_env

config = load_config("my-app", defaults_path=None)
env, explicit = select_env(config, flag=None, environ={}, cli="my-app")
print(env.origin)
```
