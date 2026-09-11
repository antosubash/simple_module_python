"""The request half of the protocol: every ``X-Inertia-*`` header, typed.

A pure function of the header mapping and method — no Starlette ``Request``
crosses this boundary, so the resolver and its conformance tests never need
a server.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

MergeIntent = Literal["append", "prepend"]


def _csv(value: str | None) -> frozenset[str]:
    if not value:
        return frozenset()
    return frozenset(part.strip() for part in value.split(",") if part.strip())


@dataclass(frozen=True)
class InertiaRequest:
    is_inertia: bool
    version: str | None
    partial_component: str | None
    partial_data: frozenset[str]
    partial_except: frozenset[str]
    reset: frozenset[str]
    error_bag: str | None
    merge_intent: MergeIntent | None
    except_once_props: frozenset[str]
    is_prefetch: bool
    method: str

    @classmethod
    def from_headers(cls, headers: Mapping[str, str], method: str) -> InertiaRequest:
        lower = {k.lower(): v for k, v in headers.items()}
        intent = (lower.get("x-inertia-infinite-scroll-merge-intent") or "").lower()
        return cls(
            is_inertia="x-inertia" in lower,
            version=lower.get("x-inertia-version"),
            partial_component=lower.get("x-inertia-partial-component") or None,
            partial_data=_csv(lower.get("x-inertia-partial-data")),
            partial_except=_csv(lower.get("x-inertia-partial-except")),
            reset=_csv(lower.get("x-inertia-reset")),
            error_bag=lower.get("x-inertia-error-bag") or None,
            merge_intent=intent if intent in ("append", "prepend") else None,
            except_once_props=_csv(lower.get("x-inertia-except-once-props")),
            is_prefetch=(lower.get("purpose") or "").lower() == "prefetch",
            method=method.upper(),
        )

    def is_partial_for(self, component: str) -> bool:
        """A partial reload targets one component and names data or exclusions."""
        return self.partial_component == component and bool(
            self.partial_data or self.partial_except
        )
