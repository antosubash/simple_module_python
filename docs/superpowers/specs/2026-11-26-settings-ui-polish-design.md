# Module settings editor: readable labels, translations, mobile layout

Status: approved (2026-11-26)

## Goal & scope

The module settings editor (`/settings/modules`, `ModulesEdit.tsx` + `ModuleForm` +
`ModuleFieldRow` + `FieldSource`) shows raw Python identifiers everywhere:
`smtp_tls_mode` as a label, `file_storage settings` as the heading, the
module package in mono as the nav entry, and `SM_FILE_STORAGE_QUOTA_BYTES` in
the trailing column of every row, which for `DbBackedSettings` modules is a
label nobody reads. Descriptions come from English Python `Field(description=)`
strings, so nothing on the page is translated except the chrome.

In scope:

- Human, translated labels, help text, group headings and module titles for
  every field of every bundled module shown by the generic editor (~150 fields
  across 11 modules), in every locale each module ships (en, de, plus es where
  present).
- A fallback chain so third-party modules with no translations still look
  reasonable (no underscores).
- Visual rework of the editor: header, module navigation, row layout, source
  indicator, save bar, and a phone layout that is designed rather than merely
  not broken.
- A test that fails when a bundled module adds a settings field without a
  label, so the "all settings translated" property holds after this PR.

Out of scope: the free-form overrides pages (`Browse`/`Create`/`Edit`, raw keys
by design), modules with their own settings page (`manage_url`, e.g. branding:
they keep the "Managed on its own page" card), host `Settings` fields, and any
change to how values are stored or validated.

## Approach

**Convention-based locale keys, resolved on the client.** Each module's
`locales/<lang>.json` gets a `settings_form` section:

```json
"settings_form": {
  "title": "File storage",
  "description": "Where uploads are stored and the limits that apply to them.",
  "groups": { "s3": "Amazon S3 / compatible", "filesystem": "Local filesystem" },
  "fields": {
    "s3_bucket": { "label": "Bucket", "help": "Name of the bucket uploads go to." },
    "quota_bytes": { "label": "Storage quota (bytes)", "help": "…" }
  }
}
```

Keys: `<package>.settings_form.title|description`,
`<package>.settings_form.groups.<slug>` (slug = group text lowercased, non
alphanumerics → `_`), `<package>.settings_form.fields.<field>.label|help`.
All module catalogs are already loaded on admin pages, so a small helper in the
settings module (`ui/utils/field-text.ts`) looks them up with `i18n.exists`.

Fallback chain per string: locale key → pydantic `Field(title=…)` /
`description` sent by the server → humanised identifier (`smtp_tls_mode` →
"SMTP TLS mode", with a short acronym list: SMTP, TLS, URL, S3, ID, TTL, OIDC,
JWKS, DB, API, CORS, KB, MS, UPN). The page never prints a raw `snake_case`
identifier as a label.

Rejected:

- *Resolve labels on the server* with the Python translator and send `label`
  in the props: duplicates the locale lookup the client already does, needs a
  request locale threaded through `collect_module_settings`, and the REST API
  callers (CLI) want identifiers, not prose.
- *Put labels in Python* (`Field(title=…)` per field): English only, which is
  the problem being fixed. `title` is still honoured as a fallback for
  third-party modules.

## Design

### Server

`props.serialize` adds `title` (pydantic `FieldInfo.title`, else `null`) to
each field. Nothing else changes server-side; `description` stays as the
English fallback.

### Page layout

```
Desktop (lg+)                                   Phone (<lg)
┌──────────┬──────────────────────────────┐     ┌──────────────────────┐
│ 🔍 Search │ File storage                 │     │ Module settings      │
│          │ Where uploads are stored…    │     │ [ File storage    ▾ ]│  ← Select
│ ● File   │ ┌ Amazon S3 / compatible ──┐ │     │ File storage         │
│   storage│ │ Bucket          [______] │ │     │ Where uploads are…   │
│   12 ·2✎ │ │ Name of the…    Default  │ │     │ ┌ S3 ──────────────┐ │
│   Mail   │ ├──────────────────────────┤ │     │ │ Bucket           │ │
│   8      │ │ Region          [______] │ │     │ │ Name of the…     │ │
│   …      │ │                Overridden·Reset│ │ [______________] │ │
│          │ └──────────────────────────┘ │     │ │ Overridden·Reset │ │
│          │ [Test S3 connection]         │     │ └──────────────────┘ │
│          │                              │     │┌────────────────────┐│
│          │      (sticky) 2 unsaved [Save]│    ││ 2 unsaved   [Save] ││ ← sticky bottom
└──────────┴──────────────────────────────┘     └────────────────────────┘
```

