# simple_module_{{PACKAGE_NAME}}

The {{MODULE_NAME}} module for
[simple_module](https://github.com/antosubash/simple_module_python) apps.

Replace this paragraph with a description of what the module actually does —
the problem it solves and the surface it exposes to a host application.

## Install

```bash
pip install simple_module_{{PACKAGE_NAME}}
```

Add `simple_module_{{PACKAGE_NAME}}` to your host's dependencies; the
`[project.entry-points.simple_module]` entry point is discovered automatically
at boot, so no further wiring is required.

## Usage

| Route | Page | Permission |
|---|---|---|
| `GET /{{MODULE_SLUG}}/` | `{{MODULE_NAME}}/Browse` | `{{PACKAGE_NAME}}.view` |
| `GET /{{MODULE_SLUG}}/create` | `{{MODULE_NAME}}/Create` | `{{PACKAGE_NAME}}.create` |
| `GET /{{MODULE_SLUG}}/{id}/edit` | `{{MODULE_NAME}}/Edit` | `{{PACKAGE_NAME}}.edit` |
| `/api/{{MODULE_SLUG}}/` | — | JSON CRUD, gated per verb |

Document the real routes, settings and any events the module emits here.

## Configuration

Settings are a `DbBackedSettings` subclass (`{{PACKAGE_NAME}}/settings.py`) read
from the settings table and exposed on `app.state.{{PACKAGE_NAME}}`; nothing is
read from environment variables.
