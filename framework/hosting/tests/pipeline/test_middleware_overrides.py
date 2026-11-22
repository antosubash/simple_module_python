"""Middleware overrides fail closed and retain the target's position/options."""

import pytest
from fastapi import FastAPI
from simple_module_hosting.boot import app_builder
from simple_module_hosting.pipeline._body_limit import BodyLimitMiddleware
from simple_module_hosting.pipeline.middleware import SecurityHeadersMiddleware
from simple_module_hosting.pipeline.session import SessionMiddleware
from simple_module_hosting.rate_limit._rate_limit import RateLimitMiddleware
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware


@pytest.mark.parametrize(
    "target",
    [BodyLimitMiddleware, RateLimitMiddleware, SecurityHeadersMiddleware, SessionMiddleware],
)
def test_protected_layer_cannot_be_disabled(settings, target):
    from simple_module_hosting import disable_middleware

    with pytest.raises(ValueError, match="cannot be disabled"):
        app_builder.create_app(settings, customize=lambda app: disable_middleware(app, target))


def test_auth_cannot_be_disabled(settings):
    from auth.web.middleware import AuthMiddleware
    from simple_module_hosting import disable_middleware

    with pytest.raises(ValueError, match="cannot be disabled"):
        app_builder.create_app(
            settings, customize=lambda app: disable_middleware(app, AuthMiddleware)
        )


def test_replacement_must_implement_target_contract(settings):
    from simple_module_hosting import replace_middleware

    with pytest.raises(TypeError, match="subclass"):
        app_builder.create_app(
            settings,
            customize=lambda app: replace_middleware(
                app, SessionMiddleware, Middleware(GZipMiddleware)
            ),
        )


def test_replacement_requires_explicit_middleware_object(settings):
    from simple_module_hosting import replace_middleware

    with pytest.raises(TypeError, match="Middleware"):
        app_builder.create_app(
            settings,
            customize=lambda app: replace_middleware(app, SessionMiddleware, None),
        )


def test_optional_layer_disabled_and_other_app_unchanged(settings):
    from simple_module_hosting import disable_middleware

    app = app_builder.create_app(
        settings, customize=lambda app: disable_middleware(app, GZipMiddleware)
    )
    assert GZipMiddleware not in [m.cls for m in app.user_middleware]
    other = app_builder.create_app(settings)
    assert GZipMiddleware in [m.cls for m in other.user_middleware]


def test_replacement_keeps_position_and_constructor_defaults(settings):
    from simple_module_hosting import replace_middleware

    class CustomSession(SessionMiddleware):
        pass

    # Starlette types a full constructor call; assembly supplies the required secret.
    replacement = Middleware(CustomSession, session_cookie="custom")  # ty: ignore[missing-argument]
    app = app_builder.create_app(
        settings,
        customize=lambda app: replace_middleware(app, SessionMiddleware, replacement),
    )
    layers = app.user_middleware
    replacement = next(m for m in layers if m.cls is CustomSession)
    assert layers[layers.index(replacement) + 1].cls.__name__ == "InertiaMiddleware"
    assert replacement.kwargs["secret_key"] == settings.secret_key
    assert replacement.kwargs["secret_key_provider"]() == settings.secret_key
    assert replacement.kwargs["https_only"] is False
    assert replacement.kwargs["session_cookie"] == "custom"


@pytest.mark.parametrize(
    "original_positional", [False, True], ids=["keyword-to-positional", "positional-to-keyword"]
)
def test_replacement_merges_constructor_parameters(original_positional):
    from simple_module_hosting import replace_middleware
    from simple_module_hosting.pipeline.middleware_config import finalize_middleware

    class CustomGZip(GZipMiddleware):
        pass

    app = FastAPI()
    if original_positional:
        app.add_middleware(GZipMiddleware, 500, 4)
        replacement = Middleware(CustomGZip, minimum_size=1024)
    else:
        app.add_middleware(GZipMiddleware, minimum_size=500, compresslevel=4)
        replacement = Middleware(CustomGZip, 1024)
    replace_middleware(app, GZipMiddleware, replacement)
    finalize_middleware(app)

    stack = app.build_middleware_stack()
    while not isinstance(stack, CustomGZip):
        stack = stack.app
    assert stack.minimum_size == 1024
    assert stack.compresslevel == 4


def test_forwarding_constructor_keeps_inherited_positionals():
    from simple_module_hosting import replace_middleware
    from simple_module_hosting.pipeline.middleware_config import finalize_middleware

    class ForwardingGZip(GZipMiddleware):
        def __init__(self, *args, **options):
            super().__init__(*args, **options)

    class CustomGZip(ForwardingGZip):
        pass

    app = FastAPI()
    app.add_middleware(ForwardingGZip, 1024, 4)
    replace_middleware(app, ForwardingGZip, Middleware(CustomGZip))
    finalize_middleware(app)

    stack = app.build_middleware_stack()
    while not isinstance(stack, CustomGZip):
        stack = stack.app
    assert (stack.minimum_size, stack.compresslevel) == (1024, 4)


def test_missing_target_refused(settings):
    from simple_module_hosting import disable_middleware
    from simple_module_hosting.pipeline._server_timing import ServerTimingMiddleware

    with pytest.raises(KeyError, match="ServerTimingMiddleware"):
        app_builder.create_app(
            settings, customize=lambda app: disable_middleware(app, ServerTimingMiddleware)
        )


def test_helpers_refuse_changes_after_assembly(settings):
    from simple_module_hosting import add_middleware, disable_middleware

    app = app_builder.create_app(settings)
    with pytest.raises(RuntimeError, match="finalized"):
        add_middleware(app, GZipMiddleware, stage="before_session")
    with pytest.raises(RuntimeError, match="finalized"):
        disable_middleware(app, GZipMiddleware)


@pytest.mark.parametrize(
    "options",
    [{"stage": "typo"}, {"after": "session"}, {"stage": "before_session", "after": "tenant"}],
)
def test_invalid_stage_refused(settings, options):
    from simple_module_hosting import add_middleware

    with pytest.raises(ValueError, match=r"stage|after"):
        app_builder.create_app(
            settings, customize=lambda app: add_middleware(app, GZipMiddleware, **options)
        )
