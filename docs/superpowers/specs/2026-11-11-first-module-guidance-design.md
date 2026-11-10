# First-module guidance agrees with itself (#898)

## Scope

- **Wiring.** The guides said `uv add ./modules/orders`. In a `smpy new` workspace that runs
  against the workspace root, which is `package = false`, not against the host.
  `smpy create-module` prints `smpy add ../modules/orders --path host`, which writes a
  `{ workspace = true }` source into `host/pyproject.toml`; this was verified in a fresh
  workspace app. Every guide now uses that command, with `smpy add ./modules/orders` for a
  `--flat` app, also verified. The steps now also include the migration that follows.
- **Landing page template.**
  - Drop "Create an admin": `/setup` creates the first administrator, and `/` redirects
    to `/setup` until it does.
  - List create-module, then wire, then migrate.
  - "Read the docs" goes to `https://docs.py.simplemodule.dev/guide/first-module` (live,
    200).
- **DTO validation.** Verified on SQLModel 0.0.48: `Field(regex=...)` is accepted and
  ignored on a non-table model, and `Field(pattern=...)` raises `TypeError`. The
  first-module guide gets a tested `field_validator` example, and the conventions skill
  gets the rule. `tenants.contracts.TenantCreate` already works around it this way.

Out of scope: the quickstart's stale list of what `create-module` generates.

## Testing

- `test_landing_page_next_steps_match_the_first_module_guide`: fails on `main`, passes now.
- Biome check on the template.
- The DTO example was run: `"pending"` is accepted, `"Bad Value"` is rejected.