- **Header**: translated module title (h2) + description; no `<code>package</code>`.
- **Navigation**: desktop keeps the left rail, but entries show the translated
  module title (package name drops off), with field count and an "overridden"
  dot. Search matches title, package, field labels and identifiers. Below `lg`
  the rail is replaced by a full-width `Select` (44px touch target) — today it
  is a 288px-tall scroll box that pushes the form off the first screen.
- **Groups**: one `Card` per group with a translated heading; ungrouped fields
  come first in a card without a heading. Rows inside a card are separated by
  `divide-y`.
- **Row**: two columns from the card's `@lg` container width (label + help on
  the left, ~2/5; control + source line under it on the right), stacked below.
  Booleans put the switch on the right of the label row at every width (the
  standard settings-list pattern) with help below the label. The raw identifier
  is not shown; it stays available as the `title` tooltip on the label and in
  the source popover.
- **Source line** (replaces the env-var column): a small badge —
  `Default`, `Overridden` (primary, with "Reset to default"), `Set by
  environment` (amber, env var name shown), or `Stored · environment wins`.
  "Default: <value>" shows only when the live value differs from it. The
  `SM_*` env var name is shown only for env-readable classes, where it means
  something.
- **Save bar**: the Save button + unsaved count + saved confirmation move into
  a bar that is sticky at the bottom of the viewport while the form is dirty
  (and on phones always), so a long form like `background_tasks` (33 fields)
  can be saved without scrolling back up. Ctrl/Cmd+S is not added.
- An edited, unsaved row gets a tinted background and an `Unsaved` badge; the
  save bar has a `Discard` button (restores the saved values) next to Save.
  On touch devices the Reset link is a 44px target.
- Mockup: https://claude.ai/artifact/SgorYnZJXaCs7m9e8sBcq5 (approved
  2026-11-26).
- Restart-required badge, secret input, JSON input, choices select, errors,
  revert focus handling, leave guard and discard dialog keep their behaviour.

### Translations

- `settings_form` sections for: api_tokens, audit_log, background_tasks,
  file_storage, keycloak, mail, oidc, site_lock, tenants, users (branding's
  fields are edited on its own page; it gets `title`/`description` only).
  Every locale file the module ships gets the same keys (SM014/SM015 parity).
- Settings-module chrome strings added/changed (source badges, select label,
  save bar) go to settings `en`/`de`. Strings that become unused are removed.
- `make gen-i18n` regenerates the key files.

### Guard test

`modules/settings/tests/...` boots the test app, collects module settings
views, and asserts that for every module without `manage_url`, every field
has `settings_form.fields.<name>.label` and every group has a
`settings_form.groups.<slug>` key in the module's `en.json`, and that the module
has `settings_form.title`. Locale parity is already enforced by the
untranslated/locale checks.

## Decisions made

- Section name `settings_form` (no bundled locale uses it today).
- Labels carry units where the value is a number of seconds/bytes/days
  ("Invitation lifetime (hours)") rather than adding input adornments.
- The Python `description` strings stay as they are (CLI and API still use
  them); the UI prefers the translated help.
- Phone module picker is a `Select`, not horizontal chips (11+ modules don't
  fit a chip row).
- German (and Spanish for modules that ship `es.json`) translations are written
  in this PR, not stubbed with English.
- No new diagnostic code; a doctor warning for untranslated settings fields in
  third-party modules becomes a follow-up issue.

## Testing

- Vitest: label fallback chain (key → title → description → humanised),
  humaniser acronyms, row renders translated label/help, source badge states,
  mobile Select switches module (and respects the dirty guard), sticky save bar
  appears when dirty. Existing ModuleForm/ModulesEdit/row tests updated where
  they query by raw field name.
- Pytest: `title` in serialized props; the guard test above.
- Browser: desktop and 390px screenshots of mail, file_storage, users and
  background_tasks (en and de), save/reset round trip, dark mode.

## Risks

- Volume: ~150 fields × (label + help) × 2–3 locales. Mitigated by doing it
  module by module with the guard test as the done check.
- `untranslated` lint may flag German strings identical to English (e.g. "URL",
  "S3"); use the checker's existing allowance or rephrase.
- Existing JS tests select rows by raw field name; they need updating, not
  just the components.
