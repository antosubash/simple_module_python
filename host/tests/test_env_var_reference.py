"""Keep the environment reference in sync with the shipped settings and direct environment reads."""

import ast
import re
from pathlib import Path

from background_tasks.core import config_guards
from background_tasks.core.settings import BackgroundTasksSettings
from simple_module_hosting.config.bootstrap_settings import BootstrapSettings
from simple_module_hosting.config.host_settings import HostSettings
from simple_module_hosting.observability.sentry import SentrySettings
from users.core.bootstrap import BOOTSTRAP_ENV_KEYS


def _direct_environment_names(root: Path) -> set[str]:
    names = set(BOOTSTRAP_ENV_KEYS.values())
    # These names interpolate an imported prefix; use their resolved constants.
    names.update(
        value
        for name, value in vars(config_guards).items()
        if name.startswith("ENV_") and name != "ENV_PREFIX" and isinstance(value, str)
    )
    for pattern in ("framework/*/simple_module_*/**/*.py", "modules/*/*/**/*.py", "host/*.py"):
        for path in root.glob(pattern):
            if {"tests", "templates"}.intersection(path.parts):
                continue
            for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
                values = []
                if isinstance(node, ast.Call) and node.args:
                    if ast.unparse(node.func) in {
                        "os.getenv",
                        "os.environ.get",
                        "env_str",
                        "env_bool",
                        "env_csv",
                        "env_json_object",
                    }:
                        values = node.args[:1]
                elif isinstance(node, ast.Subscript) and ast.unparse(node.value) == "os.environ":
                    values = [node.slice]
                elif isinstance(node, (ast.Assign, ast.AnnAssign)):
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    if any(isinstance(t, ast.Name) and "ENV" in t.id for t in targets):
                        values = [node.value]
                names.update(
                    value.value
                    for value in values
                    if isinstance(value, ast.Constant)
                    and isinstance(value.value, str)
                    and re.fullmatch(r"SM_[A-Z0-9_]*[A-Z0-9]", value.value)
                )
    return names


def test_direct_environment_scan_covers_reads_and_constants(tmp_path):
    package = tmp_path / "modules/example/example"
    package.mkdir(parents=True)
    (package / "settings.py").write_text(
        "\n".join(
            [
                'os.environ.get("SM_EXAMPLE_GET")',
                'os.getenv("SM_EXAMPLE_GETENV")',
                'os.environ["SM_EXAMPLE_SUBSCRIPT"]',
                'env_str("SM_EXAMPLE_STRING")',
                'env_bool("SM_EXAMPLE_BOOL")',
                'env_csv("SM_EXAMPLE_CSV")',
                'ENV_EXAMPLE: str = "SM_EXAMPLE_CONSTANT"',
                'ENV_PREFIX = "SM_EXAMPLE_"',
                'unrelated = "SM_TRACKING_HEADER"',
            ]
        ),
        encoding="utf-8",
    )
    names = _direct_environment_names(tmp_path)
    assert {
        "SM_EXAMPLE_GET",
        "SM_EXAMPLE_GETENV",
        "SM_EXAMPLE_SUBSCRIPT",
        "SM_EXAMPLE_STRING",
        "SM_EXAMPLE_BOOL",
        "SM_EXAMPLE_CSV",
        "SM_EXAMPLE_CONSTANT",
    } <= names
    assert "SM_EXAMPLE_" not in names
    assert "SM_TRACKING_HEADER" not in names


def test_environment_settings_are_documented():
    reference = Path(__file__).resolve().parents[2] / "docs/reference/env-vars.md"
    documented = set(
        re.findall(r"^\| `(SM_[A-Z0-9_]+)` \|", reference.read_text(encoding="utf-8"), re.M)
    )

    expected = {
        f"{cls.model_config['env_prefix']}{name.upper()}"
        for cls in (BootstrapSettings, HostSettings, SentrySettings, BackgroundTasksSettings)
        for name in cls.model_fields
    }
    # BackgroundTasksSettings explicitly drops these from its environment sources.
    expected -= {"SM_BG_TASKS_EXECUTION_TRACKING", "SM_BG_TASKS_TRACK_PUBLISH"}

    expected |= _direct_environment_names(reference.parents[2])

    missing = sorted(expected - documented)
    assert not missing, f"Missing from docs/reference/env-vars.md: {', '.join(missing)}"
