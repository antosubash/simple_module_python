"""The release preflight step must declare every third-party import it runs.

It runs with `uv run --no-project --with ...`, which layers those packages over
the runner's interpreter. A package the system Python happened to provide
(PyYAML on ubuntu-24.04) disappears when the runner image changes.
"""

import ast
import re
import shlex
import sys
from importlib.metadata import packages_distributions
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = ROOT / ".github/workflows/release.yml"
ENTRY = "scripts.release_preflight"


def _third_party_imports(module: str, seen: set[str]) -> set[str]:
    """Top-level non-stdlib imports of `module` and the `scripts.*` modules it imports."""
    if module in seen:
        return set()
    seen.add(module)
    tree = ast.parse((ROOT / (module.replace(".", "/") + ".py")).read_text(encoding="utf-8"))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            names = [alias.name for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.module == "scripts":
            # `from scripts import check_metadata` names the submodules themselves.
            names = [f"scripts.{alias.name}" for alias in node.names]
        elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
            names = [node.module]
        else:
            continue
        for name in names:
            top = name.split(".")[0]
            if top == "scripts":
                found |= _third_party_imports(name, seen)
            elif top not in sys.stdlib_module_names and top != "__future__":
                found.add(top)
    return found


def _normalize(dist: str) -> str:
    return re.sub(r"[-_.]+", "-", dist).lower()


def _preflight_with_packages() -> set[str]:
    steps = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))["jobs"]["preflight"]["steps"]
    runs = [step["run"] for step in steps if ENTRY in step.get("run", "")]
    assert runs, f"no preflight step runs {ENTRY}"
    args = shlex.split(runs[0])
    values = [args[i + 1] for i, arg in enumerate(args[:-1]) if arg == "--with"]
    values += [arg.split("=", 1)[1] for arg in args if arg.startswith("--with=")]
    # `--with a,b` declares several packages; drop version specifiers.
    return {
        _normalize(re.split(r"[<>=!~\[; ]", part.strip(), maxsplit=1)[0])
        for value in values
        for part in value.split(",")
        if part.strip()
    }


def test_preflight_step_declares_every_third_party_import() -> None:
    declared = _preflight_with_packages()
    distributions = packages_distributions()
    missing = {
        name
        for name in _third_party_imports(ENTRY, set())
        if not {_normalize(dist) for dist in distributions.get(name, [name])} & declared
    }
    assert not missing, f"add `--with` for {sorted(missing)} to the release preflight step"
