from __future__ import annotations

from fastapi.templating import Jinja2Templates

from simple_module_inertia.config import InertiaConfig, resolved_version


def _templates(tmp_path):
    return Jinja2Templates(directory=str(tmp_path))


def test_defaults_match_the_protocol_facing_ones(tmp_path) -> None:
    cfg = InertiaConfig(templates=_templates(tmp_path))
    assert cfg.environment == "development"
    assert cfg.version == "1.0"
    assert cfg.root_template_filename == "index.html"
    assert cfg.entrypoint_filename == "main.js"
    assert cfg.use_flash_errors is False
    assert cfg.flash_error_key == "errors"


def test_a_string_version_resolves_to_itself(tmp_path) -> None:
    cfg = InertiaConfig(templates=_templates(tmp_path), version="abc123")
    assert resolved_version(cfg) == "abc123"


def test_a_callable_version_is_called_each_time(tmp_path) -> None:
    calls = []

    def compute() -> str:
        calls.append(1)
        return f"v{len(calls)}"

    cfg = InertiaConfig(templates=_templates(tmp_path), version=compute)
    assert resolved_version(cfg) == "v1"
    assert resolved_version(cfg) == "v2"
