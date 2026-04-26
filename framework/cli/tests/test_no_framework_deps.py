"""Guard: `simple-module` distribution depends only on typer + tomlkit.

If a future change accidentally pulls in simple_module_core, FastAPI,
SQLModel, or anything else, this test fires immediately.
"""

from __future__ import annotations

from importlib.metadata import distribution


def _normalize(req: str) -> str:
    """'typer (>=0.12)' -> 'typer'. Strip version specs + extras + spaces."""
    head = req.split(";", 1)[0]
    for sep in ("(", ">=", ">", "<", "==", "[", " "):
        head = head.split(sep, 1)[0]
    return head.strip().lower().replace("_", "-")


def test_simple_module_runtime_deps_are_minimal() -> None:
    requires = distribution("simple-module").requires or []
    names = {_normalize(r) for r in requires}
    assert names == {"typer", "tomlkit"}, (
        f"simple-module direct deps drifted; got {sorted(names)}, expected {{'typer', 'tomlkit'}}"
    )
