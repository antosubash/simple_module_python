# simple_module_python skills

Agent skills for working in a [simple_module_python](https://github.com/antosubash/simple_module_python) codebase. Compatible with Claude Code, Codex, Cursor, Windsurf, OpenCode, and any other agent that supports the [Agent Skills format](https://agentskills.io/specification).

## Install

There are two install paths — pick whichever fits your project.

### Option A — `smpy skills` (recommended for `simple_module_cli` users)

Every project produced by `smpy new` already depends on `simple_module_cli`, which ships these skills inside its wheel. From the project root:

```bash
smpy skills list                                          # see what's available
smpy skills add                                           # install ALL skills into ./.claude/skills/
smpy skills add simple-module-creating                    # install just one
smpy skills add -g                                        # install into ~/.claude/skills (machine-wide)
smpy skills add --dest agents/skills                      # custom target dir
smpy skills add --symlink                                 # symlink to the bundled source (good for skill devs)
smpy skills update                                        # re-pull updates for skills already installed
smpy skills update simple-module-doctor                   # explicit re-pull (force-overwrites)
```

`smpy skills` resolves the bundled set against whatever version of `simple_module_cli` is installed, so upgrading the CLI ships skill updates the next time you run `smpy skills update`.

### Option B — `npx skills` (no Python install needed)

```bash
npx skills add antosubash/simple_module_python          # all skills, current project
npx skills add antosubash/simple_module_python -g       # globally
npx skills add antosubash/simple_module_python --skill simple-module-creating -a claude-code
npx skills add antosubash/simple_module_python --list
```

The CLI is [vercel-labs/skills](https://github.com/vercel-labs/skills); see its README for symlink-vs-copy and other options.

## What's here

| Skill | Use when |
|---|---|
| [simple-module-cli](./simple-module-cli/SKILL.md) | Invoking the `smpy` CLI — `smpy new`, `smpy create-host`, `smpy create-module`, `smpy host gen-pages`, `smpy users create-admin`, etc. |
| [simple-module-creating](./simple-module-creating/SKILL.md) | Adding a new feature package — scaffolding, entry-point, `ModuleMeta` |
| [simple-module-conventions](./simple-module-conventions/SKILL.md) | Writing or reviewing module code — the invariant list (SQLModel everywhere, settings layout, framework→plugin direction, etc.) |
| [simple-module-database](./simple-module-database/SKILL.md) | Adding SQLModel tables, picking a mixin, or debugging session/transaction behavior |
| [simple-module-migrations](./simple-module-migrations/SKILL.md) | Generating, applying, or reviewing Alembic migrations after installing or changing a module |
| [simple-module-inertia-pages](./simple-module-inertia-pages/SKILL.md) | Adding or debugging an Inertia page in a module — render keys, shared props, common pitfalls |
| [simple-module-locales](./simple-module-locales/SKILL.md) | Adding or debugging i18n in a module — `locale_dirs()`, namespaces, CLDR plurals, the Zod-in-hook rule |
| [simple-module-registries](./simple-module-registries/SKILL.md) | Contributing menu items, permissions, feature flags, or events from a module |
| [simple-module-testing](./simple-module-testing/SKILL.md) | Writing pytest tests — picking the right fixture (`db_session` / `app` / `authenticated_client`), single-test runs, e2e |
| [simple-module-doctor](./simple-module-doctor/SKILL.md) | Interpreting a diagnostic code (`SM001`–`SM021`) printed at boot |

The skills are designed to stand alone — install them into any host or module-package project and they'll work without needing access to the framework's source repo.

## Contributing

Each skill is a directory containing a `SKILL.md` with YAML frontmatter (`name`, `description`). The description is "use when…" triggers only — never a workflow summary, because agents will follow the description in lieu of reading the body.

PRs welcome.
