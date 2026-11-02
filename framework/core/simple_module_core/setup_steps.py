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

# Takes ``(request, data)`` — the Starlette request and the submitted form as a
# dict — and returns a JSON-able dict (or ``None``). Typed loosely so core does
# not depend on Starlette; the wizard in ``simple_module_hosting`` calls it.
SetupActionFn = Callable[..., Awaitable[dict | None]]


@dataclass
class SetupField:
    """One input the wizard renders for a :class:`SetupAction`.

    ``label`` reaches the page as backend data, so it is resolved server-side
    through ``label_key`` with the literal as the fallback — the same rule as
    ``SetupStep.title``.
    """

    name: str
    label: str
    label_key: str = ""
    type: str = "text"
    """The HTML input type: ``text``, ``email``, ``password``, ..."""
    required: bool = True
    autocomplete: str = ""
    min_length: int | None = None


@dataclass
class SetupAction:
    """How the wizard lets an operator complete a step from the browser.

    The wizard renders ``fields`` as a form and POSTs it as JSON to
    ``/setup/steps/<step id>``, which calls ``handler(request, data)``.

    The wizard only calls the handler while **this step** reports incomplete,
    never merely while "setup mode" is on: an install whose schema falls behind
    head re-enters setup mode with its administrators intact, and an action
    gated on the weaker condition would let an anonymous request perform it
    there. The handler still owns its own race: two requests can both pass that
    check, so a handler that creates something unique must re-check inside the
    transaction that creates it.

    A step without an action can only be completed out of band (a CLI, an
    environment variable); the host logs such steps at boot.
    """

    handler: SetupActionFn
    fields: list[SetupField] = field(default_factory=list)
    submit_label: str = "Continue"
    submit_label_key: str = ""


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
    action: SetupAction | None = None
    """How the wizard completes this step; ``None`` for out-of-band steps."""
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

    def get(self, step_id: str) -> SetupStep | None:
        """The step registered under *step_id*, or ``None``."""
        return next((s for s in self._steps if s.id == step_id), None)

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

    async def is_pending(self, app, step: SetupStep) -> bool:
        """Whether *step* specifically is still unsatisfied.

        Same fail-safe as :meth:`incomplete`: a raising predicate counts as
        complete, so a database hiccup closes a step's action rather than
        opening it.
        """
        return bool(await self._evaluate(app, [step]))

    async def is_setup_complete(self, app) -> bool:
        return not await self.incomplete(app)
