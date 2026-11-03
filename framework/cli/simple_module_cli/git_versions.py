"""Version policies and release-tag selection for git module sources."""

from __future__ import annotations

import re
from collections.abc import Iterable

from simple_module_cli.requirements import _compatible_band, _matches_wildcard

# --- version helpers (no `packaging` dep — CLI depends on typer + tomlkit only) ---


def version_tuple(v: str) -> tuple[int, ...]:
    parts: list[int] = []
    for part in v.split("."):
        digits = ""
        for ch in part:
            if ch.isdigit():
                digits += ch
            else:
                break
        parts.append(int(digits) if digits else 0)
    return tuple(parts)


def _cmp(a: str, b: str) -> int:
    ta, tb = version_tuple(a), version_tuple(b)
    width = max(len(ta), len(tb))
    ta += (0,) * (width - len(ta))
    tb += (0,) * (width - len(tb))
    if ta != tb:
        return (ta > tb) - (ta < tb)
    pa, pb = _prerelease_key(a), _prerelease_key(b)
    return (pa > pb) - (pa < pb)


def _prerelease_key(version: str) -> tuple[int, int]:
    # shortcut: handles Python a/b/rc suffixes; use a full parser for other version schemes.
    match = re.search(r"(alpha|beta|a|b|rc)(\d*)$", version, re.IGNORECASE)
    if match is None:
        return (3, 0)
    return (
        {"a": 0, "alpha": 0, "b": 1, "beta": 1, "rc": 2}[match[1].lower()],
        int(match[2] or "0"),
    )


_OPS = ("<=", ">=", "==", "!=", "~=", "<", ">")


def satisfies(version: str, constraint: str) -> bool:
    for clause in constraint.split(","):
        clause = clause.strip()
        if not clause:
            continue
        for op in _OPS:
            if clause.startswith(op):
                bound = clause[len(op) :].strip()
                if op in ("==", "!=") and bound.endswith(".*"):
                    if (op == "==") != _matches_wildcard(version, bound):
                        return False
                    break
                if op == "<" and _excluded_prerelease(version, bound):
                    return False
                c = _cmp(version, bound)
                if op == "~=":
                    band = _compatible_band(bound)
                    if c < 0 or band is None or not _matches_wildcard(version, band):
                        return False
                    break
                ok = {
                    "<=": c <= 0,
                    ">=": c >= 0,
                    "==": c == 0,
                    "!=": c != 0,
                    "<": c < 0,
                    ">": c > 0,
                }[op]
                if not ok:
                    return False
                break
        else:
            return False
    return True


def _excluded_prerelease(version: str, bound: str) -> bool:
    """PEP 440: ``<0.4`` excludes ``0.4.0rc1`` unless the bound is itself a pre-release."""
    final = (3, 0)
    if _prerelease_key(version) == final or _prerelease_key(bound) != final:
        return False
    width = max(len(version_tuple(version)), len(version_tuple(bound)))
    pad = (0,) * width
    return (version_tuple(version) + pad)[:width] == (version_tuple(bound) + pad)[:width]


def derive_range(version: str) -> str:
    major = version_tuple(version)[0]
    upper = "1.0" if major == 0 else f"{major + 1}.0"
    return f">={version},<{upper}"


def pick_latest_tag(tags: Iterable[str], constraint: str | None) -> str | None:
    best: str | None = None
    for tag in tags:
        if not tag.startswith("v") or len(tag) < 2 or not tag[1].isdigit():
            continue
        ver = tag[1:]
        if constraint and not satisfies(ver, constraint):
            continue
        if best is None or _cmp(ver, best[1:]) > 0:
            best = tag
    return best
