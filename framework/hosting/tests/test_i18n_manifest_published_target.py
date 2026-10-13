"""emit_frontend_types target resolution: monorepo vs published npm package vs neither."""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_core.i18n import I18nRegistry
from simple_module_hosting.i18n_manifest import (
    emit_frontend_types,
    resolve_i18n_types_dir,
)


def _registry(*keys: str) -> I18nRegistry:
    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": dict.fromkeys(keys, "x")}
    return reg


def _published(root: Path) -> Path:
    src = root / "node_modules" / "@simple-module-py" / "i18n" / "src"
    src.mkdir(parents=True)
    return src


def test_monorepo_checkout_wins_over_node_modules(tmp_path: Path) -> None:
    local = tmp_path / "packages" / "i18n" / "src"
    local.mkdir(parents=True)
    _published(tmp_path)
    assert resolve_i18n_types_dir(tmp_path) == (local, False)


def test_walks_up_to_hoisted_node_modules(tmp_path: Path) -> None:
    src = _published(tmp_path)
    host = tmp_path / "host"
    host.mkdir()
    found, published = resolve_i18n_types_dir(host)
    assert published is True
    assert found is not None and found.resolve() == src.resolve()


def test_neither_present_resolves_to_none(tmp_path: Path) -> None:
    assert resolve_i18n_types_dir(tmp_path) == (None, False)


def test_boot_path_is_silent_noop_when_neither_exists(tmp_path: Path) -> None:
    emit_frontend_types(_registry("app.k"), tmp_path)
    assert not (tmp_path / "node_modules").exists()


def test_strict_raises_when_neither_exists(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        emit_frontend_types(_registry("app.k"), tmp_path, strict=True)


def test_published_target_merges_published_keys_with_app_keys(tmp_path: Path) -> None:
    src = _published(tmp_path)
    (src / "generated-resources.ts").write_text(
        "export default {\n  translation: {\n    'ui.save': '',\n    'users.title': '',\n"
        "  },\n} as const;\n"
    )
    # App registry has its own namespace and no `users` — must not count as a removal.
    emit_frontend_types(_registry("ui.save", "myapp.title"), tmp_path, strict=True)
    resources = (src / "generated-resources.ts").read_text()
    for key in ("ui.save", "users.title", "myapp.title"):
        assert f"'{key}': ''" in resources
    keys = (src / "keys.generated.ts").read_text()
    assert "myapp" in keys and "users" in keys

    # Idempotent: a second run changes nothing.
    mtime = (src / "keys.generated.ts").stat().st_mtime_ns
    emit_frontend_types(_registry("ui.save", "myapp.title"), tmp_path, strict=True)
    assert (src / "keys.generated.ts").stat().st_mtime_ns == mtime
