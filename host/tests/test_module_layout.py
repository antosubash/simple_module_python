"""Keep every module package root to the layout in docs/module-layout.md."""

from __future__ import annotations

import tomllib
from pathlib import Path

import pytest

MODULES = Path(__file__).resolve().parents[2] / "modules"
ALLOWED_ROOT = frozenset(
    {
        "__init__.py",
        "py.typed",
        "module.py",
        "models.py",
        "models",
        "tasks.py",
        "task_config.py",
        "contracts",
        "pages",
        "locales",
        "theme.css",
        "styles.css",
        "cli.py",
        "core",
        "web",
        "ui",
    }
)
# Add named domain areas here only when they contain several related features.
DOMAIN_AREAS: dict[str, frozenset[str]] = {
    "api_tokens": frozenset({"credentials"}),
    "audit_log": frozenset({"entries"}),
    "auth": frozenset({"oidc_common"}),
    "background_tasks": frozenset({"executions", "logs", "outbox", "worker"}),
    "branding": frozenset({"assets"}),
    "file_storage": frozenset({"backends", "files", "multipart"}),
    "keycloak": frozenset({"identity"}),
    "mail": frozenset({"delivery"}),
    "oidc": frozenset({"identity"}),
    "permissions": frozenset({"grants"}),
    "settings": frozenset({"module_settings"}),
    "tenants": frozenset({"invitations", "resolution"}),
    "users": frozenset({"accounts", "admin", "auth_local", "demo", "invites", "mailer", "oauth"}),
}

# Plain re-export shims (#500) that predate the layout: public compat paths kept
# at the root until their own 0.1.0 deprecation expires (host/tests/test_deprecation_expiry.py),
# then deleted together with the entry here.
DEPRECATED_ROOT: dict[str, frozenset[str]] = {
    "settings": frozenset({"hydrate.py", "module_registry.py", "registration.py"}),
}


def _is_layout_shim(path: Path) -> bool:
    """A moved module's old path: a deprecated alias, allowed until its remove_in."""
    text = path.read_text(encoding="utf-8")
    return "deprecated_module(" in text and "sys.modules[__name__]" in text


def _only_bytecode(path: Path) -> bool:
    """A directory an older checkout left behind holding only ``__pycache__``."""
    return all(child.name == "__pycache__" for child in path.iterdir())


def _is_shim_package(path: Path) -> bool:
    """An old package path kept only for its aliases: shims plus a docstring __init__."""
    files = [f for f in path.glob("*.py") if f.name != "__init__.py"]
    return bool(files) and all(_is_layout_shim(f) for f in files)


@pytest.mark.parametrize("module", sorted(p.name for p in MODULES.iterdir() if p.is_dir()))
def test_module_root_layout(module: str) -> None:
    package = MODULES / module / module
    assert package.is_dir(), f"Missing package for {module}"
    entries = {
        p.name
        for p in package.iterdir()
        if (p.suffix == ".py" and not _is_layout_shim(p))
        or (
            p.is_dir()
            and p.name != "__pycache__"
            and not _only_bytecode(p)
            and not _is_shim_package(p)
        )
    }
    deprecated = DEPRECATED_ROOT.get(module, frozenset())
    assert deprecated <= {p.name for p in package.iterdir()}, (
        f"{module}: remove expired DEPRECATED_ROOT entries"
    )
    allowed = ALLOWED_ROOT | DOMAIN_AREAS.get(module, frozenset()) | deprecated
    assert not entries - allowed, f"{module}: unexpected roots {entries - allowed}"
    if (package / "cli.py").is_file():
        project = tomllib.loads((MODULES / module / "pyproject.toml").read_text())["project"]
        targets = [
            value for group in project.get("entry-points", {}).values() for value in group.values()
        ]
        assert any(value.split(":")[0] == f"{module}.cli" for value in targets)
    # Tests mirror the package areas: tests/<area>/<feature>/test_<module>_*.py.
    assert not list((MODULES / module / "tests").glob("test_*.py")), module
