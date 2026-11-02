# Git Module Sources Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** `smpy add <spec>` and `smpy update` make any git repo (and local path) a first-class module source alongside PyPI, via `[tool.uv.sources]`, including multi-module repos and wizard/create-host integration.

**Architecture:** Four new files in `framework/cli/simple_module_cli/`: `git_source.py` (spec parsing, remote-ref classification, shallow clone, repo scan, version helpers), `pyproject_edit.py` (tomlkit write helpers), `add_cmd.py` (the `smpy add` command + post-install pipeline), `update_cmd.py` (the `smpy update` command). `wizard.py`/`new.py`/`cli.py` gain a repeatable `--git-module` path. All subprocess side effects (`uv`, `npm`) go through an injectable `exec_runner`; git operations through an injectable `git_runner` so tests use local fixture repos, never the network.

**Tech Stack:** Python 3.12, Typer, tomlkit (writes), stdlib `tomllib` (reads), `git` binary via subprocess, pytest + `typer.testing.CliRunner`.

**Spec:** `docs/superpowers/specs/2026-08-19-git-module-sources-design.md`

## Global Constraints

- `simple_module_cli` runtime deps are exactly `{typer, tomlkit}` — enforced by `framework/cli/tests/test_no_framework_deps.py`. No `packaging`, no `GitPython`. Read clone metadata with stdlib `tomllib`.
- 300-line cap on every `.py` file (`scripts/check_file_size.py`).
- Test basenames must be globally unique across the repo (no `__init__.py` in test dirs) — all new test files are prefixed `test_cli_`.
- No network in tests. Git fixtures are local repos in `tmp_path`, cloned via `file://` URIs (real `git` binary is available and offline).
- Run tests from repo root: `uv run pytest framework/cli/tests/<file>.py -v`.
- Lint gate: `uv run ruff format <files>` then `make lint` at the end.
- Versioning convention (spec §3): repo-wide lockstep `v*` tags; all modules from one repo share one pinned ref; updates move them as a group.
- Nothing is written to the host `pyproject.toml` until git resolution succeeds (spec §6).

---

### Task 1: Spec parsing + version helpers (`git_source.py`, part 1)

**Files:**
- Create: `framework/cli/simple_module_cli/git_source.py`
- Test: `framework/cli/tests/test_cli_add_spec_parse.py`

**Interfaces:**
- Produces: `SpecError(ValueError)`; `GitAddSpec(url, ref, subdirectory)`; `ParsedSpec(kind: Literal["pypi","git","path"], raw, git: GitAddSpec|None, path: Path|None)`; `parse_add_spec(spec: str) -> ParsedSpec`; `version_tuple(v: str) -> tuple[int,...]`; `satisfies(version: str, constraint: str) -> bool`; `derive_range(version: str) -> str`; `pick_latest_tag(tags: Iterable[str], constraint: str | None) -> str | None`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for `smpy add` spec parsing and version helpers."""

from __future__ import annotations

import pytest
from simple_module_cli.git_source import (
    SpecError,
    derive_range,
    parse_add_spec,
    pick_latest_tag,
    satisfies,
    version_tuple,
)


def test_pypi_spec_passthrough() -> None:
    p = parse_add_spec("simple_module_blog>=1.2,<2.0")
    assert p.kind == "pypi"
    assert p.raw == "simple_module_blog>=1.2,<2.0"


def test_git_spec_plain() -> None:
    p = parse_add_spec("git+https://github.com/x/repo")
    assert p.kind == "git"
    assert p.git is not None
    assert p.git.url == "https://github.com/x/repo"
    assert p.git.ref is None
    assert p.git.subdirectory is None


def test_git_spec_with_ref_and_subdirectory() -> None:
    p = parse_add_spec("git+https://github.com/x/repo@v1.2.0#subdirectory=modules/blog")
    assert p.git is not None
    assert p.git.url == "https://github.com/x/repo"
    assert p.git.ref == "v1.2.0"
    assert p.git.subdirectory == "modules/blog"


def test_git_ssh_userinfo_at_is_not_a_ref() -> None:
    p = parse_add_spec("git+ssh://git@github.com/x/repo")
    assert p.git is not None
    assert p.git.url == "ssh://git@github.com/x/repo"
    assert p.git.ref is None


def test_git_ssh_userinfo_with_ref() -> None:
    p = parse_add_spec("git+ssh://git@github.com/x/repo@main")
    assert p.git is not None
    assert p.git.url == "ssh://git@github.com/x/repo"
    assert p.git.ref == "main"


def test_path_spec() -> None:
    p = parse_add_spec("../mod")
    assert p.kind == "path"


def test_bare_https_url_rejected_with_hint() -> None:
    with pytest.raises(SpecError, match="git\\+"):
        parse_add_spec("https://github.com/x/repo")


def test_unknown_fragment_rejected() -> None:
    with pytest.raises(SpecError, match="subdirectory"):
        parse_add_spec("git+https://github.com/x/repo#egg=foo")


def test_empty_spec_rejected() -> None:
    with pytest.raises(SpecError):
        parse_add_spec("   ")


def test_version_tuple_and_satisfies() -> None:
    assert version_tuple("1.2.3") == (1, 2, 3)
    assert satisfies("1.2.3", ">=1.2,<2.0")
    assert not satisfies("2.0.0", ">=1.2,<2.0")
    assert satisfies("1.2", ">=1.2.0")  # padded comparison
    assert not satisfies("1.2.3", "!=1.2.3")
    assert satisfies("0.5.0", "<1.0")


def test_derive_range() -> None:
    assert derive_range("0.3.2") == ">=0.3.2,<1.0"
    assert derive_range("1.4.0") == ">=1.4.0,<2.0"


def test_pick_latest_tag() -> None:
    tags = ["v0.1.0", "v1.2.0", "v1.10.0", "v2.0.0", "not-a-version", "release-3"]
    assert pick_latest_tag(tags, ">=1.0,<2.0") == "v1.10.0"
    assert pick_latest_tag(tags, None) == "v2.0.0"
    assert pick_latest_tag(["nope"], None) is None
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/cli/tests/test_cli_add_spec_parse.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'simple_module_cli.git_source'`

- [ ] **Step 3: Implement**

```python
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


# --- version helpers (no `packaging` dep — see Global Constraints) ---


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
```

(Leave room in this file — Task 2 appends the git operations and scan below these helpers.)

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_cli_add_spec_parse.py -v`
Expected: PASS (all)

- [ ] **Step 5: Format + commit**

```bash
uv run ruff format framework/cli/simple_module_cli/git_source.py framework/cli/tests/test_cli_add_spec_parse.py
git add framework/cli/simple_module_cli/git_source.py framework/cli/tests/test_cli_add_spec_parse.py
git commit -m "feat(cli): add-spec parsing and version helpers for git module sources"
```

---

### Task 2: Remote-ref classification, shallow clone, repo scan (`git_source.py`, part 2)

**Files:**
- Modify: `framework/cli/simple_module_cli/git_source.py` (append)
- Create: `framework/cli/tests/conftest.py` (fixture factory for local git module repos) — check first: if a conftest already exists there, add the fixture to it instead
- Test: `framework/cli/tests/test_cli_git_scan.py`

**Interfaces:**
- Consumes: `version_tuple` etc. from Task 1.
- Produces: `RefInfo(kind: Literal["tag","branch","rev","default"], value: str|None)`; `list_remote_refs(url, *, run) -> tuple[set[str], set[str]]` (tags, branches); `classify_ref(url, ref, *, run) -> RefInfo`; `shallow_clone(url, ref_info: RefInfo, dest: Path, *, run) -> Path`; `FoundModule(dist_name, version, subdirectory, ships_models, framework_range)`; `scan_modules(repo_root: Path) -> list[FoundModule]`. Also the pytest fixture `make_git_module_repo` (factory) in conftest.

- [ ] **Step 1: Write the conftest fixture factory**

```python
"""Shared fixtures for simple_module_cli tests."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


