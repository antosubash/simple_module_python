"""Keep the lifecycle reference complete as ModuleBase gains hooks."""

import inspect
import re
from pathlib import Path

from simple_module_core.module import ModuleBase


def test_every_public_registration_hook_is_documented():
    root = Path(__file__).resolve().parents[3]
    document = (root / "docs/framework/lifecycle.md").read_text(encoding="utf-8")
    hooks = {
        name
        for name, _ in inspect.getmembers(ModuleBase, predicate=inspect.isfunction)
        if name.startswith("register_")
    }
    documented = set(re.findall(r"\bregister_\w+\b", document))

    assert not (missing := hooks - documented), f"Undocumented lifecycle hooks: {sorted(missing)}"
