"""Where `smpy new` runs alembic when it bootstraps a scaffold's first migration.

Split out of test_cli_new_regressions.py to stay under the repo's 300-line cap.
The cwd these run in is the whole point — see GH #262.
"""

from __future__ import annotations

from pathlib import Path


def test_bootstrap_initial_migration_runs_autogenerate_when_versions_empty(
    tmp_path: Path, monkeypatch
) -> None:
    """Issue #135: the post-install hook must call ``alembic revision
    --autogenerate`` when ``migrations/versions/`` holds only ``.gitkeep``."""
    from simple_module_cli import new as new_mod

    host = tmp_path / "host"
    (host / "migrations" / "versions").mkdir(parents=True)
    (host / "migrations" / "versions" / ".gitkeep").touch()

    calls: list[tuple[list[str], Path]] = []

    def fake_run(cmd, *, cwd, check):
        del check
        calls.append((list(cmd), Path(cwd)))

        class _Result:
            returncode = 0

        return _Result()

    monkeypatch.setattr(new_mod.subprocess, "run", fake_run)
    argv = new_mod._alembic_argv(tmp_path, host)
    new_mod._bootstrap_initial_migration(tmp_path, host, argv)
    assert calls, "expected alembic autogenerate to run"
    cmd, cwd = calls[0]
    assert cmd[:7] == [
        "uv",
        "run",
        "--project",
        "host",
        "alembic",
        "-c",
        "host/alembic.ini",
    ]
    assert cmd[7:9] == ["revision", "--autogenerate"]
    # From the project root, never host/ — the same cwd `make migrate` and the
    # app use, so every relative path in the scaffold means one thing. GH #262
    # is now defended in depth (find_env_file walks up, relative sqlite anchors
    # to the project root); this keeps the bootstrap from being the odd one out.
    assert cwd == tmp_path


def test_bootstrap_initial_migration_skips_when_revision_exists(
    tmp_path: Path, monkeypatch
) -> None:
    """If the user has already run ``make migration``, don't clobber their
    revision by autogenerating a second baseline."""
    from simple_module_cli import new as new_mod

    host = tmp_path / "host"
    (host / "migrations" / "versions").mkdir(parents=True)
    (host / "migrations" / "versions" / "0001_initial.py").write_text("# revision\n")

    def fake_run(*_a, **_kw):  # pragma: no cover - must not be called
        raise AssertionError("alembic should not be invoked when a revision exists")

    monkeypatch.setattr(new_mod.subprocess, "run", fake_run)
    new_mod._bootstrap_initial_migration(tmp_path, host, new_mod._alembic_argv(tmp_path, host))


def test_alembic_argv_collapses_for_the_flat_host_layout(tmp_path: Path) -> None:
    """`create-host` puts the host *at* the project root, so there is no
    `host/` segment to point the ini path at."""
    from simple_module_cli import new as new_mod

    assert new_mod._alembic_argv(tmp_path, tmp_path) == [
        "uv",
        "run",
        "alembic",
        "-c",
        "alembic.ini",
    ]