def _git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", *args],
        cwd=repo,
        check=True,
        capture_output=True,
        env={
            "GIT_AUTHOR_NAME": "t",
            "GIT_AUTHOR_EMAIL": "t@t",
            "GIT_COMMITTER_NAME": "t",
            "GIT_COMMITTER_EMAIL": "t@t",
            "HOME": str(repo),
            "GIT_CONFIG_GLOBAL": "/dev/null",
            "GIT_CONFIG_SYSTEM": "/dev/null",
        },
    )


def _write_module_pkg(root: Path, dist_name: str, version: str, *, models: bool) -> None:
    pkg = dist_name.replace("-", "_")
    (root / pkg).mkdir(parents=True)
    (root / pkg / "__init__.py").write_text("", encoding="utf-8")
    (root / pkg / "module.py").write_text("class M:\n    pass\n", encoding="utf-8")
    if models:
        (root / pkg / "models.py").write_text("# tables\n", encoding="utf-8")
    (root / "pyproject.toml").write_text(
        f'[project]\nname = "{dist_name}"\nversion = "{version}"\n'
        f'dependencies = ["simple_module_core>=0.1,<1.0"]\n\n'
        f"[project.entry-points.simple_module]\n"
        f'{pkg} = "{pkg}.module:M"\n',
        encoding="utf-8",
    )


@pytest.fixture
def make_git_module_repo(tmp_path: Path):
    """Factory: build a local git repo holding one or more module packages.

    modules: list of (dist_name, version, subdir_or_None, ships_models).
    tags: git tags to create at HEAD. Returns the repo path (use .as_uri()
    prefixed with git+ for specs).
    """

    counter = {"n": 0}

    def factory(
        modules: list[tuple[str, str, str | None, bool]],
        *,
        tags: list[str] | None = None,
        extra_pyproject_dirs: list[str] | None = None,
    ) -> Path:
        counter["n"] += 1
        repo = tmp_path / f"repo{counter['n']}"
        repo.mkdir()
        for dist_name, version, subdir, models in modules:
            root = repo / subdir if subdir else repo
            root.mkdir(parents=True, exist_ok=True)
            _write_module_pkg(root, dist_name, version, models=models)
        for d in extra_pyproject_dirs or []:
            (repo / d).mkdir(parents=True, exist_ok=True)
            (repo / d / "pyproject.toml").write_text(
                '[project]\nname = "not-a-module"\nversion = "0"\n', encoding="utf-8"
            )
        _git(repo, "init", "-q", "-b", "main")
        _git(repo, "add", ".")
        _git(repo, "commit", "-q", "-m", "init")
        for tag in tags or []:
            _git(repo, "tag", tag)
        return repo

    return factory
```

- [ ] **Step 2: Write the failing tests**

```python
"""Tests for git-side resolution: ref classification, shallow clone, repo scan."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.git_source import (
    RefInfo,
    classify_ref,
    list_remote_refs,
    scan_modules,
    shallow_clone,
)


def _uri(repo: Path) -> str:
    return repo.as_uri()


class TestRefs:
    def test_list_remote_refs(self, make_git_module_repo) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        tags, branches = list_remote_refs(_uri(repo))
        assert "v0.1.0" in tags
        assert "main" in branches

    def test_classify_tag_branch_rev_default(self, make_git_module_repo) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        url = _uri(repo)
        assert classify_ref(url, None) == RefInfo("default", None)
        assert classify_ref(url, "v0.1.0") == RefInfo("tag", "v0.1.0")
        assert classify_ref(url, "main") == RefInfo("branch", "main")
        assert classify_ref(url, "0123abc") == RefInfo("rev", "0123abc")


class TestCloneAndScan:
    def test_clone_default_and_scan_single(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, True)])
        dest = tmp_path / "clone1"
        shallow_clone(_uri(repo), RefInfo("default", None), dest)
        found = scan_modules(dest)
        assert len(found) == 1
        mod = found[0]
        assert mod.dist_name == "simple_module_blog"
        assert mod.version == "0.2.0"
        assert mod.subdirectory is None
        assert mod.ships_models is True
        assert mod.framework_range == ">=0.1,<1.0"

    def test_clone_at_tag(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)], tags=["v0.1.0"])
        dest = tmp_path / "clone2"
        shallow_clone(_uri(repo), RefInfo("tag", "v0.1.0"), dest)
        assert (dest / "pyproject.toml").is_file()

    def test_scan_multi_module_repo(self, make_git_module_repo, tmp_path) -> None:
        repo = make_git_module_repo(
            [
                ("simple_module_blog", "0.1.0", "modules/blog", False),
                ("simple_module_comments", "0.1.0", "modules/comments", True),
            ],
            extra_pyproject_dirs=["tools/scripts"],
        )
        dest = tmp_path / "clone3"
        shallow_clone(_uri(repo), RefInfo("default", None), dest)
        found = scan_modules(dest)
        names = {m.dist_name: m for m in found}
        assert set(names) == {"simple_module_blog", "simple_module_comments"}
        assert names["simple_module_blog"].subdirectory == "modules/blog"
        assert names["simple_module_comments"].ships_models is True
```

- [ ] **Step 3: Run tests to verify they fail**

Run: `uv run pytest framework/cli/tests/test_cli_git_scan.py -v`
Expected: FAIL — `ImportError: cannot import name 'RefInfo'`

- [ ] **Step 4: Append the implementation to `git_source.py`**

```python
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
            p.name == "models.py"
            for p in pkg_root.glob("*/models.py")
            if not any(part in _SKIP_DIRS for part in p.relative_to(pkg_root).parts)
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
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_cli_git_scan.py framework/cli/tests/test_cli_add_spec_parse.py -v`
Expected: PASS. If `shallow_clone` at a tag fails on older git, drop `--depth 1` for `file://` URLs only after confirming the error — but current git supports shallow file:// clones.

- [ ] **Step 6: Confirm the 300-line cap holds**

Run: `wc -l framework/cli/simple_module_cli/git_source.py`
Expected: < 300. If over, move the version helpers (`version_tuple`, `_cmp`, `satisfies`, `derive_range`, `pick_latest_tag`) into a new `framework/cli/simple_module_cli/version_match.py` and re-export them from `git_source` for the tests.

- [ ] **Step 7: Format + commit**

```bash
uv run ruff format framework/cli/simple_module_cli/ framework/cli/tests/
git add framework/cli/simple_module_cli/ framework/cli/tests/conftest.py framework/cli/tests/test_cli_git_scan.py
git commit -m "feat(cli): remote-ref classification, shallow clone, module repo scan"
```

---

### Task 3: Pyproject write helpers (`pyproject_edit.py`)

**Files:**
- Create: `framework/cli/simple_module_cli/pyproject_edit.py`
- Test: `framework/cli/tests/test_cli_pyproject_edit.py`

**Interfaces:**
- Consumes: `RefInfo`, `derive_range` from Tasks 1–2.
- Produces: `load_pyproject(path: Path) -> tomlkit.TOMLDocument`; `save_pyproject(path: Path, doc) -> None`; `has_git_sources(doc) -> bool`; `dep_constraint(doc, dist_name: str) -> str | None`; `write_dependency(doc, dist_name: str, constraint: str) -> bool` (adds or replaces the entry; returns changed); `write_git_source(doc, dist_name: str, *, url: str, ref_info: RefInfo, subdirectory: str | None) -> bool`; `write_path_source(doc, dist_name: str, *, path: str) -> bool`; `git_sources(doc) -> dict[str, dict]` (name → source table for entries with a `git` key).

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for host pyproject.toml editing (deps + [tool.uv.sources])."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.git_source import RefInfo
from simple_module_cli.pyproject_edit import (
    dep_constraint,
    git_sources,
    has_git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
    write_git_source,
    write_path_source,
)

BASE = (
    "# host config\n"
    '[project]\nname = "myhost"\nversion = "0.1.0"\n'
    "dependencies = [\n"
    '    "fastapi>=0.110",  # keep\n'
    '    "simple_module_core>=0.1,<1.0",\n'
    "]\n"
)


def _doc(tmp_path: Path, text: str = BASE):
    p = tmp_path / "pyproject.toml"
    p.write_text(text, encoding="utf-8")
    return p, load_pyproject(p)


def test_write_dependency_adds_and_replaces(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    assert write_dependency(doc, "simple_module_blog", ">=0.2.0,<1.0") is True
    assert write_dependency(doc, "simple_module_blog", ">=0.2.0,<1.0") is False
    assert write_dependency(doc, "simple_module_blog", ">=0.3.0,<1.0") is True
    save_pyproject(p, doc)
    out = p.read_text(encoding="utf-8")
    assert "simple_module_blog>=0.3.0,<1.0" in out
    assert out.count("simple_module_blog") == 1
    assert "# keep" in out  # tomlkit round-trip preserves comments


def test_write_git_source_variants(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_git_source(
        doc,
        "simple_module_blog",
        url="https://github.com/x/repo",
        ref_info=RefInfo("tag", "v0.2.0"),
        subdirectory="modules/blog",
    )
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert "[tool.uv.sources]" in text
    assert 'git = "https://github.com/x/repo"' in text
    assert 'tag = "v0.2.0"' in text
    assert 'subdirectory = "modules/blog"' in text

    _, doc2 = _doc(tmp_path, p.read_text(encoding="utf-8"))
    assert has_git_sources(doc2) is True
    assert "simple_module_blog" in git_sources(doc2)


def test_branch_and_rev_and_default_keys(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_git_source(doc, "a", url="u", ref_info=RefInfo("branch", "main"), subdirectory=None)
    write_git_source(doc, "b", url="u", ref_info=RefInfo("rev", "abc123"), subdirectory=None)
    write_git_source(doc, "c", url="u", ref_info=RefInfo("default", None), subdirectory=None)
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert 'branch = "main"' in text
    assert 'rev = "abc123"' in text
    # default ref → bare git source, no pin key
    assert text.count("tag =") == 0


def test_write_path_source(tmp_path: Path) -> None:
    p, doc = _doc(tmp_path)
    write_path_source(doc, "simple_module_local", path="../local_mod")
    save_pyproject(p, doc)
    text = p.read_text(encoding="utf-8")
    assert 'path = "../local_mod"' in text
    assert "editable = true" in text


def test_dep_constraint_and_no_git_sources(tmp_path: Path) -> None:
    _, doc = _doc(tmp_path)
    assert dep_constraint(doc, "simple_module_core") == ">=0.1,<1.0"
    assert dep_constraint(doc, "absent") is None
    assert has_git_sources(doc) is False
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/cli/tests/test_cli_pyproject_edit.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement**

```python
"""tomlkit edits for a host ``pyproject.toml`` — deps + [tool.uv.sources].

