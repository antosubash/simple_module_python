"""Diagnostics that validate i18n locale file coverage and consistency."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from simple_module_core.diagnostics._types import Diagnostic, DiagnosticLevel
from simple_module_core.i18n import flatten_messages

if TYPE_CHECKING:
    from simple_module_core.module import ModuleBase


class I18nDiagnostics:
    """Validates locale file coverage per module.

    Codes:
    - SM013: missing locale file for a supported locale.
    - SM014: non-default locale is missing keys present in the default.
    - SM015: non-default locale has keys not present in the default.
    - SM016: locale JSON fails to parse or has non-string leaves.
    """

    def __init__(
        self,
        supported_locales: list[str] | None,
        default_locale: str,
        extra_sources: list[tuple[str, str, Path]] | None = None,
    ) -> None:
        """Build the diagnostic.

        ``supported_locales`` is the set of locales this install promises to
        ship. ``None`` means *nobody declared one* — each namespace is then
        checked against the locale files it actually has on disk. SM013 is
        skipped in that mode (a locale nothing promised cannot be missing),
        but SM014/SM015 still hold every shipped translation to the default
        locale's key set. Without this, an install that never set
        ``SM_I18N_SUPPORTED_LOCALES`` ran no locale checks at all and drift
        accumulated with nothing to flag it.

        ``extra_sources`` is an optional list of ``(reporter_name, namespace,
        locale_dir)`` triples for locale directories that aren't owned by any
        ``ModuleBase`` instance — notably the host's ``host/locales/`` and
        the shared ``packages/ui/locales/``. ``reporter_name`` is used as the
        ``module_name`` field on findings for display purposes.
        """
        self.supported_locales = None if supported_locales is None else list(supported_locales)
        self.default_locale = default_locale
        self.extra_sources = list(extra_sources or [])

    def run(self, modules: list[ModuleBase]) -> list[Diagnostic]:
        findings: list[Diagnostic] = []
        for mod in modules:
            for namespace, locale_dir in mod.locale_dirs().items():
                findings.extend(self._check_namespace(mod.meta.name, namespace, Path(locale_dir)))
        for reporter_name, namespace, locale_dir in self.extra_sources:
            findings.extend(self._check_namespace(reporter_name, namespace, Path(locale_dir)))
        return findings

    def _check_namespace(
        self, module_name: str, namespace: str, locale_dir: Path
    ) -> list[Diagnostic]:
        findings: list[Diagnostic] = []
        per_locale_keys: dict[str, set[str]] = {}
        declared = self.supported_locales is not None
        locales = self.supported_locales if declared else self._locales_on_disk(locale_dir)

        for locale in locales or ():
            path = locale_dir / f"{locale}.json"
            if not path.is_file():
                if not declared:
                    continue
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM013",
                        message=(f"Missing locale file {locale}.json for namespace '{namespace}'"),
                        module_name=module_name,
                        file=str(path),
                        suggestion=f"Create {path} (even if empty: '{{}}')",
                    )
                )
                continue
            try:
                raw = json.loads(path.read_text(encoding="utf-8"))
                if not isinstance(raw, dict):
                    raise ValueError("top-level JSON must be an object")
                flat = flatten_messages(raw)
            except (json.JSONDecodeError, ValueError) as exc:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.ERROR,
                        code="SM016",
                        message=f"Invalid locale JSON in {path}: {exc}",
                        module_name=module_name,
                        file=str(path),
                    )
                )
                continue
            per_locale_keys[locale] = set(flat.keys())

        default_keys = per_locale_keys.get(self.default_locale, set())
        for locale, keys in per_locale_keys.items():
            if locale == self.default_locale:
                continue
            missing = default_keys - keys
            extra = keys - default_keys
            if missing:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM014",
                        message=(
                            f"Locale '{locale}' in namespace '{namespace}' is missing keys: "
                            f"{', '.join(sorted(missing))}"
                        ),
                        module_name=module_name,
                    )
                )
            if extra:
                findings.append(
                    Diagnostic(
                        level=DiagnosticLevel.WARNING,
                        code="SM015",
                        message=(
                            f"Locale '{locale}' in namespace '{namespace}' has keys not in "
                            f"default: {', '.join(sorted(extra))}"
                        ),
                        module_name=module_name,
                    )
                )
        return findings

    @staticmethod
    def _locales_on_disk(locale_dir: Path) -> list[str]:
        """Locale tags a directory actually ships, from its ``<tag>.json`` files.

        The default locale sorts first only by accident of the alphabet, which
        does not matter: the parity comparison below looks it up by name.
        """
        if not locale_dir.is_dir():
            return []
        return sorted(path.stem for path in locale_dir.glob("*.json"))


def check_unknown_overrides(unknown: dict[str, list[str]]) -> list[Diagnostic]:
    """SM027: host locale overrides naming keys no catalog defines (skipped)."""
    return [
        Diagnostic(
            level=DiagnosticLevel.WARNING,
            code="SM027",
            message=(
                f"Host locale override ({locale}) names keys no catalog defines "
                f"(skipped): {', '.join(keys)}"
            ),
            module_name="host",
            suggestion="Overrides replace an existing key by its full dotted path; fix the typo.",
        )
        for locale, keys in sorted(unknown.items())
    ]


def unknown_overrides_for(
    modules: list[ModuleBase],
    extra_sources: list[tuple[str, str, Path]],
    supported_locales: list[str] | None,
    default_locale: str,
) -> dict[str, list[str]]:
    """Load the catalogs like the host does and return the unknown override keys.

    Lets ``make doctor`` report SM027 without booting the app. Overrides live
    in ``overrides/`` beside the ``host`` source's locale directory.
    """
    from simple_module_core.i18n import I18nRegistry

    host_dirs = [d for _, ns, d in extra_sources if ns == "host" and (d / "overrides").is_dir()]
    if not host_dirs:
        return {}
    overrides_dir = host_dirs[0] / "overrides"
    locales = list(supported_locales or [])
    if not locales:
        locales = sorted({default_locale, *(p.stem for p in overrides_dir.glob("*.json"))})
    registry = I18nRegistry(default_locale=default_locale, supported_locales=locales)
    for mod in modules:
        for namespace, locale_dir in mod.locale_dirs().items():
            registry.add_source(namespace, Path(locale_dir))
    for _, namespace, locale_dir in extra_sources:
        registry.add_source(namespace, locale_dir)
    registry.add_overrides(overrides_dir)
    registry.load()
    return registry.unknown_override_keys
