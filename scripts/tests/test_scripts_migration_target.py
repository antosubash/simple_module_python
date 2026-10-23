"""The repo migration target selects a branch before invoking Alembic."""

import os
import subprocess
from pathlib import Path

import pytest

MAKEFILE = Path(__file__).resolve().parents[2] / "Makefile"


@pytest.mark.parametrize("label", [None, "", "   ", "users"])
@pytest.mark.parametrize("makelevel", ["0", "1"])
def test_scripts_migration_requires_label_and_selects_head(tmp_path, monkeypatch, label, makelevel):
    # Capture the command at the uv boundary; never create a real migration.
    uv = tmp_path / "uv"
    uv.write_text('#!/bin/sh\nprintf "%s\\n" "$@"\n')
    uv.chmod(0o755)
    # `make test-py` exports MAKELEVEL=1: a nested make then appends a
    # "Leaving directory" line. Parent flags/variables must not affect this
    # isolated invocation either (especially -n or an inherited LABEL).
    monkeypatch.setenv("MAKELEVEL", makelevel)
    make_env = {
        "LABEL",
        "MAKELEVEL",
        "MAKEFLAGS",
        "MFLAGS",
        "GNUMAKEFLAGS",
        "MAKEFILES",
        "MAKEOVERRIDES",
    }
    env = {key: value for key, value in os.environ.items() if key not in make_env}
    env["PATH"] = f"{tmp_path}:{env['PATH']}"
    args = ["make", "-f", str(MAKEFILE), "migration", "msg=add foo"]
    if label is not None:
        args.append(f"LABEL={label}")
    result = subprocess.run(args, cwd=tmp_path, env=env, capture_output=True, text=True)
    if label and label.strip():
        assert result.returncode == 0, result.stderr
        assert result.stdout.splitlines()[-10:] == [
            "host",
            "alembic",
            "-c",
            "host/alembic.ini",
            "revision",
            "--autogenerate",
            "-m",
            "add foo",
            "--head",
            "users@head",
        ]
    else:
        assert result.returncode != 0
        assert "LABEL=" in result.stderr
        assert "--autogenerate" not in result.stdout
