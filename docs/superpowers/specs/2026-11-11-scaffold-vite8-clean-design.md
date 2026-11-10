# A fresh app's `make dev` runs clean (#900)

## Goal and scope

A new `smpy new` app should print no Vite errors or warnings on `make dev`, and should
have no `npm audit` findings. Each problem below was reproduced on `main` in a scaffolded
app running Vite 8.3.7.

| Symptom | Cause | Fix |
|---|---|---|
| "Failed to run dependency scan … vitest" | the `simple_module_settings` wheel ships `ui/components/validation-errors.test.ts`; Vite's dep scan walks installed module packages | move the test to `modules/settings/tests-js/`, where Vitest's `include` actually collects it (it was never run before); `make ci-build-packages` runs `scripts/check_wheel_contents.py`, which fails on any JS or TS `*.test.*` or `*.spec.*` file (by basename, so `openapi.spec.json` passes), a `test-dom.tsx`, or a member under a `page-tests/` directory |
| native config loader warning: `__dirname`, extensionless `./module-assets` and `./vite.dev-url` | the template predates Vite 8 | use `import.meta.dirname` and `.ts` extensions, and set `allowImportingTsExtensions: true` in the template tsconfig; this is legal because the tsconfig has `noEmit`, and this repo's host does the same |
| `optimizeDeps.esbuildOptions` is deprecated | Vite 8 scans with Rolldown | `optimizeDeps.rolldownOptions.resolve.modules`, which this repo's host already uses for the #152 fallback |
| 3 moderate `npm audit` findings | `@tailwindcss/typography@0.5.20`, the latest release, pins `postcss-selector-parser@6.0.10` | the root `package.json` of new apps, in both layouts, overrides it to `^6.1.5`, as this repo's root does |

## Decisions made

- The wheel check runs on built wheels, in the `ci-build-packages` CI job, rather than as a
  source-tree rule. It checks what actually ships, including future hatch config mistakes.
- The override value comes from one constant, `_APP_NPM_OVERRIDES`. A test keeps it equal
  to this repo's own override.
- Existing apps are left alone; the CHANGELOG says what to copy.

## Testing

- `scripts/tests/test_check_wheel_contents.py`.
- `framework/cli/tests/test_cli_scaffold_vite8.py` covers the template config, the
  overrides in both layouts, and their parity with this repo's override.
- The existing #152 test now asserts `rolldownOptions`.
- Real checks:
  - `make ci-build-packages`: 23 clean wheels; `main`'s settings wheel fails the check;
  - in a scaffolded app with the new template: Vite dev starts with no warnings (and no
    scan error once the test file is gone), `vite build` and `tsc` pass, and a fresh
    `npm install` gives `npm audit`: 0 vulnerabilities.
