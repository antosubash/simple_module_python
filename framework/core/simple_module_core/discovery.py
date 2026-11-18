"""Module discovery via Python entry_points and dependency ordering."""

from __future__ import annotations

import logging
from collections.abc import Sequence
from dataclasses import replace
from importlib.metadata import entry_points

from simple_module_core._auth_providers import provides_auth
from simple_module_core._entry_point_errors import own_package_missing, stale_path_message
from simple_module_core._module_conventions import (
    get_module_package_name as get_module_package_name,
)
from simple_module_core._module_ordering import (
    missing_dependencies as missing_dependencies,
)
from simple_module_core._module_ordering import (
    topological_sort as topological_sort,
)
from simple_module_core.dotenv import env_str, load_dotenv_into_environ
from simple_module_core.exceptions import (
    InvalidModuleError,
)
from simple_module_core.module import ModuleBase, ModuleMeta
from simple_module_core.module_meta import _VERSION

logger = logging.getLogger(__name__)

ENTRY_POINT_GROUP = "simple_module"

DEFAULT_AUTH_PROVIDER = "users"
"""Auth provider activated when several are installed — see select_auth_provider."""


def discover_modules(
    enabled: Sequence[str] | None = None,
    *,
    strict: bool = False,
) -> list[ModuleBase]:
    """Discover all installed modules via ``[project.entry-points.simple_module]``.

    Returns instantiated module objects (unsorted). Raises
    :class:`FrameworkVersionError` if any discovered module's
    ``requires_framework`` spec rejects the current framework API version.

    Parameters
    ----------
    enabled:
        Case-insensitive allowlist of entry-point names or ``ModuleMeta.name``.
        If every item matches an installed entry-point name, only those entry
        points are imported. Otherwise all candidates must load to resolve
        arbitrary metadata names. ``None`` loads all; an empty list imports
        nothing. Unmatched names log a warning.
    strict:
        When ``True``, any invalid module (failed to load, not a
        ``ModuleBase`` subclass, missing/invalid ``meta``) raises
        :class:`InvalidModuleError` immediately. Callers in production
        should pass ``strict=True`` so a broken deployment fails loudly
        at boot rather than silently losing a feature.

        When ``False`` (the default — preserves dev ergonomics), invalid
        modules are logged and skipped.
    """
    # Imported here to avoid a circular import at module load time.
    from simple_module_core.versioning import check_framework_compatibility

    def fail(msg: str, exc: BaseException | None = None, *, with_traceback: bool = True) -> None:
        if strict:
            raise InvalidModuleError(msg) from exc
        if exc is not None and with_traceback:
            logger.exception("%s — skipping", msg)
        else:
            logger.error("%s — skipping", msg)

    eps = entry_points(group=ENTRY_POINT_GROUP)
    modules: list[ModuleBase] = []
    allowlist_lower = {name.lower() for name in enabled} if enabled is not None else None
    ep_names = {ep.name.lower() for ep in eps}
    # Metadata names are arbitrary: an unresolved token could name any candidate.
    filter_before_load = allowlist_lower is not None and allowlist_lower <= ep_names
    matched: set[str] = set()
    origins: dict[str, str] = {}

    for ep in eps:
        if filter_before_load and ep.name.lower() not in allowlist_lower:
            continue
        try:
            module_cls = ep.load()
        except Exception as exc:
            if own_package_missing(ep, exc):
                fail(stale_path_message(ep, exc), exc, with_traceback=False)
            else:
                fail(f"Failed to load module entry point '{ep.name}': {exc}", exc)
            continue

        try:
            instance = module_cls()
        except Exception as exc:
            fail(
                f"Failed to instantiate module '{ep.name}' ({module_cls!r}): {exc}",
                exc,
            )
            continue

        if not isinstance(instance, ModuleBase):
            fail(
                f"Entry point '{ep.name}' loaded {module_cls!r} which is not a ModuleBase subclass"
            )
            continue

        meta = getattr(instance, "meta", None)
        if not isinstance(meta, ModuleMeta):
            fail(
                f"Module {module_cls.__qualname__!r} (entry point '{ep.name}') "
                "is missing 'meta = ModuleMeta(...)'"
            )
            continue

        names = {ep.name.lower(), meta.name.lower()}
        if allowlist_lower is not None and not names & allowlist_lower:
            logger.info(
                "Module '%s' is installed but not in modules_enabled — skipping",
                meta.name,
            )
            continue

        matched.update(names)
        origin = f"entry point '{ep.name}'"
        if ep.dist is not None:
            origin += f" in distribution '{ep.dist.metadata['Name']}'"
        if meta.name in origins:
            message = (
                f"SM008 Duplicate module name '{meta.name}': {origins[meta.name]} and {origin}"
            )
            if strict:
                raise InvalidModuleError(message)
            logger.warning("%s — skipping later entry point", message)
            continue
        origins[meta.name] = origin

        if meta.version is _VERSION:
            # Resolve on this instance; the class metadata is shared across discoveries.
            instance.meta = meta = replace(
                meta, version=ep.dist.version if ep.dist is not None else "1.0.0"
            )
        modules.append(instance)
        logger.info("Discovered module: %s (v%s)", meta.name, meta.version)

    # Warn about allowlist entries that didn't resolve to an installed module.
    if allowlist_lower is not None:
        missing = allowlist_lower - matched
        for name in missing:
            logger.warning(
                "modules_enabled references '%s' which is not installed — ignoring",
                name,
            )

    check_framework_compatibility(modules)
    return modules


