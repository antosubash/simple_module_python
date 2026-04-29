# Documentation site

This is a [VitePress](https://vitepress.dev) site — markdown files under `docs/`, rendered by a Vite-powered dev server.

## Run locally

```bash
cd docs
npm install
npm run dev
```

Open `http://localhost:5173`. Hot-reloads on any `.md` edit.

## Build

```bash
cd docs
npm run build       # output in docs/.vitepress/dist
npm run preview     # serve the built site
```

## Structure

```text
docs/
├── .vitepress/
│   └── config.ts         # nav, sidebar, theme
├── index.md              # home page
├── guide/                # getting-started
├── framework/            # module system deep dives
├── database/             # SQLModel, mixins, migrations
├── frontend/             # Inertia, pages, shared props
├── testing/              # fixtures, unit + E2E
├── reference/            # commands, env vars, diagnostic codes, deployment
├── plans/                # dated design docs (pre-existing)
├── superpowers/          # spec/plan pairs (pre-existing)
├── release-notes/        # per-release notes (pre-existing)
├── framework-conventions.md   # authoritative reference (pre-existing)
├── module-authoring.md        # authoritative reference (pre-existing)
├── e2e-testing.md             # authoritative reference (pre-existing)
└── release.md                 # authoritative reference (pre-existing)
```

The four pre-existing root-level `.md` files are **authoritative** when conventions are ambiguous. The themed sub-directories are the narrative onboarding path; they link back to the authoritative docs where appropriate.

## Adding a page

1. Create `docs/<section>/<slug>.md`.
2. Add it to the sidebar in `docs/.vitepress/config.ts`.
3. `npm run dev` to preview.

## Publishing

Not yet wired into CI. The `docs:build` output can be served by any static host; the repo's release workflow is scoped to Python + npm packages, not docs.
