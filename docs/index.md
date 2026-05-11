---
layout: home

hero:
  name: simple_module_python
  text: A modular monolith for Python
  tagline: FastAPI + SQLModel + Inertia.js + React. Plugin modules that compose at boot. No microservice tax, no API-client glue.
  actions:
    - theme: brand
      text: Get started
      link: /guide/quickstart
    - theme: alt
      text: Why a modular monolith?
      link: /guide/introduction
    - theme: alt
      text: View on GitHub
      link: https://github.com/antosubash/simple_module_python

features:
  - title: Build with it
    details: Five-minute quickstart, then scaffold your first module. You'll learn the loop — add a model, generate a migration, write a service, mount a page.
    link: /guide/quickstart
    linkText: Quickstart
  - title: Author a module
    details: Read the framework conventions, then walk through a real module end-to-end. Models, contracts, service, endpoints, pages, tests, locales.
    link: /guide/first-module
    linkText: Build a module
  - title: Use a bundled module
    details: Eight first-party modules ship with the framework — auth, users, permissions, settings, file_storage, background_tasks, feature_flags, dashboard.
    link: /modules/
    linkText: Browse modules
  - title: Operate it in production
    details: Deployment, environment variables, diagnostics, release pipeline, performance + load testing.
    link: /reference/deployment
    linkText: Deploy
---

## How the docs are organised

<style>
.sm-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(260px, 1fr)); gap: 1rem; margin: 1rem 0 2rem; }
.sm-grid a.sm-card { display: block; padding: 1rem 1.25rem; border: 1px solid var(--vp-c-divider); border-radius: 12px; background: var(--vp-c-bg-soft); text-decoration: none !important; }
.sm-grid a.sm-card:hover { border-color: var(--vp-c-brand-1); }
.sm-grid a.sm-card h3 { margin: 0 0 .25rem; font-size: 1rem; color: var(--vp-c-brand-1); }
.sm-grid a.sm-card p { margin: 0; color: var(--vp-c-text-2); font-size: .9rem; line-height: 1.4; }
@media (prefers-reduced-motion: no-preference) {
  .sm-grid a.sm-card { transition: border-color .15s ease, transform .15s ease; }
  .sm-grid a.sm-card:hover { transform: translateY(-1px); }
}
</style>

<div class="sm-grid">
  <a class="sm-card" href="/guide/introduction"><h3>Guide</h3><p>Install, bootstrap, and build your first module.</p></a>
  <a class="sm-card" href="/framework/overview"><h3>Framework</h3><p>Discovery, lifecycle hooks, middleware, permissions, events, i18n.</p></a>
  <a class="sm-card" href="/database/models"><h3>Database</h3><p>SQLModel conventions, per-module Base, mixins, sessions, Alembic.</p></a>
  <a class="sm-card" href="/frontend/inertia"><h3>Frontend</h3><p>Inertia page keys, shared props, page discovery, React layout.</p></a>
  <a class="sm-card" href="/testing/overview"><h3>Testing</h3><p>The fixtures in <code>conftest.py</code>, unit tests, end-to-end tests.</p></a>
  <a class="sm-card" href="/modules/"><h3>Modules</h3><p>Reference for each bundled module: routes, contracts, settings.</p></a>
  <a class="sm-card" href="/reference/make-commands"><h3>Reference</h3><p>CLI commands, env vars, diagnostic codes, deployment.</p></a>
</div>

## Try it in 60 seconds

```bash
uv tool install simple_module_cli
smpy new myapp --yes
cd myapp
make dev          # API on :8000, Vite on :5050
```

Then in another terminal, inside `myapp`:

```bash
smpy create-module orders --dest modules/orders
uv add ./modules/orders
```

That generates `modules/orders/` with a `ModuleMeta`, a SQLModel table, contracts, a service, REST + Inertia endpoints, three React pages, locales, and a smoke test — all wired in once the dev server reloads. The full walkthrough is in [Your first module](/guide/first-module).

## Where to start

- New here? Read [Introduction](/guide/introduction) for the why, then [Quickstart](/guide/quickstart) for the how.
- Already convinced? Jump straight to [Your first module](/guide/first-module).
- Need an off-the-shelf piece? See the [bundled modules](/modules/).
- Operating an existing deployment? Start with [Commands](/reference/make-commands) and [Environment variables](/reference/env-vars).

When conventions are ambiguous, the authoritative single-page docs ([Framework conventions](/framework-conventions), [Module authoring](/module-authoring), [E2E testing](/e2e-testing), [Release playbook](/release)) are the source of truth.
