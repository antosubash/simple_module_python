"""Parsing and git-side resolution for ``smpy add`` / ``smpy update``.

A git module source is a normal named dependency plus a ``[tool.uv.sources]``
redirect. This module owns everything before the host pyproject is written:
parsing the spec string, classifying ``@ref`` against the remote, shallow
cloning for metadata, and scanning a clone for module packages.

Stdlib + the ``git`` binary only: the CLI distribution depends on typer +
tomlkit alone (see test_no_framework_deps.py); clones are read with tomllib.
"""

from __future__ import annotations

import subprocess
import tomllib
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from pathlib import Path
from typing import Literal

__all__ = [
    "FoundModule",
    "GitAddSpec",
    "ParsedSpec",
    "RefInfo",
    "SpecError",
    "classify_ref",
    "derive_range",
    "list_remote_refs",
    "parse_add_spec",
    "pick_latest_tag",
    "satisfies",
    "scan_modules",
    "shallow_clone",
    "version_tuple",
]

GitRunner = Callable[..., str]


class SpecError(ValueError):
    """Malformed or unsupported `smpy add` spec."""


@dataclass(frozen=True)
class GitAddSpec:
    url: str
    ref: str | None
    subdirectory: str | None


@dataclass(frozen=True)
class ParsedSpec:
    kind: Literal["pypi", "git", "path"]
    raw: str
    git: GitAddSpec | None = None
    path: Path | None = None


def parse_add_spec(spec: str) -> ParsedSpec:
    raw = spec.strip()
    if not raw:
        raise SpecError("empty spec")
    if raw.startswith("git+"):
        return ParsedSpec("git", raw, git=_parse_git(raw))
    if raw.startswith((".", "/", "~")):
        return ParsedSpec("path", raw, path=Path(raw).expanduser())
    if "://" in raw:
        raise SpecError(f"unsupported URL {raw!r}: git sources must start with git+")
    return ParsedSpec("pypi", raw)


def _parse_git(raw: str) -> GitAddSpec:
    body = raw[len("git+") :]
    subdirectory: str | None = None
    if "#" in body:
        body, fragment = body.split("#", 1)
        for part in fragment.split("&"):
            if part.startswith("subdirectory="):
                subdirectory = part[len("subdirectory=") :] or None
            elif part:
                raise SpecError(
                    f"unsupported fragment {part!r}: only subdirectory=<dir> is understood"
                )
    ref: str | None = None
    head, sep, tail = body.rpartition("@")
    # `@` also appears in URL userinfo (ssh://git@host/...). A ref candidate
    # never contains "/" and what precedes it must still be a full URL.
    if sep and tail and "/" not in tail and "://" in head:
        body, ref = head, tail
    if "://" not in body:
        raise SpecError(f"cannot parse a git URL out of {raw!r}")
    return GitAddSpec(url=body, ref=ref, subdirectory=subdirectory)


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
    return (ta > tb) - (ta < tb)


_OPS = ("<=", ">=", "==", "!=", "<", ">")


def satisfies(version: str, constraint: str) -> bool:
    for clause in constraint.split(","):
        clause = clause.strip()
        if not clause:
            continue
        for op in _OPS:
            if clause.startswith(op):
                bound = clause[len(op) :].strip()
                c = _cmp(version, bound)
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
