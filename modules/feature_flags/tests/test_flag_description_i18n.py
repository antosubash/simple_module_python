"""Feature flag descriptions are translated server-side (TEST-016)."""

from __future__ import annotations

from feature_flags.service import FeatureFlagService
from simple_module_core.feature_flags import FeatureFlagDefinition, FeatureFlagRegistry
from simple_module_core.i18n import Translator

PUBLIC_UPLOADS = "file_storage.public_uploads"


def _translator(app, locale: str) -> Translator:
    registry = app.state.sm.i18n_registry
    if locale not in registry.supported_locales:  # test hosts default to ["en"]
        registry.supported_locales = [*registry.supported_locales, locale]
        registry.load()
    return Translator(registry, locale=locale, default_locale="en")


async def _description(app, db_session, locale: str) -> str:
    svc = FeatureFlagService(db_session)
    views = await svc.list_flags(app.state.sm.feature_flags, translate=_translator(app, locale).t)
    return next(v.description for v in views if v.name == PUBLIC_UPLOADS)


async def test_description_follows_the_locale(app, db_session):
    english = await _description(app, db_session, "en")
    german = await _description(app, db_session, "de")
    assert english == "Allow unauthenticated uploads (future)."
    assert german != english
    assert "Uploads" in german


async def test_unresolved_key_keeps_the_literal(db_session):
    reg = FeatureFlagRegistry()
    reg.add(FeatureFlagDefinition(name="x", description="Literal", description_key="nope.key"))
    views = await FeatureFlagService(db_session).list_flags(reg, translate=lambda k: k)
    assert views[0].description == "Literal"
