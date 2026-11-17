"""Keep the environment reference in sync with the shipped settings models."""

import re
from pathlib import Path

from background_tasks.core.settings import BackgroundTasksSettings
from simple_module_hosting.bootstrap_settings import BootstrapSettings
from simple_module_hosting.host_settings import HostSettings
from simple_module_hosting.sentry import SentrySettings


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

    missing = sorted(expected - documented)
    assert not missing, f"Missing from docs/reference/env-vars.md: {', '.join(missing)}"
