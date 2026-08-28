"""Setup-step registry — modules declare what a usable install still needs.

A fresh deployment has no administrator, so every route either redirects to a
login nobody can pass or 500s. ``SetupMiddleware`` closes that hole: while any
*required* step reports incomplete, the app serves the setup wizard instead.

Modules contribute steps through
:meth:`~simple_module_core.module.ModuleBase.register_setup_steps`. Which
module contributes matters more than it looks. The obvious implementation —
counting superusers in the host — locks every Keycloak install out of its own
application permanently, because identity lives in Keycloak and the local
users table is legitimately empty forever. Keycloak registers no step, so the
gate simply never engages there.

Completion is recomputed per request rather than latched in a one-way flag.
An install that loses its administrators is then recoverable through the
browser rather than requiring shell access to the container. The cost is that
deleting every admin on a live install reopens setup — acceptable, since an
install with no administrator is already non-functional.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field

# Takes the app, returns whether this step is satisfied. Async because every
# real check is a database query.
SetupCheckFn = Callable[..., Awaitable[bool]]


@dataclass
class SetupStep:
    """One thing an install needs before it can be used.

    Args:
        id: Stable identifier, namespaced by module (``users.administrator``).
            Used as the wizard's step key and in logs.
        title: Short human-readable name, shown as the wizard step heading.
        is_complete: Async predicate returning ``True`` once satisfied.
        description: Optional longer explanation for the wizard.
        required: Whether an incomplete step gates the whole app. A step that
            is *not* required still appears in the wizard but does not hold
            the install closed — for optional polish like a site name.
        order: Lower sorts first. Ties fall back to registration order.
        module: Contributing module; stamped by the registry, not set by hand.
    """

    id: str
    title: str
    is_complete: SetupCheckFn
    description: str = ""
    title_key: str = ""
    """Catalog key for ``title``, resolved against the request's locale.

    Steps come from arbitrary modules, so their titles reach the wizard as
    backend data rather than JSX literals and cannot go through ``useT()`` at
    the call site. Same arrangement ``MenuItem`` already uses for ``label`` /
    ``label_key``: the key wins when it resolves, the literal is the fallback,
    and a module that ships no catalog still renders something readable.
    """
    description_key: str = ""
    """Catalog key for ``description``, with the same fallback rule."""
    required: bool = True
    order: int = 100
    module: str = field(default="")


class SetupRegistry:
    """Aggregates every module's :class:`SetupStep`.

    Populated once during boot and consulted per request by
    ``SetupMiddleware`` — effectively immutable after the registration phase.
    """

    def __init__(self) -> None:
        self._steps: list[SetupStep] = []
        self._current_owner: str = ""

    def set_owner(self, module_name: str) -> None:
        """Attribute subsequently-added steps to *module_name*.

        The host calls this around each ``register_setup_steps`` hook, so a
        step knows its module without changing the ``add`` signature module
        authors use — the same arrangement as ``HealthRegistry``.
        """
        self._current_owner = module_name

    def add(self, step: SetupStep) -> None:
        if not step.module:
            step.module = self._current_owner
        self._steps.append(step)

    @property
    def all_steps(self) -> list[SetupStep]:
        """Every registered step, required or not, in display order."""
        return sorted(self._steps, key=lambda s: s.order)

    @property
    def required_steps(self) -> list[SetupStep]:
        return [s for s in self.all_steps if s.required]

    def __bool__(self) -> bool:
        """``False`` when nothing registered — the gate cannot engage."""
        return bool(self._steps)

    async def _evaluate(self, app, steps: list[SetupStep]) -> list[SetupStep]:
        """Return which of *steps* are not yet satisfied.

        A step whose predicate raises counts as *complete*. That direction is
        deliberate: a transient database error must not lock a working install
        behind a setup wizard that would then let an anonymous visitor create
        an administrator. Failing closed here would be failing open on
        security.
        """
        pending: list[SetupStep] = []
        for step in steps:
            try:
                done = await step.is_complete(app)
            except Exception:
                continue
            if not done:
                pending.append(step)
        return pending

    async def incomplete(self, app) -> list[SetupStep]:
        """Return the required steps that are not yet satisfied — the gate."""
        return await self._evaluate(app, self.required_steps)

    async def incomplete_all(self, app) -> list[SetupStep]:
        """Return every unsatisfied step, optional ones included.

        What the wizard displays, as opposed to what the gate acts on. Using
        :meth:`incomplete` for the display would report every ``required=False``
        step as done no matter its predicate, since that list never contains
        them.
        """
        return await self._evaluate(app, self.all_steps)

    async def is_setup_complete(self, app) -> bool:
        return not await self.incomplete(app)