Format-preserving: comments and layout in the host file survive the edit.
Callers write nothing until resolution has succeeded (spec §6): build the
document in memory, then ``save_pyproject`` once.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import tomlkit
from tomlkit.items import Array, Table

from simple_module_cli.git_source import RefInfo

__all__ = [
    "dep_constraint",
    "git_sources",
    "has_git_sources",
    "load_pyproject",
    "save_pyproject",
    "write_dependency",
    "write_git_source",
    "write_path_source",
]


def load_pyproject(path: Path) -> tomlkit.TOMLDocument:
    return tomlkit.parse(path.read_text(encoding="utf-8"))


def save_pyproject(path: Path, doc: tomlkit.TOMLDocument) -> None:
    path.write_text(tomlkit.dumps(doc), encoding="utf-8")


def _dependencies(doc: tomlkit.TOMLDocument) -> Array:
    project = doc.get("project")
    if not isinstance(project, (dict, Table)):
        raise ValueError("pyproject has no [project] table")
    deps = project.get("dependencies")
    if not isinstance(deps, (list, Array)):
        deps = tomlkit.array()
        deps.multiline(True)
        project["dependencies"] = deps
    return deps


def _dep_index(deps: Array, dist_name: str) -> int | None:
    key = dist_name.replace("-", "_").lower()
    for i, raw in enumerate(deps):
        text = str(raw).strip().replace("-", "_").lower()
        head = text
        for sep in ("[", ">", "<", "=", "!", "~", ";", " "):
            head = head.split(sep, 1)[0]
        if head == key:
            return i
    return None


def dep_constraint(doc: tomlkit.TOMLDocument, dist_name: str) -> str | None:
    deps = _dependencies(doc)
    idx = _dep_index(deps, dist_name)
    if idx is None:
        return None
    text = str(deps[idx]).strip()
    for i, ch in enumerate(text):
        if ch in "<>=!~":
            return text[i:].strip()
    return None


def write_dependency(doc: tomlkit.TOMLDocument, dist_name: str, constraint: str) -> bool:
    deps = _dependencies(doc)
    entry = f"{dist_name}{constraint}"
    idx = _dep_index(deps, dist_name)
    if idx is None:
        deps.append(entry)
        return True
    if str(deps[idx]).strip() == entry:
        return False
    deps[idx] = entry
    return True


def _uv_sources(doc: tomlkit.TOMLDocument) -> Table:
    tool = doc.setdefault("tool", tomlkit.table(is_super_table=True))
    uv = tool.setdefault("uv", tomlkit.table(is_super_table=True))
    return uv.setdefault("sources", tomlkit.table())


def write_git_source(
    doc: tomlkit.TOMLDocument,
    dist_name: str,
    *,
    url: str,
    ref_info: RefInfo,
    subdirectory: str | None,
) -> bool:
    src = tomlkit.inline_table()
    src["git"] = url
    if ref_info.kind in ("tag", "branch", "rev") and ref_info.value:
        src[ref_info.kind] = ref_info.value
    if subdirectory:
        src["subdirectory"] = subdirectory
    sources = _uv_sources(doc)
    if dist_name in sources and dict(sources[dist_name]) == dict(src):
        return False
    sources[dist_name] = src
    return True


def write_path_source(doc: tomlkit.TOMLDocument, dist_name: str, *, path: str) -> bool:
    src = tomlkit.inline_table()
    src["path"] = path
    src["editable"] = True
    sources = _uv_sources(doc)
    if dist_name in sources and dict(sources[dist_name]) == dict(src):
        return False
    sources[dist_name] = src
    return True


def _sources_dict(doc: tomlkit.TOMLDocument) -> dict[str, Any]:
    tool = doc.get("tool")
    if not isinstance(tool, dict):
        return {}
    uv = tool.get("uv")
    if not isinstance(uv, dict):
        return {}
    sources = uv.get("sources")
    return dict(sources) if isinstance(sources, dict) else {}


def git_sources(doc: tomlkit.TOMLDocument) -> dict[str, dict]:
    return {
        name: dict(src)
        for name, src in _sources_dict(doc).items()
        if isinstance(src, dict) and "git" in src
    }


