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

#: Operators naming a floor the bump should raise. ``>`` is deliberately absent:
#: ``>0.0.31`` is already satisfied by anything newer, and rewriting it to
#: ``>0.0.33`` would exclude the very version being installed.
_FLOOR_OPS = frozenset({"==", "===", "~=", ">="})

#: Operators that can exclude the latest release. Kept verbatim; if the latest
#: version trips one, the dependency is skipped rather than silently loosened.
_CEILING_OPS = frozenset({"<", "<=", "!="})


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


def _excluded_by(parsed: ParsedRequirement, latest: str) -> str | None:
    """Return the clause that rules ``latest`` out, or ``None`` if it's allowed."""
    for op, version in parsed.clauses:
        if op not in _CEILING_OPS:
            continue
        cmp = _compare(latest, version)
        if (op == "<" and cmp >= 0) or (op == "<=" and cmp > 0) or (op == "!=" and cmp == 0):
            return f"{op}{version}"
    return None


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

    bumped = tuple(
        (op, latest) if op in _FLOOR_OPS else (op, version) for op, version in parsed.clauses
    )
    if bumped == parsed.clauses:
        # Only ``>``/``<``/``!=`` clauses: already satisfied by anything newer,
        # so raising a floor here would be inventing a constraint.
        return RewriteResult(None)

    new = _render(parsed, bumped)
    return RewriteResult(None) if new == spec.strip() else RewriteResult(new)
