"""Values that keep a scaffolded app passing its own ``make lint`` (GH #896)."""

from __future__ import annotations

# ty is pre-1.0 and renames rules between releases, so
# new apps get the range this repo is tested on, not the newest ty.
# ``test_scaffold_lint_tooling.py`` fails once ``uv.lock`` moves past it.
TY_REQUIREMENT = "ty>=0.0.104,<0.0.105"

# Apps turn ty's ``invalid-assignment`` off, so this ignore would be reported as
# unused there; only a module inside the framework repo, which checks the rule,
# gets it.
MODEL_CONFIG_TY_IGNORE = "  # ty: ignore[invalid-assignment]"