def has_git_sources(doc: tomlkit.TOMLDocument) -> bool:
    return bool(git_sources(doc))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_cli_pyproject_edit.py -v`
Expected: PASS. Watch for tomlkit API drift on `setdefault` for super tables — if `tool.uv` lands as `[tool.uv]` header noise, mirror how `app_project._rewrite_pyproject` builds the same block (it already writes `[tool.uv.sources]` for workspace entries) and copy its construction style.

- [ ] **Step 5: Format + commit**

```bash
uv run ruff format framework/cli/simple_module_cli/pyproject_edit.py framework/cli/tests/test_cli_pyproject_edit.py
git add framework/cli/simple_module_cli/pyproject_edit.py framework/cli/tests/test_cli_pyproject_edit.py
git commit -m "feat(cli): format-preserving pyproject edits for module sources"
```

---

### Task 4: `smpy add` command (`add_cmd.py` + registration)

**Files:**
- Create: `framework/cli/simple_module_cli/add_cmd.py`
- Modify: `framework/cli/simple_module_cli/cli.py` (register `add`; extend module docstring's command list)
- Test: `framework/cli/tests/test_cli_add_cmd.py`

**Interfaces:**
- Consumes: everything from Tasks 1–3.
- Produces: `run_add(spec: str, *, pyproject: Path, select: list[str] | None = None, all_modules: bool = False, no_sync: bool = False, assume_yes: bool = False, git_runner=None, exec_runner=None) -> list[str]` (returns dist names added; raises `typer.Exit` on failure); Typer command `add_module` registered as `smpy add`; `post_install(project_dir: Path, dists: list[str], models_dists: list[str], exec_runner) -> None`; `ExecRunner = Callable[[list[str], Path], int]`. Task 5 imports `post_install` and `ExecRunner`; Task 6 imports `run_add`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for `smpy add` — end-to-end against local git fixture repos."""

from __future__ import annotations

from pathlib import Path

import pytest
import typer
from simple_module_cli.add_cmd import run_add

HOST = (
    '[project]\nname = "myhost"\nversion = "0.1.0"\n'
    'dependencies = ["simple_module_core>=0.1,<1.0"]\n'
)


@pytest.fixture
def host_pyproject(tmp_path: Path) -> Path:
    p = tmp_path / "host" / "pyproject.toml"
    p.parent.mkdir()
    p.write_text(HOST, encoding="utf-8")
    return p


def _recorder():
    calls: list[list[str]] = []

    def runner(cmd: list[str], cwd: Path) -> int:
        calls.append(cmd)
        return 0

    return calls, runner


def test_add_single_module_from_git(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, True)], tags=["v0.2.0"])
    calls, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}@v0.2.0",
        pyproject=host_pyproject,
        exec_runner=runner,
    )
    assert added == ["simple_module_blog"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert "simple_module_blog>=0.2.0,<1.0" in text
    assert 'tag = "v0.2.0"' in text
    assert ["uv", "sync"] in calls  # post-install pipeline ran


def test_add_multi_module_select(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        select=["simple_module_comments"],
        exec_runner=runner,
    )
    assert added == ["simple_module_comments"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert 'subdirectory = "modules/comments"' in text
    assert "simple_module_blog" not in text


def test_add_multi_module_all(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    added = run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        all_modules=True,
        exec_runner=runner,
    )
    assert sorted(added) == ["simple_module_blog", "simple_module_comments"]


def test_add_multi_module_without_selection_fails_listing_options(
    make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo(
        [
            ("simple_module_blog", "0.1.0", "modules/blog", False),
            ("simple_module_comments", "0.1.0", "modules/comments", False),
        ]
    )
    _, runner = _recorder()
    with pytest.raises(typer.Exit):
        run_add(
            f"git+{repo.as_uri()}",
            pyproject=host_pyproject,
            assume_yes=True,  # non-interactive, no --module/--all
            exec_runner=runner,
        )
    err = capsys.readouterr().err
    assert "simple_module_blog" in err and "simple_module_comments" in err
    # nothing written on failure
    assert "tool.uv.sources" not in host_pyproject.read_text(encoding="utf-8")


def test_add_repo_without_entry_point_fails_with_hint(
    tmp_path, make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo([], extra_pyproject_dirs=["lib"])
    _, runner = _recorder()
    with pytest.raises(typer.Exit):
        run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    assert "entry-points.simple_module" in capsys.readouterr().err
    assert host_pyproject.read_text(encoding="utf-8") == HOST


def test_first_git_add_prints_security_notice(make_git_module_repo, host_pyproject, capsys) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)])
    _, runner = _recorder()
    run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    out = capsys.readouterr().out
    assert "URL you chose" in out


def test_models_module_prints_migration_reminder(
    make_git_module_repo, host_pyproject, capsys
) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, True)])
    _, runner = _recorder()
    run_add(f"git+{repo.as_uri()}", pyproject=host_pyproject, exec_runner=runner)
    assert "migration" in capsys.readouterr().out.lower()


def test_no_sync_writes_but_skips_pipeline(make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.1.0", None, False)])
    calls, runner = _recorder()
    run_add(
        f"git+{repo.as_uri()}",
        pyproject=host_pyproject,
        no_sync=True,
        exec_runner=runner,
    )
    assert calls == []
    assert "simple_module_blog" in host_pyproject.read_text(encoding="utf-8")


def test_pypi_spec_adds_plain_dependency(host_pyproject) -> None:
    _, runner = _recorder()
    added = run_add(
        "simple_module_dashboard>=0.1,<1.0",
        pyproject=host_pyproject,
        exec_runner=runner,
    )
    assert added == ["simple_module_dashboard"]
    assert "simple_module_dashboard>=0.1,<1.0" in host_pyproject.read_text(encoding="utf-8")


def test_path_spec_adds_editable_source(tmp_path, make_git_module_repo, host_pyproject) -> None:
    repo = make_git_module_repo([("simple_module_local", "0.1.0", None, False)])
    _, runner = _recorder()
    added = run_add(str(repo), pyproject=host_pyproject, exec_runner=runner)
    assert added == ["simple_module_local"]
    text = host_pyproject.read_text(encoding="utf-8")
    assert "editable = true" in text
```

Note: `str(repo)` is an absolute path, so `parse_add_spec` classifies it as `path`; `run_add` scans the directory in place (no clone) and errors if no module package is found at its root.

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/cli/tests/test_cli_add_cmd.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `add_cmd.py`**

