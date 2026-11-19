"""Plan git updates across the workspace before writing any manifest."""

from pathlib import Path

import tomlkit
import typer

from simple_module_cli.git_source import derive_range, list_remote_refs, pick_latest_tag
from simple_module_cli.package_update_deps import Change, _dependency_arrays, normalize, source_map
from simple_module_cli.requirements import is_valid_version, parse_requirement, rewrite_requirement


def plan_git(
    files: list[tuple[Path, tomlkit.TOMLDocument]], *, only: str | None, git_runner=None
) -> tuple[list[Change], list[str], dict[str, str]]:
    """Keep tag siblings together; branch sources refresh and immutable revs stay put."""
    inherited = source_map(files[0][1])
    groups: dict[str, list[tuple[Path, str, dict]]] = {}
    dependencies = []
    for file, doc in files:
        own = source_map(doc)
        for name, src in own.items():
            if isinstance(src, dict) and "git" in src:
                groups.setdefault(str(src["git"]), []).append((file, name, src))
        effective = {**inherited, **own}
        for deps in _dependency_arrays(doc):
            for i, raw in enumerate(deps):
                parsed = parse_requirement(raw) if isinstance(raw, str) else None
                if (
                    parsed
                    and isinstance(src := effective.get(normalize(parsed.name)), dict)
                    and "git" in src
                ):
                    dependencies.append((file, deps, i, parsed, src))

    changes = []
    relock = []
    targets = {}
    for url, entries in groups.items():
        if only and normalize(only) not in {name for _, name, _ in entries}:
            continue
        for _, name, src in entries:
            if "branch" in src or not any(k in src for k in ("tag", "rev")):
                typer.echo(f"{name}: tracks a branch — dev-mode re-lock.")
                relock.append(name)
        tagged = [(f, n, s) for f, n, s in entries if "tag" in s]
        if not tagged:
            continue
        deps = [d for d in dependencies if d[4].get("git") == url and "tag" in d[4]]
        # An exact pin moves with its tag; it still supplies a floor against downgrades.
        constraint = ",".join(
            f"{'>=' if op in ('==', '===') and not v.endswith('.*') else op}{v}"
            for d in deps
            for op, v in d[3].clauses
        )
        floors = [
            f">={version}"
            for _, _, src in tagged
            if is_valid_version(version := str(src["tag"]).removeprefix("v"))
        ]
        constraint = ",".join(filter(None, [constraint, *floors]))
        kwargs = {"run": git_runner} if git_runner else {}
        tags, _ = list_remote_refs(url, **kwargs)
        candidate = pick_latest_tag(tags, constraint)
        if candidate is None:
            continue
        version = candidate[1:]
        for file, name, src in tagged:
            targets[name] = version
            if src["tag"] != candidate:
                changes.append(Change(file, name, str(src["tag"]), candidate))
                src["tag"] = candidate
            else:
                typer.echo(f"{name}: up to date ({candidate}).")
        for file, array, i, parsed, _ in deps:
            old = str(array[i])
            result = rewrite_requirement(old, version)
            new = result.spec
            if not parsed.clauses:
                new = f"{parsed.name}{parsed.extras}{derive_range(version)}{parsed.marker}"
            if new and new != old:
                array[i] = new
                changes.append(Change(file, parsed.name, old, new))
    return changes, sorted(set(relock)), targets
