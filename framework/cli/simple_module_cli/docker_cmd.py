"""Additional, Python-only worker images for an existing Compose project."""

import re
from pathlib import Path
from typing import Annotated

import typer

from simple_module_cli.docker_assets import _read, _template_root

_GROUP = "docker"
_COMMAND = "add-worker"
_ENCODING = "utf-8"
_DEFAULT_BASE = "python:3.12-slim-bookworm"
_NAME = r"[a-z][a-z0-9-]{0,40}"
_IDENTIFIER = r"[A-Za-z_][A-Za-z0-9_]*"
_QUEUES = rf"{_IDENTIFIER}(?:,{_IDENTIFIER})*"
_MODULE = rf"{_IDENTIFIER}(?:\.{_IDENTIFIER})*"
_MODULES = rf"{_MODULE}(?:,{_MODULE})*"
_APT = r"[a-z0-9][a-z0-9+.-]*"
_EXTRA = r"[A-Za-z_][A-Za-z0-9_-]*"
_BASE = (
    r"(?:[a-z0-9]+(?:[.-][a-z0-9]+)*(?::[0-9]+)?/)?"
    r"[a-z0-9]+(?:[._-][a-z0-9]+)*(?:/[a-z0-9]+(?:[._-][a-z0-9]+)*)*"
    r"(?::[A-Za-z0-9_][A-Za-z0-9_.-]*)?(?:@sha256:[a-f0-9]{64})?"
)
_COMPOSE_FILES = ("compose.yml", "docker-compose.yml")
_WORKER = re.compile(r"^  worker:\n(?P<body>(?: {4}[^\n]*\n|\n)*)", re.MULTILINE)
_COMMAND_BLOCK = re.compile(r"^    command:\n(?:      [^\n]*\n)*", re.MULTILINE)
_BUILD_BLOCK = re.compile(r"^    build:\n(?:      [^\n]*\n)*", re.MULTILINE)
_ENV_HEADER = "    environment:\n"
_INCLUDE = re.compile(r"^include:[ \t]*(?:#[^\n]*)?$", re.MULTILINE)
_INCLUDE_ANY = re.compile(r"^include:", re.MULTILINE)
_MARKER = "  # smpy worker-{name}"
_INCLUDE_ENTRY = "{marker}\n  - compose.worker-{name}.yml\n"
_DOCKER_PATH = "docker/worker-{name}.Dockerfile"
_COMPOSE_PATH = "compose.worker-{name}.yml"
_DOCKER_TEMPLATE = "worker.Dockerfile.tpl"
_COMPOSE_TEMPLATE = "compose-worker.yml.tpl"
_APT_FLAG = " \\\n    && apt-get install -y --no-install-recommends "
_EXTRA_FLAG = " --extra "
_EMPTY = ""
_NEWLINE = "\n"
_ENV_VALUES = (
    '      SM_BG_TASKS_WORKER_QUEUES: "{queues}"\n'
    '      SM_BG_TASKS_WORKER_INCLUDE_MODULES: "{modules}"\n'
)
_BUILD_VALUES = "    build:\n      context: .\n      dockerfile: {dockerfile}\n"

docker_app = typer.Typer(help="Manage Docker worker images.", no_args_is_help=True)


def _validate(value: str, pattern: str, label: str) -> None:
    if re.fullmatch(pattern, value) is None:
        raise typer.BadParameter(f"Invalid {label}: {value!r}; expected {pattern}")


def _render(template: str, values: dict[str, str]) -> str:
    content = _read(_template_root() / template)
    for key, value in values.items():
        content = content.replace("{{" + key + "}}", value)
    return content


def _include_worker(content: str, name: str) -> str:
    marker = _MARKER.format(name=name)
    if marker in content.splitlines():
        return content
    entry = _INCLUDE_ENTRY.format(marker=marker, name=name)
    include = _INCLUDE.search(content)
    if include:
        position = include.end() + 1
        return content[:position] + entry + content[position:]
    if _INCLUDE_ANY.search(content):
        raise typer.BadParameter(
            "Existing include must use a block list (include: on its own line)."
        )
    return "include:\n" + entry + _NEWLINE + content


