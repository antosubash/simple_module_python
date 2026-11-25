"""Named module stages and explicit, boot-time middleware overrides."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from inspect import Parameter, signature
from typing import Any, Literal

from fastapi import FastAPI
from starlette.middleware import Middleware
from starlette.middleware.gzip import GZipMiddleware

from simple_module_hosting.i18n.i18n_middleware import LocaleMiddleware
from simple_module_hosting.observability._observability import RequestLoggingMiddleware
from simple_module_hosting.pipeline._server_timing import ServerTimingMiddleware
from simple_module_hosting.pipeline.compression import HostGZipMiddleware
from simple_module_hosting.pipeline.session import SessionMiddleware

MiddlewareStage = Literal["before_session", "default", "after_tenant"]

# These change compression/observability only, never access or request safety.
_DISABLABLE = frozenset(
    {GZipMiddleware, HostGZipMiddleware, RequestLoggingMiddleware, ServerTimingMiddleware}
)
_STAGE_ANCHORS = {"before_session": SessionMiddleware, "after_tenant": LocaleMiddleware}


@dataclass
class _Configuration:
    stages: dict[str, list[Middleware]] = field(default_factory=dict)
    overrides: dict[type, Middleware | None] = field(default_factory=dict)
    finalized: bool = False


def _configuration(app: FastAPI) -> _Configuration:
    config = getattr(app.state, "_sm_middleware_config", None)
    if config is None:
        config = _Configuration()
        app.state._sm_middleware_config = config
    if config.finalized or app.middleware_stack is not None:
        raise RuntimeError("The middleware pipeline is already finalized")
    return config


def add_middleware(
    app: FastAPI,
    middleware_class: type,
    *args: Any,
    stage: MiddlewareStage = "default",
    after: Literal["tenant"] | None = None,
    **kwargs: Any,
) -> None:
    """Add module middleware in its existing tier or a named stage.

    ``after="tenant"`` aliases ``stage="after_tenant"``: both Tenant and
    Locale have run, but layout permissions have not. Calls within each stage
    retain Starlette's LIFO order. Use during registration or ``customize``.
    """
    config = _configuration(app)
    if after is not None:
        if after != "tenant" or stage != "default":
            raise ValueError('Use after="tenant" alone, or specify a stage')
        stage = "after_tenant"
    if stage not in ("default", "before_session", "after_tenant"):
        raise ValueError(f"Unknown middleware stage: {stage!r}")
    if stage == "default":
        app.add_middleware(middleware_class, *args, **kwargs)
    else:
        config.stages.setdefault(stage, []).append(Middleware(middleware_class, *args, **kwargs))


def replace_middleware(app: FastAPI, target: type, replacement: Middleware) -> None:
    """Replace exactly one installed layer, preserving its position and defaults.

    The explicit Middleware object must name a subclass of ``target``. The
    subclass accepts the original constructor options and owns the same ASGI
    and security contract; options on ``replacement`` override those defaults.
    No middleware executes until assembly has validated every override.
    """
    config = _configuration(app)
    if not isinstance(replacement, Middleware):
        raise TypeError("replacement must be an explicit starlette.middleware.Middleware object")
    if not isinstance(replacement.cls, type) or not issubclass(replacement.cls, target):
        raise TypeError(f"replacement must be a subclass of {target.__name__}")
    _set_override(config, target, replacement)


def disable_middleware(app: FastAPI, target: type) -> None:
    """Disable only GZip, request logging or development ServerTiming.

    All other layers, including module-provided Auth, require a replacement
    implementing their contract. Absent or ambiguous targets fail assembly.
    """
    config = _configuration(app)
    if target not in _DISABLABLE:
        raise ValueError(f"{target.__name__} cannot be disabled; supply a replacement subclass")
    _set_override(config, target, None)


def _set_override(config: _Configuration, target: type, replacement: Middleware | None) -> None:
    if target in config.overrides:
        raise ValueError(f"An override for {target.__name__} is already registered")
    config.overrides[target] = replacement


def finalize_middleware(app: FastAPI) -> None:
    """Splice stages and apply overrides after the outer layers are installed."""
    config = _configuration(app)
    layers = list(app.user_middleware)
    for stage, entries in config.stages.items():
        anchor = _STAGE_ANCHORS[stage]
        index = _target_index(layers, anchor)
        if stage == "after_tenant":
            index += 1  # Inside Locale; also inside Tenant whenever it is enabled.
        layers[index:index] = reversed(entries)
    for target, replacement in config.overrides.items():
        index = _target_index(layers, target)
        original = layers[index]
        if replacement is None:
            del layers[index]
        else:
            # Bind legacy positional options against the public target's signature.
            constructor_class = target if target is GZipMiddleware else original.cls
            layers[index] = _merge_replacement(
                original, replacement, constructor_class=constructor_class
            )
    app.user_middleware = layers
    config.finalized = True


def _merge_replacement(
    original: Middleware,
    replacement: Middleware,
    *,
    constructor_class: Callable[..., Any] | None = None,
) -> Middleware:
    if not original.args and not replacement.args:
        options: dict[str, Any] = dict(original.kwargs)
        options.update(replacement.kwargs)
        return Middleware(replacement.cls, **options)

    constructor = signature(constructor_class or original.cls)
    bound = constructor.bind_partial(None, *original.args, **original.kwargs)
    if replacement.args:
        # Only positional overrides replace inherited ones; binding the bare
        # placeholder would turn a forwarding ``*args`` into ``(None,)``.
        bound.arguments.update(constructor.bind_partial(None, *replacement.args).arguments)
    extra = {}
    for name, value in replacement.kwargs.items():
        parameter = constructor.parameters.get(name)
        if parameter is not None and parameter.kind not in (
            Parameter.VAR_POSITIONAL,
            Parameter.VAR_KEYWORD,
        ):
            bound.arguments[name] = value
        else:
            extra[name] = value
    # Starlette supplies the wrapped app; the placeholder only binds its parameter.
    return Middleware(replacement.cls, *bound.args[1:], **(bound.kwargs | extra))


def _target_index(layers: list[Middleware], target: type) -> int:
    # The Starlette class remains an override target for the host GZip layer.
    matches = (target, HostGZipMiddleware) if target is GZipMiddleware else (target,)
    indices = [index for index, layer in enumerate(layers) if layer.cls in matches]
    if not indices:
        raise KeyError(f"Middleware {target.__name__} is not installed")
    if len(indices) != 1:
        raise ValueError(f"Middleware {target.__name__} is installed more than once")
    return indices[0]
