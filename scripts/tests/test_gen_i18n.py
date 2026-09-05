"""``make gen-i18n`` — the one script in ``scripts/`` with no test of its own.

``scripts/tests/`` has a module per sibling script; this one was missed. What
matters here is the property #302 fixed and nothing pins from the outside: the
command's exit code has to distinguish "wrote the key files" from "wrote
nothing", because the alternative is a `tsc` error about a key the catalog
does contain, several steps removed from the cause.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "gen_i18n.py"
GENERATED = ROOT / "packages" / "i18n" / "src" / "keys.generated.ts"


def _run() -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        check=False,
    )


class TestTheCommandReportsWhatHappened:
    def test_it_succeeds_and_leaves_the_key_files_current(self) -> None:
        result = _run()

        assert result.returncode == 0, result.stderr
        assert GENERATED.is_file()
        assert "i18n key files up to date" in result.stdout

    def test_it_fails_when_it_cannot_write(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The regression: this used to print success and exit 0.

        Driven through the script's own module rather than by making the real
        package directory unwritable, which would leave the tree broken if the
        assertion failed.
        """
        from simple_module_hosting import i18n_manifest

        def explode(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(i18n_manifest, "write_generated_resources", explode)
        with pytest.raises(OSError, match="disk full"):
            i18n_manifest.emit_frontend_types(_registry(), ROOT, strict=True)

    def test_the_boot_path_still_prefers_stale_types_to_a_failed_start(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The other half of the same flag — a live boot must not raise."""
        from simple_module_hosting import i18n_manifest

        def explode(*args: object, **kwargs: object) -> None:
            raise OSError("disk full")

        monkeypatch.setattr(i18n_manifest, "write_generated_resources", explode)
        i18n_manifest.emit_frontend_types(_registry(), ROOT)  # logged, not raised


def _registry():
    from simple_module_core.i18n import I18nRegistry

    reg = I18nRegistry(default_locale="en", supported_locales=["en"])
    reg._messages = {"en": {"host.landing.title": "Hello"}}
    return reg