```python
"""``smpy add`` — add a module from PyPI, any git repo, or a local path.

Git specs: ``git+<url>[@<tag|branch|sha>][#subdirectory=<dir>]``. The spec
is resolved first (ls-remote + shallow clone + entry-point scan); the host
pyproject is written only after resolution succeeds. A git spec without
``#subdirectory`` is scanned for module packages — one match is added
directly, several go through ``--module``/``--all`` or an interactive
picker. Then: ``uv sync`` → ``smpy host gen-pages`` → ``smpy host
sync-js-deps`` → entry-point verification, unless ``--no-sync``.
"""

from __future__ import annotations

import subprocess
import tempfile
from collections.abc import Callable
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.git_source import (
    FoundModule,
    ParsedSpec,
    classify_ref,
    derive_range,
    parse_add_spec,
    scan_modules,
    shallow_clone,
    SpecError,
)
from simple_module_cli.pyproject_edit import (
    has_git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
    write_git_source,
    write_path_source,
)

__all__ = ["ExecRunner", "add_module", "post_install", "run_add"]

ExecRunner = Callable[[list[str], Path], int]

_SECURITY_NOTICE = (
    "note: this installs and runs code from a URL you chose — review the "
    "repository before booting the host."
)

_ENTRYPOINT_CHECK = (
    "import sys\n"
    "from importlib.metadata import distributions\n"
    "target = sys.argv[1].replace('-', '_').lower()\n"
    "for dist in distributions():\n"
    "    if any(ep.group == 'simple_module' for ep in dist.entry_points):\n"
    "        name = (dist.metadata['Name'] or '').replace('-', '_').lower()\n"
    "        if name == target:\n"
    "            sys.exit(0)\n"
    "sys.exit(1)\n"
)


def _default_exec_runner(cmd: list[str], cwd: Path) -> int:
    return subprocess.run(cmd, cwd=cwd, check=False).returncode


def _fail(message: str) -> typer.Exit:
    typer.echo(f"ERROR: {message}", err=True)
    return typer.Exit(code=1)


def _choose(
    found: list[FoundModule],
    *,
    select: list[str] | None,
    all_modules: bool,
    assume_yes: bool,
) -> list[FoundModule]:
    if len(found) == 1:
        return found
    if all_modules:
        return found
    if select:
        wanted = {s.replace("-", "_").lower() for s in select}
        chosen = [m for m in found if m.dist_name.replace("-", "_").lower() in wanted]
        missing = wanted - {m.dist_name.replace("-", "_").lower() for m in chosen}
        if missing:
            raise _fail(f"module(s) not found in repo: {', '.join(sorted(missing))}")
        return chosen
    if assume_yes:
        names = ", ".join(m.dist_name for m in found)
        raise _fail(f"repo contains multiple modules ({names}); pick with --module a,b or --all")
    return [
        m
        for m in found
        if typer.confirm(f"Include {m.dist_name} ({m.subdirectory or 'repo root'})?")
    ]


def post_install(
    project_dir: Path,
    dists: list[str],
    models_dists: list[str],
    exec_runner: ExecRunner,
) -> None:
    """uv sync → gen-pages → sync-js-deps → entry-point check → reminders."""
    if exec_runner(["uv", "sync"], project_dir) != 0:
        raise _fail("`uv sync` failed — pyproject was written; fix and re-run `uv sync`.")
    if (project_dir / "client_app").is_dir():
        exec_runner(["uv", "run", "smpy", "host", "gen-pages"], project_dir)
        exec_runner(["uv", "run", "smpy", "host", "sync-js-deps"], project_dir)
    for dist in dists:
        code = exec_runner(["uv", "run", "python", "-c", _ENTRYPOINT_CHECK, dist], project_dir)
        if code != 0:
            raise _fail(
                f"{dist} installed but exposes no [project.entry-points.simple_module] "
                "entry point — it is not a SimpleModule module."
            )
    for dist in models_dists:
        typer.echo(
            f"{dist} ships database models — generate and apply the migration:\n"
            f'  make migration msg="add {dist}"\n  make migrate'
        )


def run_add(
    spec: str,
    *,
    pyproject: Path,
    select: list[str] | None = None,
    all_modules: bool = False,
    no_sync: bool = False,
    assume_yes: bool = False,
    git_runner=None,
    exec_runner: ExecRunner | None = None,
) -> list[str]:
    if not pyproject.is_file():
        raise _fail(f"{pyproject} not found")
    exec_runner = exec_runner or _default_exec_runner
    try:
        parsed = parse_add_spec(spec)
    except SpecError as exc:
        raise _fail(str(exc)) from exc
    doc = load_pyproject(pyproject)

    if parsed.kind == "pypi":
        name = parsed.raw
        for i, ch in enumerate(parsed.raw):
            if ch in "<>=!~[; ":
                name = parsed.raw[:i]
                break
        constraint = parsed.raw[len(name) :]
        write_dependency(doc, name, constraint)
        save_pyproject(pyproject, doc)
        typer.echo(f"Added {name} (PyPI).")
        if not no_sync:
            post_install(pyproject.parent, [name], [], exec_runner)
        return [name]

    if parsed.kind == "path":
        assert parsed.path is not None
        root = parsed.path if parsed.path.is_absolute() else pyproject.parent / parsed.path
        found = [m for m in scan_modules(root) if m.subdirectory is None]
        if not found:
            raise _fail(
                f"{root} has no [project.entry-points.simple_module] entry point at its root"
            )
        mod = found[0]
        write_dependency(doc, mod.dist_name, derive_range(mod.version))
        write_path_source(doc, mod.dist_name, path=str(parsed.path))
        save_pyproject(pyproject, doc)
        typer.echo(f"Added {mod.dist_name} (editable path {parsed.path}).")
        if not no_sync:
            post_install(
                pyproject.parent,
                [mod.dist_name],
                [mod.dist_name] if mod.ships_models else [],
                exec_runner,
            )
        return [mod.dist_name]

    assert parsed.git is not None
    git_kwargs = {"run": git_runner} if git_runner else {}
    ref_info = classify_ref(parsed.git.url, parsed.git.ref, **git_kwargs)
    with tempfile.TemporaryDirectory(prefix="smpy-add-") as tmp:
        clone = shallow_clone(parsed.git.url, ref_info, Path(tmp) / "repo", **git_kwargs)
        found = scan_modules(clone)
    if parsed.git.subdirectory is not None:
        found = [m for m in found if m.subdirectory == parsed.git.subdirectory]
    if not found:
        where = (
            f"subdirectory {parsed.git.subdirectory!r} of {parsed.git.url}"
            if parsed.git.subdirectory
            else parsed.git.url
        )
        raise _fail(f"{where} has no package declaring [project.entry-points.simple_module]")
    chosen = _choose(found, select=select, all_modules=all_modules, assume_yes=assume_yes)
    if not chosen:
        raise _fail("no modules selected")

    if not has_git_sources(doc):
        typer.echo(_SECURITY_NOTICE)
    for mod in chosen:
        write_dependency(doc, mod.dist_name, derive_range(mod.version))
        write_git_source(
            doc,
            mod.dist_name,
            url=parsed.git.url,
            ref_info=ref_info,
            subdirectory=mod.subdirectory,
        )
        pin = f"{ref_info.kind} {ref_info.value}" if ref_info.value else "default branch"
        typer.echo(f"Added {mod.dist_name} {mod.version} from git ({pin}).")
        if ref_info.kind == "branch":
            typer.echo(
                f"  {mod.dist_name} tracks a branch — dev-mode pin; prefer a v* tag for releases."
            )
    save_pyproject(pyproject, doc)
    if not no_sync:
        post_install(
            pyproject.parent,
            [m.dist_name for m in chosen],
            [m.dist_name for m in chosen if m.ships_models],
            exec_runner,
        )
    return [m.dist_name for m in chosen]


def add_module(
    spec: Annotated[
        str,
        typer.Argument(help="PyPI requirement, git+URL[@ref][#subdirectory=dir], or local path."),
    ],
    module: Annotated[
        str,
        typer.Option("--module", help="Comma-separated module dist names (multi-module repos)."),
    ] = "",
    all_modules: Annotated[
        bool, typer.Option("--all", help="Add every module found in the repo.")
    ] = False,
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    no_sync: Annotated[
        bool,
        typer.Option("--no-sync", help="Write pyproject only; skip uv sync / gen-pages."),
    ] = False,
    yes: Annotated[bool, typer.Option("--yes", "-y", help="Never prompt (fail instead).")] = False,
) -> None:
    """Add a module dependency from PyPI, a git repo, or a local path."""
    pyproject = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    select = [m.strip() for m in module.split(",") if m.strip()]
    run_add(
        spec,
        pyproject=pyproject,
        select=select or None,
        all_modules=all_modules,
        no_sync=no_sync,
        assume_yes=yes,
    )
```

- [ ] **Step 4: Register in `cli.py`**

In `framework/cli/simple_module_cli/cli.py`, add to the imports:

```python
from simple_module_cli.add_cmd import add_module
```

and next to `app.command("package-update")(package_update)`:

```python
app.command("add")(add_module)
```

