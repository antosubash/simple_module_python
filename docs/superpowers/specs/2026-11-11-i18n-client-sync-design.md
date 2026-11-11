# Scaffolded apps send `X-SM-I18n` (#871)

#788 made the server choose whether to send the i18n catalog per tab, from the
`X-SM-I18n: <locale>:<audience>` header. Only this repo's `host/client_app/i18n.ts` sent
it. The scaffold's `app.tsx` had its own `router.on('success')` handler with no header,
so `smpy new` apps fell back to the per-session markers.

## Design

- Move the logic into `packages/i18n/src/inertia.ts`, exported as
  `@simple-module-py/i18n/inertia` (a subpath export, so the main entry stays
  framework-agnostic). It exports `bootI18nFromInitialPage(i18n)` and
  `subscribeI18nToNavigation(router)`.
- The router is a parameter with a structural `I18nRouter` type, so the package does
  not depend on `@inertiajs/react`.
- This repo's `host/client_app/app.tsx` and the scaffold template call it.
  `host/client_app/i18n.ts` and its test are removed, and the test moves to
  `packages/i18n/src/inertia.test.ts` with a fake router.
- Published apps pin `@simple-module-py/i18n` to the CLI version, which ships in
  lockstep, so the subpath exists wherever the new template does.

## Verification

- The package tests (`vitest`), `make ci-js-typecheck` and Biome pass.
- In a scaffolded app with the new template and package: `tsc` passes. In the browser,
  clicking a sidebar link sends `x-sm-i18n: en:full`, and the response carries
  `"messages": null`, so the tab keeps the catalog it holds.
