"""Portable module key constants, generated only in editable source projects."""

import importlib.resources
import logging
from pathlib import Path

from simple_module_core import ModuleBase, get_module_package_name
from simple_module_core.i18n import I18nRegistry

from simple_module_hosting._generated_files import _write_if_changed
from simple_module_hosting.settings import Settings

logger = logging.getLogger(__name__)


def module_key_outputs(modules: list[ModuleBase]) -> list[tuple[ModuleBase, Path]]:
    outputs = []
    for module in modules:
        name = get_module_package_name(module)
        package = Path(str(importlib.resources.files(name)))
        # Wheels ship these files; a consuming app must not write into site-packages.
        project = package.parents[name.count(".")]
        if not (project / "pyproject.toml").is_file():
            continue
        area = next((package / a for a in ("pages", "ui") if (package / a).is_dir()), None)
        if area is not None and module.locale_dirs():
            outputs.append((module, area / "i18n.generated.ts"))
    return outputs


def write_module_keys(
    locale_dirs: dict[str, Path], output: Path, *, default_locale: str = "en"
) -> None:
    from simple_module_hosting.i18n_manifest import _render_keys

    registry = I18nRegistry(default_locale=default_locale, supported_locales=[default_locale])
    for namespace, directory in locale_dirs.items():
        registry.add_source(namespace, directory)
    registry.load()
    keys = sorted(registry.messages(default_locale))
    source = "import '@simple-module-py/i18n';\n\n" + _render_keys(keys)
    source += "\ntype ModuleTranslationResources = {\n"
    source += "".join(f"  readonly '{key}': '';\n" for key in keys)
    source += (
        "};\n\ndeclare module '@simple-module-py/i18n' {\n"
        "  interface TranslationResources extends ModuleTranslationResources {}\n"
        "}\n"
    )
    output.parent.mkdir(parents=True, exist_ok=True)
    _write_if_changed(output, source)


def emit_module_keys(modules: list[ModuleBase], settings: Settings, *, strict: bool) -> None:
    for module, output in module_key_outputs(modules):
        try:
            write_module_keys(
                module.locale_dirs(), output, default_locale=settings.i18n_default_locale
            )
        except OSError:
            if strict:
                raise
            logger.exception("Cannot write module i18n keys to %s", output)
