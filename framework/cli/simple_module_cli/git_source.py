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


# --- remote resolution + clone scanning ---


@dataclass(frozen=True)
class RefInfo:
    kind: Literal["tag", "branch", "rev", "default"]
    value: str | None


@dataclass(frozen=True)
class FoundModule:
    dist_name: str
    version: str
    subdirectory: str | None
    ships_models: bool
    framework_range: str | None


def _default_git_runner(args: list[str], cwd: Path | None = None) -> str:
    result = subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True, text=True)
    return result.stdout


def list_remote_refs(
    url: str, *, run: GitRunner = _default_git_runner
) -> tuple[set[str], set[str]]:
    out = run(["ls-remote", "--tags", "--heads", url])
    tags: set[str] = set()
    branches: set[str] = set()
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) != 2:
            continue
        ref = parts[1].removesuffix("^{}")
        if ref.startswith("refs/tags/"):
            tags.add(ref.removeprefix("refs/tags/"))
        elif ref.startswith("refs/heads/"):
            branches.add(ref.removeprefix("refs/heads/"))
    return tags, branches


def classify_ref(url: str, ref: str | None, *, run: GitRunner = _default_git_runner) -> RefInfo:
    if ref is None:
        return RefInfo("default", None)
    tags, branches = list_remote_refs(url, run=run)
    if ref in tags:
        return RefInfo("tag", ref)
    if ref in branches:
        return RefInfo("branch", ref)
    return RefInfo("rev", ref)


def shallow_clone(
    url: str, ref_info: RefInfo, dest: Path, *, run: GitRunner = _default_git_runner
) -> Path:
    dest.parent.mkdir(parents=True, exist_ok=True)
    base = ["clone", "--depth", "1", "--quiet"]
    if ref_info.kind in ("tag", "branch") and ref_info.value:
        run([*base, "--branch", ref_info.value, url, str(dest)])
    elif ref_info.kind == "rev" and ref_info.value:
        # --branch can't take a SHA; fetch the rev into a fresh clone instead.
        run([*base, url, str(dest)])
        run(["fetch", "--depth", "1", "origin", ref_info.value], cwd=dest)
        run(["checkout", "--quiet", "FETCH_HEAD"], cwd=dest)
    else:
        run([*base, url, str(dest)])
    return dest


_SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}


def _framework_range(deps: list[str]) -> str | None:
    for dep in deps:
        text = str(dep).strip()
        if text.replace("-", "_").startswith("simple_module_core"):
            for i, ch in enumerate(text):
                if ch in "<>=!~":
                    return text[i:].strip()
    return None


def scan_modules(repo_root: Path) -> list[FoundModule]:
    """Find every package in the clone declaring the simple_module entry point."""
    candidates: list[Path] = []
    for pattern in ("pyproject.toml", "*/pyproject.toml", "*/*/pyproject.toml"):
        candidates.extend(sorted(repo_root.glob(pattern)))
    found: list[FoundModule] = []
    for pyproject in candidates:
        rel_parts = pyproject.relative_to(repo_root).parts
        if any(part in _SKIP_DIRS for part in rel_parts):
            continue
        try:
            data = tomllib.loads(pyproject.read_text(encoding="utf-8"))
        except (OSError, tomllib.TOMLDecodeError):
            continue
        project = data.get("project") or {}
        entry_points = project.get("entry-points") or {}
        if "simple_module" not in entry_points or "name" not in project:
            continue
        pkg_root = pyproject.parent
        subdirectory = None if pkg_root == repo_root else "/".join(rel_parts[:-1])
        ships_models = any(
            not any(part in _SKIP_DIRS for part in p.relative_to(pkg_root).parts)
            for p in pkg_root.glob("*/models.py")
        )
        found.append(
            FoundModule(
                dist_name=str(project["name"]),
                version=str(project.get("version", "0")),
                subdirectory=subdirectory,
                ships_models=ships_models,
                framework_range=_framework_range(project.get("dependencies") or []),
            )
        )
    return found
