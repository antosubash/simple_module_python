# Settings UI polish — implementation plan

Design: `docs/superpowers/specs/2026-11-26-settings-ui-polish-design.md`.

## T1 — Server prop + guard test (sequential, first)

- `modules/settings/settings/module_settings/{discovery,props}.py`: add `title`
  (pydantic `FieldInfo.title` or `None`) to the field view and the serialized prop.
- Test first: serialized props carry `title`.
- Guard test `modules/settings/tests/module_settings/fields/test_settings_field_translations.py`:
  for every bundled module whose `core/settings.py` defines a
  `DbBackedSettings` subclass, its `locales/en.json` has
  `settings_form.title`, and (unless the module has its own settings page)
  `settings_form.fields.<field>.label` for every field and
  `settings_form.groups.<slug>` for every group. Slug rule shared with the
  client: lower-case, runs of non-alphanumerics → `_`, trimmed.
- Done: the new test fails listing the missing keys (red until T2).

## T2 — Translations (independent of T3/T4; own worktree, then merged)

- Add `settings_form` sections to en/de(/es) for api_tokens, audit_log,
  background_tasks, file_storage, keycloak, mail, oidc, site_lock, tenants,
  users; branding gets `title`/`description` only.
- Done: T1 guard test green, `make gen-i18n` run and committed,
  `make ci-check-untranslated` (or the lint equivalent) and locale parity green.

## T3 — Client text helper (independent)

- `modules/settings/settings/ui/utils/field-text.ts`: `groupSlug`,
  `humanize`, `fieldLabel`, `fieldHelp`, `groupLabel`, `moduleTitle`,
  `moduleDescription` with the fallback chain key → title/description → humanised.
- Vitest first: `modules/settings/tests-js/field-text.test.ts`.

## T4 — Editor UI (after T3)

- `ModuleFieldRow` (two-column row, switch-right for bools, unsaved tint),
  `FieldSource` → source badge line, `ModuleForm` (cards per group, header with
  title/description, sticky save bar with Discard), `ModulesEdit` (translated
  nav, mobile `Select`), settings `en`/`de` chrome strings.
- Update existing JS tests that query raw field names; add tests for badges,
  mobile select, save bar, discard.
- Every file stays under 300 lines; split new components out
  (`SaveBar.tsx`, `ModuleNav.tsx`, `SourceBadge.tsx`).

## T5 — Integrate and verify

- `make gen`, `make lint`, `make test-js`, targeted pytest; browser check
  desktop + 390px, en + de, dark mode; screenshots for the PR.