Extend the module docstring's built-in command list with `smpy add`.

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_cli_add_cmd.py -v`
Expected: PASS. If `raise _fail(...)` trips ty (returning `typer.Exit` then raising), keep `_fail` returning the exception — `raise _fail(x)` is valid because `_fail` returns the `typer.Exit` instance.

- [ ] **Step 6: Check line cap, format + commit**

```bash
wc -l framework/cli/simple_module_cli/add_cmd.py   # must be < 300
uv run ruff format framework/cli/simple_module_cli/ framework/cli/tests/
git add framework/cli/simple_module_cli/add_cmd.py framework/cli/simple_module_cli/cli.py framework/cli/tests/test_cli_add_cmd.py
git commit -m "feat(cli): smpy add — modules from PyPI, git repos, or local paths"
```

If over 300 lines, move `post_install` + `_ENTRYPOINT_CHECK` + `_default_exec_runner` into `framework/cli/simple_module_cli/module_install.py` and import from there (update Task 5's import accordingly).

---

### Task 5: `smpy update` command (`update_cmd.py` + registration)

**Files:**
- Create: `framework/cli/simple_module_cli/update_cmd.py`
- Modify: `framework/cli/simple_module_cli/cli.py` (register `update`)
- Test: `framework/cli/tests/test_cli_update_sources.py`

**Interfaces:**
- Consumes: `list_remote_refs`, `pick_latest_tag` (Task 1–2); `load_pyproject`, `save_pyproject`, `git_sources`, `dep_constraint`, `write_dependency` (Task 3); `post_install`, `ExecRunner` (Task 4).
- Produces: `run_sources_update(pyproject: Path, *, only: str | None, dry_run: bool, git_runner=None, exec_runner=None) -> None`; Typer command `update_modules` registered as `smpy update`.

- [ ] **Step 1: Write the failing tests**

```python
"""Tests for `smpy update` — git-tag group updates over [tool.uv.sources]."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.update_cmd import run_sources_update


def _host(tmp_path: Path, url: str) -> Path:
    p = tmp_path / "host" / "pyproject.toml"
    p.parent.mkdir()
    p.write_text(
        '[project]\nname = "myhost"\nversion = "0.1.0"\n'
        "dependencies = [\n"
        '    "simple_module_blog>=0.1.0,<1.0",\n'
        '    "simple_module_comments>=0.1.0,<1.0",\n'
        '    "simple_module_dashboard>=0.1",\n'
        "]\n\n"
        "[tool.uv.sources]\n"
        f'simple_module_blog = {{ git = "{url}", tag = "v0.1.0", subdirectory = "modules/blog" }}\n'
        f'simple_module_comments = {{ git = "{url}", tag = "v0.1.0", subdirectory = "modules/comments" }}\n',
        encoding="utf-8",
    )
    return p


def _recorder():
    calls: list[list[str]] = []

    def runner(cmd: list[str], cwd: Path) -> int:
        calls.append(cmd)
        return 0

    return calls, runner


def _git_stub(tags: list[str]):
    def run(args, cwd=None):
        assert args[0] == "ls-remote"
        return "".join(f"sha\trefs/tags/{t}\n" for t in tags) + "sha\trefs/heads/main\n"

    return run


def test_group_update_moves_all_siblings(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only=None,
        dry_run=False,
        git_runner=_git_stub(["v0.1.0", "v0.3.0", "v2.0.0"]),  # v2 excluded by <1.0
        exec_runner=runner,
    )
    text = p.read_text(encoding="utf-8")
    assert text.count('tag = "v0.3.0"') == 2
    assert 'tag = "v0.1.0"' not in text
    # dep floors bumped to the new version
    assert "simple_module_blog>=0.3.0,<1.0" in text
    assert ["uv", "sync"] in calls


def test_dry_run_writes_nothing(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    before = p.read_text(encoding="utf-8")
    calls, runner = _recorder()
    run_sources_update(
        p, only=None, dry_run=True, git_runner=_git_stub(["v0.3.0"]), exec_runner=runner
    )
    assert p.read_text(encoding="utf-8") == before
    assert calls == []


def test_only_limits_to_that_group(tmp_path: Path, capsys) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only="simple_module_blog",
        dry_run=False,
        git_runner=_git_stub(["v0.3.0"]),
        exec_runner=runner,
    )
    # group update still moves the sibling — same repo, one ref (spec §3/§4)
    assert p.read_text(encoding="utf-8").count('tag = "v0.3.0"') == 2


def test_pypi_name_delegates_to_uv_lock(tmp_path: Path) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    calls, runner = _recorder()
    run_sources_update(
        p,
        only="simple_module_dashboard",
        dry_run=False,
        git_runner=_git_stub([]),
        exec_runner=runner,
    )
    assert ["uv", "lock", "--upgrade-package", "simple_module_dashboard"] in calls


def test_branch_pin_relocks_and_labels_dev_mode(tmp_path: Path, capsys) -> None:
    p = tmp_path / "pyproject.toml"
    p.write_text(
        '[project]\nname = "h"\nversion = "0"\n'
        'dependencies = ["simple_module_blog>=0.1,<1.0"]\n\n'
        "[tool.uv.sources]\n"
        'simple_module_blog = { git = "https://github.com/x/b", branch = "main" }\n',
        encoding="utf-8",
    )
    calls, runner = _recorder()
    run_sources_update(p, only=None, dry_run=False, git_runner=_git_stub([]), exec_runner=runner)
    assert ["uv", "lock", "--upgrade-package", "simple_module_blog"] in calls
    assert "dev-mode" in capsys.readouterr().out


def test_no_newer_tag_is_a_quiet_noop(tmp_path: Path, capsys) -> None:
    p = _host(tmp_path, "https://github.com/x/mods")
    before = p.read_text(encoding="utf-8")
    calls, runner = _recorder()
    run_sources_update(
        p, only=None, dry_run=False, git_runner=_git_stub(["v0.1.0"]), exec_runner=runner
    )
    assert p.read_text(encoding="utf-8") == before
    assert "up to date" in capsys.readouterr().out
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `uv run pytest framework/cli/tests/test_cli_update_sources.py -v`
Expected: FAIL — module not found.

- [ ] **Step 3: Implement `update_cmd.py`**

```python
"""``smpy update`` — move git-sourced modules to their newest release tag.

Git-sourced modules pinned to a tag are updated group-wise: every module
sourced from the same repo URL moves to the same new tag (one repo, one
ref — spec §3). The new tag must be a ``v*`` semver tag satisfying every
sibling's declared dependency range. Branch-pinned sources re-lock to the
newest SHA (dev-mode). Rev-pinned sources are left alone. A plain PyPI
dependency named via ``NAME`` delegates to ``uv lock --upgrade-package``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.add_cmd import ExecRunner, _default_exec_runner, post_install
from simple_module_cli.git_source import (
    derive_range,
    list_remote_refs,
    pick_latest_tag,
)
from simple_module_cli.pyproject_edit import (
    dep_constraint,
    git_sources,
    load_pyproject,
    save_pyproject,
    write_dependency,
)

__all__ = ["run_sources_update", "update_modules"]


def _groups(sources: dict[str, dict]) -> dict[str, list[str]]:
    by_url: dict[str, list[str]] = {}
    for name, src in sources.items():
        by_url.setdefault(str(src["git"]), []).append(name)
    return by_url