@docker_app.command(_COMMAND)
def add_worker(
    name: Annotated[str, typer.Argument(help="Worker image name.")],
    queues: Annotated[str, typer.Option("--queues", help="Comma-separated queue identifiers.")],
    base: Annotated[
        str, typer.Option("--base", help="Python base image (must provide Python).")
    ] = _DEFAULT_BASE,
    apt: Annotated[
        list[str] | None, typer.Option("--apt", help="Repeat for each apt package.")
    ] = None,
    extras: Annotated[
        list[str] | None, typer.Option("--extras", help="Repeat for each uv extra.")
    ] = None,
    modules: Annotated[
        str, typer.Option("--modules", help="Comma-separated Python module paths.")
    ] = _EMPTY,
    force: Annotated[
        bool, typer.Option("--force", help="Replace an existing worker image.")
    ] = False,
) -> None:
    """Generate a worker image and include its service in the project Compose file."""
    _validate(name, _NAME, "name")
    _validate(queues, _QUEUES, "queues")
    _validate(base, _BASE, "base image")
    if modules:
        _validate(modules, _MODULES, "modules")
    for package in apt or []:
        _validate(package, _APT, "apt package")
    for extra in extras or []:
        _validate(extra, _EXTRA, "extra")

    root = Path.cwd()
    compose = next((root / file for file in _COMPOSE_FILES if (root / file).is_file()), None)
    if compose is None:
        raise typer.BadParameter("No compose.yml or docker-compose.yml in the current directory.")
    content = _read(compose)
    if not content.endswith(_NEWLINE):
        content += _NEWLINE
    dockerfile = _DOCKER_PATH.format(name=name)
    service_file = _COMPOSE_PATH.format(name=name)
    paths = (root / dockerfile, root / service_file)
    service_exists = re.search(rf"^  worker-{re.escape(name)}:", content, re.MULTILINE)
    if not force and (any(path.exists() for path in paths) or service_exists):
        raise typer.BadParameter(
            f"Worker {name!r} already exists; use --force to replace its files."
        )
    worker = _WORKER.search(content)
    if worker is None:
        raise typer.BadParameter(
            "Compose must contain an existing worker service to copy its wiring."
        )
    body = worker.group("body")
    if not _BUILD_BLOCK.search(body) or _ENV_HEADER not in body:
        raise typer.BadParameter(
            "Existing worker must have block-style build and environment mappings."
        )
    body = _COMMAND_BLOCK.sub(_EMPTY, body)
    body = _BUILD_BLOCK.sub(_BUILD_VALUES.format(dockerfile=dockerfile), body)
    body = body.replace(
        _ENV_HEADER, _ENV_HEADER + _ENV_VALUES.format(queues=queues, modules=modules)
    )
    updated = _include_worker(content, name)
    values = {
        "NAME": name,
        "BASE": base,
        "APT_PACKAGES": " " + " ".join(apt) if apt else _EMPTY,
        "APT": _APT_FLAG + " ".join(apt) if apt else _EMPTY,
        "EXTRAS": _EMPTY.join(_EXTRA_FLAG + extra for extra in extras or []),
        "BODY": body.rstrip(_NEWLINE) + _NEWLINE,
        "QUEUES": queues,
    }
    docker_content = _render(_DOCKER_TEMPLATE, values)
    service_content = _render(_COMPOSE_TEMPLATE, values)
    paths[0].parent.mkdir(parents=True, exist_ok=True)
    paths[0].write_text(docker_content, encoding=_ENCODING)
    paths[1].write_text(service_content, encoding=_ENCODING)
    compose.write_text(updated, encoding=_ENCODING)
    typer.echo(f"Created {dockerfile} and {service_file}.")
