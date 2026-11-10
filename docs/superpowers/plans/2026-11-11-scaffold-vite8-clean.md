# Plan: a fresh app's `make dev` runs clean (#900)

Design: `docs/superpowers/specs/2026-11-11-scaffold-vite8-clean-design.md`.

1. Move `validation-errors.test.ts` to `modules/settings/tests-js/`.
2. Add `scripts/check_wheel_contents.py` and its tests, and wire it into
   `make ci-build-packages`.
3. Port the template's `vite.config.ts` and `tsconfig.json` to Vite 8, and update the #152
   test.
4. Add `_APP_NPM_OVERRIDES` to the root `package.json` in both layouts, with tests.
5. Add a CHANGELOG entry, then run the real checks in a scaffolded app.