def run_sources_update(
    pyproject: Path,
    *,
    only: str | None,
    dry_run: bool,
    git_runner=None,
    exec_runner: ExecRunner | None = None,
) -> None:
    if not pyproject.is_file():
        typer.echo(f"ERROR: {pyproject} not found.", err=True)
        raise typer.Exit(code=1)
    exec_runner = exec_runner or _default_exec_runner
    git_kwargs = {"run": git_runner} if git_runner else {}
    doc = load_pyproject(pyproject)
    sources = git_sources(doc)

    if only and only not in sources:
        # PyPI-sourced (or path-sourced) name: delegate to uv's resolver.
        if dep_constraint(doc, only) is None:
            typer.echo(f"ERROR: {only} is not a dependency of this host.", err=True)
            raise typer.Exit(code=1)
        if dry_run:
            typer.echo(f"Would run: uv lock --upgrade-package {only}")
            return
        exec_runner(["uv", "lock", "--upgrade-package", only], pyproject.parent)
        post_install(pyproject.parent, [], [], exec_runner)
        return

    changed: list[str] = []
    relock: list[str] = []
    for url, names in _groups(sources).items():
        if only and only not in names:
            continue
        tag_pinned = [n for n in names if "tag" in sources[n]]
        branch_pinned = [n for n in names if "branch" in sources[n]]
        for name in branch_pinned:
            typer.echo(f"{name}: tracks branch {sources[name]['branch']!r} — dev-mode re-lock.")
            relock.append(name)
        if not tag_pinned:
            continue
        tags, _ = list_remote_refs(url, **git_kwargs)
        candidate: str | None = None
        for name in tag_pinned:
            constraint = dep_constraint(doc, name)
            best = pick_latest_tag(tags, constraint)
            if best is None:
                continue
            if candidate is None or best != candidate:
                # every sibling must accept the same tag; intersect by re-checking
                candidate = best if candidate is None else min(candidate, best)
        if candidate is None:
            continue
        current = {str(sources[n]["tag"]) for n in tag_pinned}
        if current == {candidate}:
            typer.echo(f"{url}: up to date ({candidate}).")
            continue
        version = candidate[1:]
        for name in tag_pinned:
            uv_sources = doc["tool"]["uv"]["sources"]  # exists: git_sources was non-empty
            uv_sources[name]["tag"] = candidate
            write_dependency(doc, name, derive_range(version))
            changed.append(name)
            typer.echo(f"{name}: → {candidate}")

    if not changed and not relock:
        if not sources:
            typer.echo("No git-sourced modules found. For PyPI deps use `smpy package-update`.")
        return
    if dry_run:
        typer.echo("(dry-run) no files written.")
        return
    if changed:
        save_pyproject(pyproject, doc)
    for name in relock:
        exec_runner(["uv", "lock", "--upgrade-package", name], pyproject.parent)
    if changed or relock:
        post_install(pyproject.parent, changed, [], exec_runner)


def update_modules(
    name: Annotated[
        str | None,
        typer.Argument(help="Module dist name. Omit to update every git-sourced module."),
    ] = None,
    path: Annotated[
        Path,
        typer.Option("--path", help="Project root or pyproject.toml. Defaults to cwd."),
    ] = Path(),
    dry_run: Annotated[
        bool, typer.Option("--dry-run", help="Show planned changes without writing.")
    ] = False,
) -> None:
    """Update git-sourced modules to their newest release tag (group-wise per repo)."""
    pyproject = path if path.name == "pyproject.toml" else path / "pyproject.toml"
    run_sources_update(pyproject, only=name, dry_run=dry_run)
```

Group-tag note: with per-module constraints the safe shared tag is the *minimum* of each sibling's best tag (a tag one sibling's range rejects must not win). The test suite covers equal constraints; the `min(candidate, best)` uses string compare on `vX.Y.Z` which is wrong for `v1.10` vs `v1.9` — implement the min with `version_tuple` comparison instead: keep whichever of the two tags has the smaller `version_tuple(tag[1:])`. Import `version_tuple` from `git_source` and write it as an explicit `if` (no `min` with a key on two values, keep it readable).

- [ ] **Step 4: Register in `cli.py`**

```python
from simple_module_cli.update_cmd import update_modules

...
app.command("update")(update_modules)
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `uv run pytest framework/cli/tests/test_cli_update_sources.py framework/cli/tests/test_cli_add_cmd.py -v`
Expected: PASS.

- [ ] **Step 6: Format + commit**

```bash
uv run ruff format framework/cli/simple_module_cli/ framework/cli/tests/
git add framework/cli/simple_module_cli/update_cmd.py framework/cli/simple_module_cli/cli.py framework/cli/tests/test_cli_update_sources.py
git commit -m "feat(cli): smpy update — group-wise git tag updates for module sources"
```

---

### Task 6: Wizard + `smpy new` + `create-host` integration

**Files:**
- Modify: `framework/cli/simple_module_cli/wizard.py` (git URL loop; return arity 3 → 4)
- Modify: `framework/cli/simple_module_cli/new.py` (`--git-module` repeatable option; apply specs after scaffold)
- Modify: `framework/cli/simple_module_cli/cli.py` (`create-host` gains `--git-module`)
- Modify: `framework/cli/tests/test_cli_wizard.py` (new arity + one extra blank answer per drive)
- Test: `framework/cli/tests/test_cli_wizard_git.py`, `framework/cli/tests/test_cli_new_git_module.py`

**Interfaces:**
- Consumes: `run_add` from Task 4.
- Produces: `run_wizard(*, default_db, default_tenancy) -> tuple[str, bool, list[str], list[str]]` — fourth element is the list of git specs (may be empty). `new_project` and `create_host` accept `git_module: list[str] | None` via repeatable `--git-module`.

- [ ] **Step 1: Extend the wizard**

In `wizard.py`, after the module selection and before the final `Proceed?` confirm, insert:

```python
git_specs: list[str] = []
if typer.confirm("Add modules from a git URL?", default=False):
    while True:
        url = typer.prompt("git+URL (blank to finish)", default="", show_default=False).strip()
        if not url:
            break
        if not url.startswith("git+"):
            typer.echo("Spec must start with git+ (e.g. git+https://github.com/x/repo)")
            continue
        git_specs.append(url)
```

and change the return to `return db, tenancy, resolved, git_specs`.

- [ ] **Step 2: Update existing wizard tests**

In `test_cli_wizard.py`: `_drive` unpacks four values (`db, tenancy, selected = ...` → also capture `git_specs`), and every `_drive([...])` answers list gets one extra `""` (the new confirm, defaulting to no). Adjust `run_wizard` call sites in `_drive`'s wrapper accordingly.

- [ ] **Step 3: Write the failing wizard-git tests**

```python
"""Tests for the wizard's git-module step."""

from __future__ import annotations

import typer
from simple_module_cli.wizard import run_wizard
from typer.testing import CliRunner


def _drive(answers: list[str]):
    captured: dict = {}
    wrapper_app = typer.Typer()

    @wrapper_app.command()
    def wrapper() -> None:
        db, tenancy, selected, git_specs = run_wizard(default_db="sqlite", default_tenancy=False)
        captured.update(db=db, selected=selected, git_specs=git_specs)

    runner = CliRunner()
    result = runner.invoke(wrapper_app, [], input="\n".join(answers) + "\n")
    assert result.exit_code == 0, result.output
    return captured


def test_wizard_collects_git_specs() -> None:
    captured = _drive(["", "", "", "y", "git+https://github.com/x/repo@v1.0.0", "", ""])
    assert captured["git_specs"] == ["git+https://github.com/x/repo@v1.0.0"]


def test_wizard_git_step_default_is_skip() -> None:
    captured = _drive(["", "", "", "", ""])
    assert captured["git_specs"] == []


def test_wizard_rejects_non_git_spec_and_reprompts() -> None:
    captured = _drive(
        ["", "", "", "y", "https://github.com/x/repo", "git+https://github.com/x/r", "", ""]
    )
    assert captured["git_specs"] == ["git+https://github.com/x/r"]
```

- [ ] **Step 4: Run wizard tests**

Run: `uv run pytest framework/cli/tests/test_cli_wizard_git.py framework/cli/tests/test_cli_wizard.py -v`
Expected: PASS after Steps 1–2 (the git tests were written before running — verify they failed first by running between Steps 2 and 3 if strict TDD ordering is wanted; the wizard change and test update are inseparable because the arity changes).

- [ ] **Step 5: Wire `--git-module` into `smpy new`**

In `new.py`: add the option

```python
git_module: Annotated[
    list[str] | None,
    typer.Option(
        "--git-module",
        help="git+URL[@ref][#subdirectory=dir] module source; repeatable.",
    ),
] = (None,)
```

