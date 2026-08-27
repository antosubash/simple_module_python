"""PEP 508 requirement rewriting for ``smpy package-update``.

Split out of ``package_update`` so the version-bump rules live in one place
with their own tests, and so neither file approaches the 300-line cap.

The rule that matters: bumping a dependency changes its *version*, not its
*pin style*. ``simple_module_core==0.0.32`` becomes ``==0.0.33``, not
``>=0.0.33`` — a host that pins exactly has made a deliberate choice, and the
published module wheels pin exactly too, so loosening the host leaves the
effective version decided by whichever wheel pins hardest. ``--loosen``
restores the old blanket ``>=`` rewrite for anyone who wants it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

__all__ = ["ParsedRequirement", "RewriteResult", "parse_requirement", "rewrite_requirement"]

# Longest-first: ``===`` must win over ``==``, and ``>=`` over ``>``.
_OPS = ("===", "==", "~=", "!=", ">=", "<=", ">", "<")
_CLAUSE_RE = re.compile(rf"\s*({'|'.join(re.escape(op) for op in _OPS)})\s*([^,]+)")

#: Operators naming a plain floor the bump should raise. ``>`` is deliberately
#: absent: ``>0.0.31`` is already satisfied by anything newer, and rewriting it
#: to ``>0.0.33`` would exclude the very version being installed. ``~=`` is
#: absent too — it carries an implicit ceiling, handled separately below.
_FLOOR_OPS = frozenset({"==", "===", ">="})

#: Suffix marking a PEP 440 wildcard (``==1.4.*``, ``!=1.0.*``). These match on
#: a *prefix* of the release segments, so they must never go through the
#: numeric comparison — ``version_key`` maps ``*`` to 0, which would read
#: ``1.0.*`` as ``1.0.0`` and quietly answer the wrong question.
_WILDCARD = ".*"


@dataclass(frozen=True)
class ParsedRequirement:
    """A PEP 508 requirement split into the parts the rewrite cares about."""

    name: str
    #: Extras bracket including the brackets (``"[redis]"``), or ``""``.
    extras: str
    #: ``(operator, version)`` pairs in source order.
    clauses: tuple[tuple[str, str], ...]
    #: Environment marker including the leading ``;``, or ``""``.
    marker: str


@dataclass(frozen=True)
class RewriteResult:
    """Outcome of a rewrite: a new spec, or a reason there isn't one."""

    #: The rewritten requirement, or ``None`` when nothing should change.
    spec: str | None
    #: Human-readable reason when ``spec`` is ``None`` and the user should be
    #: told (an excluded latest); ``None`` when the no-op is unremarkable.
    reason: str | None = None


def version_key(version: str) -> tuple[int, ...]:
    """Coarse PEP 440 release-segment ordering.

    ``packaging`` isn't a CLI dependency (see ``test_no_framework_deps.py``),
    so this compares the numeric release segments only. Good enough to answer
    "does the latest release trip this upper bound", which is all it's for.
    """
    parts: list[int] = []
    for part in version.split("."):
        digits = re.match(r"\d+", part)
        parts.append(int(digits.group()) if digits else 0)
    return tuple(parts)


def _compare(left: str, right: str) -> int:
    """Three-way compare two versions on their release segments, zero-padded."""
    a, b = version_key(left), version_key(right)
    width = max(len(a), len(b))
    a += (0,) * (width - len(a))
    b += (0,) * (width - len(b))
    return (a > b) - (a < b)


def parse_requirement(spec: str) -> ParsedRequirement | None:
    """Split a PEP 508 requirement string, or ``None`` if the name is unusable."""
    base, sep, marker = spec.partition(";")
    base = base.strip()
    marker = f";{marker}" if sep else ""

    head, bracket, rest = base.partition("[")
    if bracket:
        extras_body, closed, tail = rest.partition("]")
        if not closed:
            return None
        extras = f"[{extras_body}]"
        remainder = tail
    else:
        extras = ""
        # No extras: the name runs until the first operator character.
        match = re.match(r"[^<>=!~]*", head)
        name_end = match.end() if match else 0
        head, remainder = head[:name_end], head[name_end:]

    name = head.strip()
    if not name:
        return None

    clauses = tuple((op, version.strip()) for op, version in _CLAUSE_RE.findall(remainder))
    return ParsedRequirement(name=name, extras=extras, clauses=clauses, marker=marker)


