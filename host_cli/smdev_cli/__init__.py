"""``smdev``: the dev host's own CLI, generated from its bundled OpenAPI schema."""

from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

from simple_module_remote import build_cli

try:
    __version__ = version("smdev-cli")
except PackageNotFoundError:  # pragma: no cover - source checkout without install
    __version__ = "0.0.0"

PACKAGE_DIR = Path(__file__).parent
SCHEMA_PATH = PACKAGE_DIR / "openapi.json"
DEFAULTS_PATH = PACKAGE_DIR / "defaults.toml"
CLI_NAME = "smdev"


def make_cli(**kwargs):
    """Build the click group (tests pass ``transport=`` and ``keyring_backend=``)."""
    return build_cli(CLI_NAME, SCHEMA_PATH, DEFAULTS_PATH, version=__version__, **kwargs)


def main() -> None:
    make_cli()()
