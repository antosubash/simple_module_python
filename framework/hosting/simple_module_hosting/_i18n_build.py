"""Construct the i18n registry from module, host and UI sources."""

from __future__ import annotations

from pathlib import Path

from simple_module_core import ModuleBase
from simple_module_core.i18n import I18nRegistry

from simple_module_hosting.settings import Settings


def build_i18n_registry(
    settings: Settings,
    modules: list[ModuleBase],
    project_root: Path,
) -> tuple[I18nRegistry, list[tuple[str, str, Path]]]:
    """Construct the i18n registry from module + host + UI sources.

    Returns ``(registry, extra_sources)`` where ``extra_sources`` is the list
    of ``(reporter_name, namespace, dir)`` triples the diagnostic runner
    needs to validate non-module locale directories.
    """
    registry = I18nRegistry(
        default_locale=settings.i18n_default_locale,
        supported_locales=settings.i18n_supported_locales,
    )
    extra_sources: list[tuple[str, str, Path]] = []

    for mod in modules:
        audience = getattr(mod.meta, "i18n_audience", "public")
        for namespace, locale_dir in mod.locale_dirs().items():
            registry.add_source(namespace, locale_dir, audience=audience)

    # The framework's own catalog — the setup wizard ships with this package,
    # so its strings must too, whatever host is serving it.
    hosting_locales = Path(__file__).resolve().parent / "locales"
    registry.add_source("hosting", hosting_locales)
    extra_sources.append(("simple_module_hosting", "hosting", hosting_locales))

    host_locales = project_root / "host" / "locales"
    if host_locales.is_dir():
        registry.add_source("host", host_locales)
        extra_sources.append(("host", "host", host_locales))

    overrides = host_locales / "overrides"
    if overrides.is_dir():
        registry.add_overrides(overrides)

    # Shared UI strings ship inside this package (not ``packages/ui``) so a
    # scaffolded app, which has no ``packages/ui`` checkout, still resolves
    # every ``ui.*`` key.
    ui_locales = Path(__file__).resolve().parent / "ui_locales"
    registry.add_source("ui", ui_locales)
    extra_sources.append(("simple_module_hosting/ui", "ui", ui_locales))

    registry.load()
    return registry, extra_sources
