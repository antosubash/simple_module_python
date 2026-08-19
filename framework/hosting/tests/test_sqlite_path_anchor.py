"""Relative SQLite paths must not depend on the process working directory.

``SM_DATABASE_URL=sqlite+aiosqlite:///./host/app.db`` is written relative to
the workspace root. The web process chdirs there, but CLI tools
(``smpy users create-admin``, alembic) run from wherever the operator
happens to be — from ``host/`` the same URL silently pointed at
``host/host/app.db`` and failed with "unable to open database file".

The settings layer now anchors relative sqlite paths on the project root
(``SM_PROJECT_ROOT``, else the directory of the discovered ``.env``), and
discovers the ``.env`` by walking up from the cwd — via the shared
``simple_module_core.dotenv.find_env_file``, so ``parse_dotenv`` consumers
(diagnostics CLI, worker entrypoints, users bootstrap) resolve the same file
— so subdirectory invocations see the same database as the app.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from simple_module_core.dotenv import find_env_file
from simple_module_hosting.bootstrap_settings import _absolutize_sqlite_url


class TestAbsolutize:
    def test_relative_path_resolves_against_anchor(self, tmp_path: Path) -> None:
        url = _absolutize_sqlite_url("sqlite+aiosqlite:///./host/app.db", anchor=tmp_path)
        assert url == f"sqlite+aiosqlite:///{tmp_path / 'host' / 'app.db'}"

    def test_bare_relative_path_resolves(self, tmp_path: Path) -> None:
        url = _absolutize_sqlite_url("sqlite+aiosqlite:///app.db", anchor=tmp_path)
        assert url == f"sqlite+aiosqlite:///{tmp_path / 'app.db'}"

    def test_absolute_path_untouched(self, tmp_path: Path) -> None:
        url = "sqlite+aiosqlite:////var/data/app.db"
        assert _absolutize_sqlite_url(url, anchor=tmp_path) == url

    def test_memory_untouched(self, tmp_path: Path) -> None:
        url = "sqlite+aiosqlite:///:memory:"
        assert _absolutize_sqlite_url(url, anchor=tmp_path) == url

    def test_uri_mode_untouched(self, tmp_path: Path) -> None:
        """SQLite URI-mode paths (shared in-memory DBs) are not file paths."""
        url = "sqlite+aiosqlite:///file:shared?mode=memory&cache=shared&uri=true"
        assert _absolutize_sqlite_url(url, anchor=tmp_path) == url

    def test_bare_scheme_untouched(self, tmp_path: Path) -> None:
        url = "sqlite+aiosqlite://"
        assert _absolutize_sqlite_url(url, anchor=tmp_path) == url

    def test_postgres_untouched(self, tmp_path: Path) -> None:
        url = "postgresql+asyncpg://u:p@localhost/db"
        assert _absolutize_sqlite_url(url, anchor=tmp_path) == url

    def test_query_string_survives(self, tmp_path: Path) -> None:
        url = _absolutize_sqlite_url("sqlite+aiosqlite:///app.db?mode=ro", anchor=tmp_path)
        assert url == f"sqlite+aiosqlite:///{tmp_path / 'app.db'}?mode=ro"


class TestFindEnvFile:
    def test_walks_up_from_subdirectory(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("SM_X=1\n", encoding="utf-8")
        host = tmp_path / "host"
        host.mkdir()
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(host)
        assert find_env_file() == tmp_path / ".env"

    def test_cwd_env_wins_over_parent(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        (tmp_path / ".env").write_text("SM_X=parent\n", encoding="utf-8")
        host = tmp_path / "host"
        host.mkdir()
        (host / ".env").write_text("SM_X=child\n", encoding="utf-8")
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(host)
        assert find_env_file() == host / ".env"

    def test_project_root_env_var_wins(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        root = tmp_path / "elsewhere"
        root.mkdir()
        monkeypatch.setenv("SM_PROJECT_ROOT", str(root))
        monkeypatch.chdir(tmp_path)
        assert find_env_file() == root / ".env"

    def test_no_env_anywhere_falls_back_to_plain_name(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        deep = tmp_path / "a" / "b"
        deep.mkdir(parents=True)
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(deep)
        assert find_env_file() == Path(".env")

    def test_walk_stops_at_repo_boundary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A nested checkout must never load the outer project's .env."""
        (tmp_path / ".env").write_text("SM_X=outer\n", encoding="utf-8")
        inner = tmp_path / "inner_repo"
        inner.mkdir()
        (inner / ".git").write_text("gitdir: elsewhere\n", encoding="utf-8")
        sub = inner / "host"
        sub.mkdir()
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(sub)
        # inner repo has none; outer is off-limits
        assert find_env_file() == Path(".env")

    def test_walk_stops_at_scaffold_boundary(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A fresh scaffold has `.env.example` before any `.git` exists — it
        must bound the walk the same way, or a scaffold nested inside another
        checkout silently boots with the outer project's `.env`."""
        (tmp_path / ".env").write_text("SM_X=outer\n", encoding="utf-8")
        scaffold = tmp_path / "demo_app"
        scaffold.mkdir()
        (scaffold / ".env.example").write_text("SM_X=example\n", encoding="utf-8")
        sub = scaffold / "host"
        sub.mkdir()
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(sub)
        assert find_env_file() == Path(".env")


class TestSettingsIntegration:
    def test_settings_absolutize_via_project_root(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        from simple_module_hosting.settings import Settings

        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        s = Settings(database_url="sqlite+aiosqlite:///./host/app.db")
        assert s.database_url == f"sqlite+aiosqlite:///{tmp_path / 'host' / 'app.db'}"

    def test_settings_leave_memory_url_alone(self) -> None:
        from simple_module_hosting.settings import Settings

        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        assert s.database_url == "sqlite+aiosqlite:///:memory:"

    def test_env_file_discovered_per_instantiation(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The .env is discovered when Settings is built, not when the module
        was first imported — SM_PROJECT_ROOT set after import must load that
        project's .env, so env values and the sqlite anchor can't come from
        two different projects."""
        from simple_module_hosting.settings import Settings

        (tmp_path / ".env").write_text("SM_SECRET_KEY=from-late-project\n", encoding="utf-8")
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        s = Settings(database_url="sqlite+aiosqlite:///:memory:")
        assert s.secret_key == "from-late-project"
