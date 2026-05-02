---
layout: home

hero:
  name: simple_module_python
  text: Modular-monolith for Python
  tagline: FastAPI + SQLModel + Inertia.js + React — plugin modules that compose at boot. No microservice tax, no API-client glue.
  actions:
    - theme: brand
      text: Get started
      link: /guide/introduction
    - theme: alt
      text: Quickstart
      link: /guide/quickstart
    - theme: alt
      text: View on GitHub
      link: https://github.com/antosubash/simple_module_python

features:
  - title: One app, many modules
    details: Each module ships its own SQLModel tables, API endpoints, and React pages — but everything runs in one FastAPI process. Installed as Python packages, discovered via entry points.
  - title: SQLModel end-to-end
    details: A single type system for tables and DTOs. Per-module Base class gives you a Postgres schema (or table-name prefix on SQLite) with zero boilerplate.
  - title: Inertia.js, not a split SPA
    details: Server renders React pages with shared props (auth, menus, i18n) — no REST glue. Auto-discovered .tsx pages under modules/, hot-reloaded by Vite.
  - title: Diagnostics that fail boot
    details: Orphan pages, phantom renders, coupling violations, migration drift, locale inconsistencies — caught at dev time, enforced at production boot.
  - title: Batteries-included
    details: Permissions, roles, audit/soft-delete/multi-tenant mixins, event bus, i18n with CLDR plurals, feature flags, health checks — standard plumbing you don't have to rebuild.
  - title: Scaffold in one command
    details: make new-module name=orders generates the full package — ModuleMeta, models, service, endpoints, pages, tests — already wired into the app.
---

## What you'll find here

This documentation is structured around what you're trying to do:

- **[Guide](/guide/introduction)** — install, bootstrap, and build your first module.
- **[Framework](/framework/overview)** — the module system: discovery, lifecycle hooks, middleware, permissions, events, i18n.
- **[Database](/database/models)** — SQLModel conventions, per-module `Base`, mixins, session lifecycle, Alembic migrations.
- **[Frontend](/frontend/inertia)** — Inertia page keys, shared props, page discovery, client dependencies.
- **[Testing](/testing/overview)** — the fixtures in `conftest.py`, how to write unit tests against a real DB, and how to run E2E.
- **[Reference](/reference/make-commands)** — `make` targets, environment variables, diagnostic codes, deployment.

The authoritative single-page docs (`framework-conventions.md`, `module-authoring.md`, `e2e-testing.md`, `release.md`) are also linked from each section's sidebar — they are the source of truth when conventions are ambiguous.
