"""Subject provider contracts; membership predicates are synchronous SQL builders."""

from __future__ import annotations

import re
from collections.abc import Awaitable, Callable, Collection, Mapping
from dataclasses import dataclass
from typing import Any

from simple_module_core.principals import PRINCIPALS_KEY, PrincipalRegistry
from simple_module_core.resources import ResourcePrincipal
from simple_module_core.user_directory import UserDirectory
from sqlalchemy.ext.asyncio import AsyncSession

from sharing.contracts.schemas import ShareCandidate
from sharing.core.audience import Audience, OpenAudience

SUBJECTS_KEY = "sharing.subjects"


@dataclass(frozen=True)
class SubjectContext:
    db: AsyncSession
    directory: UserDirectory
    audience: Audience | OpenAudience
    principal: ResourcePrincipal
    translate: Callable[[str], str] | None = None


@dataclass(frozen=True)
class SubjectProvider:
    """A trusted module's subject implementation.

    Validation/search/labels must enforce visibility in the active tenant and
    mask private data. ``labels`` is batched; ``membership`` builds SQL without
    I/O (use a subquery for live memberships), never per-resource lookups.
    """

    name: str
    label_key: str
    validate: Callable[[SubjectContext, str], Awaitable[str | None]]
    candidates: Callable[[SubjectContext, str, str], Awaitable[list[ShareCandidate]]]
    labels: Callable[[SubjectContext, Collection[str]], Awaitable[Mapping[str, str]]]
    membership: Callable[[ResourcePrincipal, Any], Any]


class SubjectRegistry:
    """Host/worker-local providers; duplicate names fail at registration."""

    def __init__(self) -> None:
        self._providers: dict[str, SubjectProvider] = {}

    def register(self, provider: SubjectProvider) -> None:
        if not re.fullmatch(r"[a-z][a-z0-9_]{0,15}", provider.name):
            raise ValueError("Subject type must be a lowercase identifier of at most 16 characters")
        if provider.name in self._providers:
            raise ValueError(f"Subject type {provider.name!r} is registered twice")
        self._providers[provider.name] = provider

    def get(self, name: str) -> SubjectProvider | None:
        return self._providers.get(name)

    def all(self) -> list[SubjectProvider]:
        return list(self._providers.values())


def get_subject_registry(host: Any) -> SubjectRegistry:
    """The same registry during ``register_principal_builder`` and HTTP requests.

    A custom module depends on Sharing, then registers against the supplied
    PrincipalRegistry in its principal-builder hook. No process-global state.
    """
    if isinstance(host, PrincipalRegistry):
        builder = host
    else:
        factory = host.state.sm.db.session_factory
        builder = factory.kw.get("info", {}).get(PRINCIPALS_KEY)
        if builder is None:
            raise RuntimeError("No principal registry bound to this host")
    if SUBJECTS_KEY not in builder.resource_context:
        from sharing.core.subjects import default_subject_registry

        builder.resource_context[SUBJECTS_KEY] = default_subject_registry()
    return builder.resource_context[SUBJECTS_KEY]
