"""Shared catalogs cache by registry, locale and audience, and follow reloads."""

from types import SimpleNamespace

from fastapi import FastAPI
from simple_module_core.i18n import I18nRegistry
from simple_module_hosting._i18n_json import catalog_json
from simple_module_hosting._inertia_shared import build_i18n_block
from starlette.requests import Request


def _block(registry, locale="en", authenticated=False):
    app = FastAPI()
    app.state.sm = SimpleNamespace(i18n_registry=registry)
    request = Request(
        {
            "type": "http",
            "method": "GET",
            "path": "/",
            "headers": [],
            "app": app,
            "state": {"locale": locale},
        }
    )
    return build_i18n_block(request.scope, request, is_authenticated=authenticated)


def test_catalog_json_cache_tracks_locale_audience_and_reload(tmp_path):
    public = tmp_path / "public"
    admin = tmp_path / "admin"
    public.mkdir()
    admin.mkdir()
    (public / "en.json").write_text('{"title":"Hello"}')
    (public / "es.json").write_text('{"title":"Hola"}')
    (admin / "en.json").write_text('{"title":"Secret"}')
    (admin / "es.json").write_text("{}")
    registry = I18nRegistry("en", ["en", "es"])
    registry.add_source("public", public)
    registry.add_source("admin", admin, audience="admin")
    registry.load()
    first = _block(registry)["messages"]
    assert first == {"public.title": "Hello"}
    assert _block(registry)["messages"] is first
    assert _block(registry, "es")["messages"] == {"public.title": "Hola"}
    assert _block(registry, "es", True)["messages"] == {
        "public.title": "Hola",
        "admin.title": "Secret",
    }
    assert _block(I18nRegistry("en", ["en"]))["messages"] == {}
    (public / "en.json").write_text('{"title":"Updated"}')
    registry.load()
    updated = _block(registry)["messages"]
    assert updated == {"public.title": "Updated"}
    assert updated is not first


def test_a_registry_that_cannot_be_weak_referenced_is_served_uncached():
    class _Stub:
        __slots__ = ()

        def messages_snapshot(self, locale, *, include_admin):
            return {"a": "A"}

    assert catalog_json(_Stub(), "en", include_admin=True) == {"a": "A"}