The wizard branch becomes:

```python
        db_final, tenancy_final, resolved, wizard_git = run_wizard(
            default_db=db.value, default_tenancy=tenancy
        )
```

(the flag-driven branch sets `wizard_git: list[str] = []`), and after `create_app_project(...)` succeeds, before the install phase:

```python
    git_specs = [*(git_module or []), *wizard_git]
    for spec in git_specs:
        run_add(
            spec,
            pyproject=target / "pyproject.toml",
            no_sync=True,  # the install phase below (or the user) runs uv sync
            assume_yes=yes,
        )
```

Import `run_add` from `simple_module_cli.add_cmd`. In the `no_install` next-steps output, nothing changes — `uv sync` is already listed.

- [ ] **Step 6: Wire `--git-module` into `create-host` (`cli.py`)**

Add the same repeatable option to `create_host`, and after `_create_host(...)`:

```python
    for spec in git_module or []:
        run_add(spec, pyproject=target / "pyproject.toml", no_sync=True, assume_yes=True)
```

(`create-host` is non-interactive: multi-module repos need `#subdirectory` per spec here, which `assume_yes=True` enforces with a clear error.)

- [ ] **Step 7: Write the failing new-integration test**

```python
"""`smpy new --git-module` writes git sources into the scaffolded host."""

from __future__ import annotations

from pathlib import Path

from simple_module_cli.cli import app
from typer.testing import CliRunner


def test_new_with_git_module_writes_source(tmp_path: Path, make_git_module_repo) -> None:
    repo = make_git_module_repo([("simple_module_blog", "0.2.0", None, False)], tags=["v0.2.0"])
    runner = CliRunner()
    result = runner.invoke(
        app,
        [
            "new",
            "demoapp",
            "--dest",
            str(tmp_path / "demoapp"),
            "--preset",
            "minimal",
            "--yes",
            "--no-install",
            "--git-module",
            f"git+{repo.as_uri()}@v0.2.0",
        ],
    )
    assert result.exit_code == 0, result.output
    text = (tmp_path / "demoapp" / "pyproject.toml").read_text(encoding="utf-8")
    assert "simple_module_blog>=0.2.0,<1.0" in text
    assert 'tag = "v0.2.0"' in text
```

- [ ] **Step 8: Run the integration tests**

Run: `uv run pytest framework/cli/tests/test_cli_new_git_module.py framework/cli/tests/test_cli_new.py -v`
Expected: PASS (scaffold templates work offline; `--no-install` skips uv/npm). If the scaffolded root `pyproject.toml` lives elsewhere than `target/pyproject.toml`, read `create_app_project` to find the actual host pyproject path and adjust — do not guess.

- [ ] **Step 9: Format + commit**

```bash
uv run ruff format framework/cli/simple_module_cli/ framework/cli/tests/
git add -A framework/cli
git commit -m "feat(cli): --git-module for smpy new / create-host + wizard git step"
```

---

### Task 7: Documentation

**Files:**
- Modify: `docs/module-authoring.md` (intro + new "Distributing via git" section)
- Modify: `framework/cli/simple_module_cli/templates/host/README.md.tpl` (git install alternative)
- Modify: `docs/framework-conventions.md` (one-paragraph lockstep-tag convention)

- [ ] **Step 1: Reframe `docs/module-authoring.md` intro**

Change line 3's "installable from PyPI" to "installable from PyPI **or any git repo**", keeping the rest of the sentence.

- [ ] **Step 2: Add the "Distributing via git" section** (place it after the "Standalone vs in-repo" section)

```markdown
## Distributing via git

A module does not need PyPI. Any git repo whose package declares
`[project.entry-points.simple_module]` is installable:

```bash
smpy add git+https://github.com/you/your-module@v1.2.0
```

This writes a normal named dependency plus a `[tool.uv.sources]` redirect
into the host's `pyproject.toml`, runs `uv sync`, regenerates the module
pages manifest, and verifies the entry point. `uv.lock` pins the exact
commit SHA, so builds stay reproducible.

**Release tags.** Tag releases `vX.Y.Z` where the version matches the
package's `pyproject.toml` — the tag is the release. `smpy update` finds the
newest tag satisfying the host's declared range and rewrites the pin.
Branch pins (`@main`) are dev-mode: they re-lock to the newest SHA on
update and are labeled as such.

**Multi-module repos.** A repo may carry several modules (the `modules/*`
monorepo layout). `smpy add git+URL` without `#subdirectory` scans the repo
and offers a picker (`--module a,b` / `--all` non-interactively). All
modules installed from one repo share one pinned ref, and `smpy update`
moves them together — tag the repo as a unit.

**What the repo must contain.** The scaffold from `smpy create-module
--standalone` is already correct: the entry point, `package.json` and
`pages/` force-included into the wheel, and a `v*`-triggered publish
workflow (optional for git-only distribution). Frontend assets need no npm
publishing — the host aliases the module's npm name onto its installed
package directory.

**Private repos.** Authentication is git's job: SSH keys, credential
helpers, or tokens in CI. If `git clone` works in your shell, `smpy add`
and `uv sync` work too.
```

- [ ] **Step 3: Extend the host README template**

In `framework/cli/simple_module_cli/templates/host/README.md.tpl`, next to the existing `uv add simple_module_my_module` line, add:

```markdown
# or straight from a git repo (any host, private included):
smpy add git+https://github.com/you/your-module@v1.2.0
```

- [ ] **Step 4: Add the tag convention to `docs/framework-conventions.md`**

Append under the versioning/API-stability section (find the semver / `requires_framework` discussion and add one paragraph):

```markdown
Modules distributed via git release by tagging: repo-wide lockstep `vX.Y.Z`
tags where the tag version equals every contained package's declared
version. Hosts pin one ref per repo; `smpy update` moves all modules from
the same repo together.
```

- [ ] **Step 5: Commit**

```bash
git add docs/module-authoring.md docs/framework-conventions.md framework/cli/simple_module_cli/templates/host/README.md.tpl
git commit -m "docs: modules installable from any git repo — authoring + host docs"
```

---

### Task 8: Full verification sweep

- [ ] **Step 1: Bootstrap check** — if this worktree hasn't been synced: `uv sync --all-packages && npm install && make gen-pages` (memory: skipping this fakes unrelated failures).

- [ ] **Step 2: Run the whole CLI suite** — `uv run pytest framework/cli/tests/ -v` → all green, including `test_no_framework_deps.py` (new modules import only typer/tomlkit/stdlib).

- [ ] **Step 3: Full gates** — `make test-py > /tmp-file 2>&1; echo $?` style (redirect to a file, don't pipe — memory: piped exit codes lie), then `make lint`. Fix anything that surfaces.

- [ ] **Step 4: Manual smoke** — in a temp dir outside the repo: build a local two-module git repo (reuse the conftest recipe by hand), then `uv run smpy add git+file://...` against a scaffolded host with `--no-sync` and inspect the written pyproject.

- [ ] **Step 5: Commit any fixes; push the branch.**

---

## Self-review notes

- Spec §1 table forms → Task 1 (parse) + Task 4 (behavior); §2 multi-module → Tasks 2/4; §3 convention → Tasks 5/7; §4 update → Task 5; §5 wizard → Task 6; §6 validation → Task 4 (write-late, entry-point check, security notice, migration reminder); §7 docs → Task 7; §8 testing → every task + Task 8.
- Deliberate deviation from spec §4: `smpy update` bumps the dependency floor to the new tag's version alongside the tag pin (keeps `dep_constraint`-based tag filtering meaningful on the next update). Harmless strengthening; documented here.
- `derive_range` uses `<1.0` for 0.x majors — matches the framework's own `>=0.1,<1.0` convention.