def resolve_auth_provider() -> str:
    """Return the configured auth provider name, honoring ``.env``.

    For tools that run outside the host process (``make doctor``, ``smpy host
    gen-pages``) and so have no ``BootstrapSettings`` to read from. The host
    passes ``settings.auth_provider`` to :func:`select_auth_provider` instead.
    """
    load_dotenv_into_environ()
    return env_str("SM_AUTH_PROVIDER", DEFAULT_AUTH_PROVIDER)


def select_auth_provider(
    modules: Sequence[ModuleBase],
    preferred: str = DEFAULT_AUTH_PROVIDER,
    *,
    strict: bool = False,
) -> list[ModuleBase]:
    """Drop every auth provider except ``preferred`` when several are installed.

    ``users`` and ``keycloak`` both claim ``app.state.auth.auth_provider``, so
    only one can be active — that's what SM020 reports. A dev workspace has
    both installed (``uv sync --all-packages`` installs every member), which
    would otherwise fail the boot on a fresh clone. Selecting one here keeps
    the alternative provider installed and testable but inert.

    Nothing is dropped when fewer than two providers are present — a host that
    installs only ``keycloak`` keeps it whatever ``preferred`` says.

    A ``preferred`` that names none of the installed providers is a
    misconfiguration (typically a typo). Leaving every provider mounted means
    two modules write ``app.state.auth.auth_provider`` and the topological
    order silently decides the winner, so this always warns, and with
    ``strict`` raises :class:`InvalidModuleError`. Callers in production
    should pass ``strict=True``: SM020 would catch this, but diagnostics run
    in development only, so nothing else reports it in a deployed app.
    """
    providers = [m for m in modules if provides_auth(m)]
    if len(providers) < 2:
        return list(modules)

    installed = ", ".join(m.meta.name for m in providers)
    keep = next((m for m in providers if m.meta.name.lower() == preferred.lower()), None)
    if keep is None:
        msg = (
            f"SM_AUTH_PROVIDER={preferred!r} matches none of the installed auth "
            f"providers ({installed}); all of them stay mounted and the last one "
            "registered wins"
        )
        if strict:
            raise InvalidModuleError(msg)
        logger.warning("%s — set it to one of the names above", msg)
        return list(modules)

    logger.info(
        "Auth provider '%s' active (SM_AUTH_PROVIDER); skipping also-installed: %s",
        keep.meta.name,
        ", ".join(m.meta.name for m in providers if m is not keep),
    )
    return [m for m in modules if m is keep or not provides_auth(m)]
