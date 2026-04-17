"""FastAPI dependency for request-scoped Translator resolution."""

from __future__ import annotations

from typing import Annotated

from fastapi import Depends, Request
from simple_module_core.i18n import Translator


async def get_translator(request: Request) -> Translator:
    """Resolve a Translator bound to ``request.state.locale``.

    Reads the registry from ``request.app.state.sm.i18n_registry`` and the
    default locale from ``request.app.state.sm.settings.i18n_default_locale``.

    ``request.state.locale`` is populated by LocaleMiddleware.
    """
    sm = request.app.state.sm
    default_locale = sm.settings.i18n_default_locale
    locale = getattr(request.state, "locale", default_locale)
    return Translator(sm.i18n_registry, locale=locale, default_locale=default_locale)


TranslatorDep = Annotated[Translator, Depends(get_translator)]
