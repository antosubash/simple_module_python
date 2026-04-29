# simple_module_python skills

Agent skills for working in a [simple_module_python](https://github.com/antosubash/simple_module_python) codebase. Compatible with Claude Code, Codex, Cursor, Windsurf, OpenCode, and any other agent that supports the [Agent Skills format](https://agentskills.io/specification).

## Install

Pick your scope and run one command:

```bash
# All skills in this repo, into the current project
npx skills add antosubash/simple_module_python

# Globally (available in every project on your machine)
npx skills add antosubash/simple_module_python -g

# Just one skill, into a specific agent
npx skills add antosubash/simple_module_python --skill simple-module-creating -a claude-code

# List what's available without installing
npx skills add antosubash/simple_module_python --list
```

The CLI is [vercel-labs/skills](https://github.com/vercel-labs/skills); see its README for symlink-vs-copy and other options.

## What's here

| Skill | Use when |
|---|---|
| [simple-module-cli](./simple-module-cli/SKILL.md) | Invoking the `sm` CLI — `sm new`, `sm create-host`, `sm create-module`, `sm host gen-pages`, `sm users create-admin`, etc. |
| [simple-module-creating](./simple-module-creating/SKILL.md) | Adding a new feature package — scaffolding, entry-point, `ModuleMeta` |
| [simple-module-conventions](./simple-module-conventions/SKILL.md) | Writing or reviewing module code — the invariant list (SQLModel everywhere, settings layout, framework→plugin direction, etc.) |
| [simple-module-database](./simple-module-database/SKILL.md) | Adding SQLModel tables, picking a mixin, or debugging session/transaction behavior |
| [simple-module-migrations](./simple-module-migrations/SKILL.md) | Generating, applying, or reviewing Alembic migrations after installing or changing a module |
| [simple-module-inertia-pages](./simple-module-inertia-pages/SKILL.md) | Adding or debugging an Inertia page in a module — render keys, shared props, common pitfalls |
| [simple-module-doctor](./simple-module-doctor/SKILL.md) | Interpreting a diagnostic code (`SM001`–`SM018`) printed at boot |

The skills are designed to stand alone — install them into any host or module-package project and they'll work without needing access to the framework's source repo.

## Contributing

Each skill is a directory containing a `SKILL.md` with YAML frontmatter (`name`, `description`). The description is "use when…" triggers only — never a workflow summary, because agents will follow the description in lieu of reading the body.

PRs welcome.
