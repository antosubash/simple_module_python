# Plan: scaffolded module pages use AuthenticatedLayout (#897)

Design: `docs/superpowers/specs/2026-11-10-scaffold-page-layout-design.md`.

1. **Test first:** add `TestPageLayout` to `framework/cli/tests/test_scaffolding_module_js.py`,
   checking both variants and all three pages.
2. **Templates:** add the `AuthenticatedLayout` import, in sorted position, and the
   `.layout` assignment to the six `pages/*.tsx.tpl` files.
3. **Check:**
   - run `biome check` on the rendered pages of both variants;
   - in a real app, `create-module`, then the module's `npm run typecheck`;
   - start `make dev` and open `/<module>/` in a browser: the sidebar must show.
4. **Docs:** add a CHANGELOG Fixed entry with the fix for existing modules.
