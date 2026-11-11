# Shipped skills link to files the wheel contains (#875)

`skills/` is installed as `simple_module_cli/skills/` (a symlink in the repo). Two skills
linked `../../docs/module-layout.md`, which points outside the installed package.

## Decisions

- Link the docs site, `https://docs.py.simplemodule.dev/module-layout` (returns 200),
  instead of shipping `docs/` in the wheel. The site follows `main` and needs no new
  packaging. A GitHub link at a tag would need a version stamp.
- Add `framework/cli/tests/test_cli_skill_links.py`: every relative link in a shipped
  `SKILL.md` must resolve inside `skills/` and exist. It fails on `main` and passes now.
- Add a "Downstream modules" section to `docs/module-layout.md`: copy
  `host/tests/test_module_layout.py`, point `MODULES` at the app's modules, and set your
  own `DOMAIN_AREAS`. The issue asked for this.
