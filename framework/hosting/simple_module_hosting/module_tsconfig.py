"""Host-owned TypeScript projects for modules without an authored config."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import tomllib
from collections.abc import Sequence
from pathlib import Path

from simple_module_core import get_module_package_name

from simple_module_hosting._generated_files import _write_if_changed
from simple_module_hosting.assets import ModuleAssets


def _link(target: Path, path: Path) -> None:
    """Keep source links in the host tree so npm exports resolve normally."""
    if path.is_symlink() or path.is_junction():
        if path.resolve() == target.resolve():
            return
        if path.is_junction():
            path.rmdir()
        else:
            path.unlink()
    if path.exists():
        raise ValueError(f"Expected a generated source link at {path}; remove it and retry")
    path.parent.mkdir(parents=True, exist_ok=True)
    if os.name == "nt":
        # Directory junctions don't require Windows developer mode or admin rights.
        from _winapi import CreateJunction

        CreateJunction(str(target), str(path))
    else:
        path.symlink_to(target, target_is_directory=True)


def _has_typescript(package: Path) -> bool:
    return any(package.rglob("*.tsx")) or any(package.rglob("*.ts"))


def check_local_coverage(assets: Sequence[ModuleAssets], repo_root: Path) -> None:
    """Refuse to silently skip an uninstalled workspace module with frontend sources."""
    packages = {asset.package_dir.resolve() for asset in assets}
    for project in (repo_root / "modules").glob("*/pyproject.toml"):
        data = tomllib.loads(project.read_text(encoding="utf-8"))
        entries = data.get("project", {}).get("entry-points", {}).get("simple_module", {})
        roots = [
            project.parent.joinpath(*get_module_package_name(value.split(":")[0]).split("."))
            for value in entries.values()
        ]
        # A missing entry point must not hide an ordinary module directory either.
        if not roots:
            roots.append(project.parent / project.parent.name)
        for package in set(roots):
            if package.resolve() not in packages and (
                (project.parent / "tsconfig.json").is_file() or _has_typescript(package)
            ):
                raise ValueError(
                    f"{project.parent}: frontend module not discovered; run uv sync --all-packages"
                )


def write_module_tsconfigs(assets: Sequence[ModuleAssets], output_dir: Path) -> list[Path]:
    """Return authored overrides or generate defaults, without writing into modules."""
    output_dir = output_dir.resolve()
    generated = output_dir / ".module-tsconfig"
    configs = []
    aliases = {}
    for asset in assets:
        if asset.npm_name:
            if not re.fullmatch(r"(?:@[\w.-]+/)?[\w.-]+", asset.npm_name) or any(
                part in {".", ".."} for part in asset.npm_name.split("/")
            ):
                raise ValueError(f"Invalid module npm name: {asset.npm_name!r}")
            aliases[asset.npm_name] = asset.package_dir
    alias_dir = generated / "node_modules"
    # Remove only links owned by this generator; never traverse a module target.
    if alias_dir.is_dir():
        for link in [*alias_dir.glob("*"), *alias_dir.glob("@*/*")]:
            if (link.is_symlink() or link.is_junction()) and link.relative_to(
                alias_dir
            ).as_posix() not in aliases:
                link.rmdir() if link.is_junction() else link.unlink()
    for name, target in aliases.items():
        _link(target, alias_dir / name)
    for asset in assets:
        package = asset.package_dir
        # Namespace packages can be several directories below their owning project.
        project = package.parents[asset.package_name.count(".")]
        candidates = [package / "tsconfig.json"]
        if (project / "pyproject.toml").is_file():
            candidates.append(project / "tsconfig.json")
        override = next((path for path in candidates if path.is_file()), None)
        if override is not None:
            configs.append(override)
            continue
        if not _has_typescript(package):
            continue
        linked = (
            alias_dir / asset.npm_name if asset.npm_name else generated / "src" / asset.package_name
        )
        _link(package, linked)
        config = {
            "extends": str(output_dir / "tsconfig.json"),
            "compilerOptions": {"preserveSymlinks": True},
            "include": [str(linked / "**/*.ts"), str(linked / "**/*.tsx")],
            "exclude": [
                str(linked / "**/node_modules/**"),
                "**/*.test.*",
                "**/*.spec.*",
                "**/test-dom.tsx",
                "**/page-tests/**",
            ],
        }
        path = generated / f"{asset.package_name}.json"
        payload = json.dumps(config, indent=2) + "\n"
        _write_if_changed(path, payload)
        configs.append(path)
    return list(dict.fromkeys(configs))


def run_typecheck(
    assets: Sequence[ModuleAssets], host_dir: Path, repo_root: Path, *, installed_only: bool = False
) -> int:
    """Check the host and each module, propagating the first compiler failure."""
    npx = shutil.which("npx")
    if npx is None:
        raise ValueError("npx not found on PATH")
    if not installed_only:
        check_local_coverage(assets, repo_root.resolve())
    configs = [host_dir.resolve() / "tsconfig.json"]
    configs.extend(write_module_tsconfigs(assets, host_dir))
    for config in configs:
        print(f"tsc -p {config}", flush=True)
        result = subprocess.run(
            [npx, "--no-install", "tsc", "--noEmit", "-p", str(config)], cwd=host_dir
        )
        if result.returncode:
            return result.returncode
    return 0
