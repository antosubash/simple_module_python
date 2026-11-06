"""Ratchet package roots while existing modules migrate one PR at a time."""

# Keep the frozen filename inventory readable as whitespace-separated data.
# ruff: noqa: SIM905

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
    "branding": frozenset({"assets"}),
    "keycloak": frozenset({"identity"}),
    "mail": frozenset({"delivery"}),
    "oidc": frozenset({"identity"}),
    "permissions": frozenset({"grants"}),
    "settings": frozenset({"module_settings"}),
    "tenants": frozenset({"invitations", "resolution"}),
}

# Plain re-export shims (#500) that predate the layout: public compat paths kept
# at the root until their own 0.1.0 deprecation expires (host/tests/test_deprecation_expiry.py),
# then deleted together with the entry here.
DEPRECATED_ROOT: dict[str, frozenset[str]] = {
    "settings": frozenset({"hydrate.py", "module_registry.py", "registration.py"}),
}

# Frozen inventory, not a computed baseline: moves must remove their old entries.
LEGACY_FLAT: dict[str, frozenset[str]] = {
    "background_tasks": frozenset(
        """
        _lifecycle.py _signal_bus.py _signal_support.py after_commit.py celery_app.py
        config_guards.py constants.py db_settings.py deps.py endpoints filters.py health.py
        invalidation.py log_context.py log_purge.py log_service.py log_sink.py
        outbox_claim.py outbox_clock.py outbox_dispatch.py outbox_guard.py outbox_loop.py
        outbox_service.py outbox_support.py outbox_sweep.py outbox_transport.py
        outbox_worker.py retry_service.py runner.py service.py services.py settings.py
        settings_celery.py settings_env_checks.py settings_logs.py signals.py sync_db.py
        task_heartbeat.py task_resource.py task_routing.py tenant_celery.py
        tenant_context.py tracking.py worker_inspector.py worker_settings.py
        workers_state.py
        """.split()
    ),
    "file_storage": frozenset(
        """
        aggregates.py audit_labels.py backend_guard.py backends body_limits.py checksum.py
        constants.py cookieless.py cors.py csp.py deletes.py deps.py downloads.py endpoints
        errors.py format.py health.py media_types.py object_reaper.py queries.py ranges.py
        reads.py resolve.py scope.py service.py services.py serving.py settings.py
        tenant_cache.py tenant_deletion.py thumbnails.py upload_guards.py upload_support.py
        uploads.py visibility.py worker.py worker_support.py
        """.split()
    ),
    "users": frozenset(
        """
        admin administrators.py audit.py auth_local backend.py bootstrap.py constants.py
        credentials.py data_compatibility.py db_adapter.py demo deps.py directory.py
        errors.py exceptions.py invites mailer manager.py middleware.py oauth provider.py
        registration.py reset_revocation.py roles_cache.py session_revocation.py
        session_version_cache.py settings.py setup.py setup_action.py shared_props.py
        startup.py state.py token_storage.py token_strategy.py
        """.split()
    ),
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
    legacy = LEGACY_FLAT.get(module, frozenset())
    if module in LEGACY_FLAT:
        assert legacy, f"{module}: remove the empty LEGACY_FLAT entry"
    assert not entries - allowed - legacy, (
        f"{module}: unexpected roots {entries - allowed - legacy}"
    )
    assert legacy <= entries, f"{module}: remove stale LEGACY_FLAT entries {legacy - entries}"
    assert not legacy & allowed, f"{module}: remove allowed entries from LEGACY_FLAT"
    if (package / "cli.py").is_file():
        project = tomllib.loads((MODULES / module / "pyproject.toml").read_text())["project"]
        targets = [
            value for group in project.get("entry-points", {}).values() for value in group.values()
        ]
        assert any(value.split(":")[0] == f"{module}.cli" for value in targets)
    if module not in LEGACY_FLAT:
        assert not list((MODULES / module / "tests").glob("test_*.py")), module


def test_legacy_modules_still_exist() -> None:
    assert all((MODULES / name / name).is_dir() for name in LEGACY_FLAT)
