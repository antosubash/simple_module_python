"""Ignore the invoking project's dotenv files, including during collection.

Keep lookup and SQLite anchoring intact, and allow temporary dotenv files used
by tests of configuration itself. Real environment variables still apply.
"""

from pathlib import Path

import pytest
from pydantic_settings import DotEnvSettingsSource
from simple_module_core.settings import dotenv
from simple_module_hosting.config import _preapp_config


def isolate_project_dotenv(config: pytest.Config) -> None:
    ignored = {
        dotenv.find_env_file().resolve(),
        (config.rootpath / ".env").resolve(),
        (Path.cwd() / ".env").resolve(),
    }
    patch = pytest.MonkeyPatch()
    config.add_cleanup(patch.undo)
    parse = dotenv.parse_dotenv
    read = DotEnvSettingsSource._read_env_file

    def parse_dotenv(path: Path | None = None) -> dict[str, str]:
        path = path if path is not None else dotenv.find_env_file()
        return {} if path.resolve() in ignored else parse(path)

    def read_env_file(source, path: Path):
        return {} if path.resolve() in ignored else read(source, path)

    patch.setattr(dotenv, "parse_dotenv", parse_dotenv)
    # Hosting imports the parser before the pytest plugin is loaded.
    patch.setattr(_preapp_config, "parse_dotenv", parse_dotenv)
    patch.setattr(DotEnvSettingsSource, "_read_env_file", read_env_file)