def _render(parsed: ParsedRequirement, clauses: tuple[tuple[str, str], ...]) -> str:
    body = ",".join(f"{op}{version}" for op, version in clauses)
    return f"{parsed.name}{parsed.extras}{body}{parsed.marker}"


def _matches_wildcard(version: str, pattern: str) -> bool:
    """Does ``version`` fall under a PEP 440 wildcard like ``1.4.*``?"""
    prefix = version_key(pattern[: -len(_WILDCARD)])
    release = version_key(version)
    return len(release) >= len(prefix) and release[: len(prefix)] == prefix


def _compatible_band(version: str) -> str | None:
    """The wildcard a ``~=`` clause implies, or ``None`` if it has none.

    ``~=1.4`` means ``>=1.4, ==1.*``; ``~=1.4.2`` means ``>=1.4.2, ==1.4.*``.
    A single-segment ``~=1`` is invalid PEP 440 and has no band to derive.
    """
    parts = version.split(".")
    if len(parts) < 2:
        return None
    return ".".join(parts[:-1]) + _WILDCARD


def _allows(op: str, version: str, latest: str) -> bool:
    """Would this clause still be satisfied by ``latest``?

    Floors (``==``/``===``/``>=``) are always "allowed": the rewrite moves them
    *to* ``latest``, so they can't exclude it. Everything else either carries a
    ceiling of its own or is left verbatim, and has to be checked.
    """
    if op in _FLOOR_OPS and not version.endswith(_WILDCARD):
        return True
    if version.endswith(_WILDCARD):
        # ``==1.0.*`` allows anything under the prefix; ``!=1.0.*`` allows
        # anything outside it.
        inside = _matches_wildcard(latest, version)
        return inside if op in ("==", "===") else not inside
    if op == "~=":
        band = _compatible_band(version)
        return band is not None and _matches_wildcard(latest, band)
    cmp = _compare(latest, version)
    if op == "<":
        return cmp < 0
    if op == "<=":
        return cmp <= 0
    if op == "!=":
        return cmp != 0
    # ``>`` — already satisfied by anything newer than the pin.
    return True


def _excluded_by(parsed: ParsedRequirement, latest: str) -> str | None:
    """Return the clause that rules ``latest`` out, or ``None`` if it's allowed."""
    for op, version in parsed.clauses:
        if not _allows(op, version, latest):
            return f"{op}{version}"
    return None


def _bump(op: str, version: str, latest: str) -> str:
    """The version this clause should carry after the update.

    Only a plain floor moves. A wildcard band (``==1.0.*``, ``!=1.0.*``) that
    already allows ``latest`` is left exactly as written — narrowing it to a
    single release would be a policy change, not a version bump. ``~=`` does
    move, but only because ``_allows`` has already established that ``latest``
    is inside its compatible band.
    """
    if version.endswith(_WILDCARD):
        return version
    if op in _FLOOR_OPS or op == "~=":
        return latest
    return version


def rewrite_requirement(spec: str, latest: str, *, loosen: bool = False) -> RewriteResult:
    """Point ``spec`` at ``latest``, preserving its pin style unless ``loosen``.

    Returns a ``RewriteResult`` whose ``spec`` is ``None`` when the requirement
    already asks for ``latest``, when it carries no floor to raise, or when an
    upper bound excludes ``latest`` (the last carries a ``reason``).
    """
    parsed = parse_requirement(spec)
    if parsed is None:
        return RewriteResult(None)

    if loosen or not parsed.clauses:
        # Nothing to preserve — an unconstrained dependency has no pin style,
        # so it gets the tool's default floor. Extras and markers survive.
        new = f"{parsed.name}{parsed.extras}>={latest}{parsed.marker}"
        return RewriteResult(None) if new == spec.strip() else RewriteResult(new)

    blocker = _excluded_by(parsed, latest)
    if blocker is not None:
        return RewriteResult(None, reason=f"{latest} excluded by {blocker}")

    bumped = tuple((op, _bump(op, version, latest)) for op, version in parsed.clauses)
    if bumped == parsed.clauses:
        # Nothing here names a floor to raise — a bare ``>``/``<``/``!=``, or a
        # wildcard band that already covers ``latest``. Rewriting either would
        # invent a constraint the author didn't ask for.
        return RewriteResult(None)

    new = _render(parsed, bumped)
    return RewriteResult(None) if new == spec.strip() else RewriteResult(new)
