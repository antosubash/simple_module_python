"""Unit tests for the dependency-free ``.env`` parser.

``parse_dotenv`` is invoked by the diagnostics CLI, the users-module
bootstrap, and every worker entrypoint before settings construction — a bug
here is hard to debug because it manifests as "the setting just isn't there".
"""

from __future__ import annotations

import pathlib
from pathlib import Path

import pytest
from simple_module_core.dotenv import (
    env_bool,
    env_str,
    find_env_file,
    load_dotenv_into_environ,
    parse_dotenv,
)


class TestParseDotenv:
    def test_missing_file_returns_empty(self, tmp_path):
        assert parse_dotenv(tmp_path / "absent.env") == {}

    def test_basic_keys(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("FOO=bar\nBAZ=qux\n", encoding="utf-8")
        assert parse_dotenv(env) == {"FOO": "bar", "BAZ": "qux"}

    def test_blank_lines_and_comments_ignored(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "# leading comment\n\nFOO=bar\n   \n# inline-style # not stripped\nBAZ=qux\n",
            encoding="utf-8",
        )
        assert parse_dotenv(env) == {"FOO": "bar", "BAZ": "qux"}

    def test_quotes_stripped_matching_pairs(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text(
            "A=\"double\"\nB='single'\nC=plain\n",
            encoding="utf-8",
        )
        assert parse_dotenv(env) == {"A": "double", "B": "single", "C": "plain"}

    def test_value_with_equals_keeps_remainder(self, tmp_path):
        """KEY=foo=bar=baz must parse as KEY -> "foo=bar=baz" (first ``=`` splits).

        Tokens, JWTs and database URLs frequently contain ``=`` — losing them
        would silently break SMTP/JWT configuration in prod.
        """
        env = tmp_path / ".env"
        env.write_text("URL=postgresql://u:p=raw@h/db\n", encoding="utf-8")
        assert parse_dotenv(env) == {"URL": "postgresql://u:p=raw@h/db"}

    def test_whitespace_around_key_and_value_trimmed(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("  KEY  =  value  \n", encoding="utf-8")
        assert parse_dotenv(env) == {"KEY": "value"}

    def test_no_equals_line_skipped(self, tmp_path):
        env = tmp_path / ".env"
        env.write_text("VALID=1\nbroken line without equals\nANOTHER=2\n", encoding="utf-8")
        assert parse_dotenv(env) == {"VALID": "1", "ANOTHER": "2"}

    def test_default_path_uses_sm_project_root(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("ROOTED=yes\n", encoding="utf-8")
        monkeypatch.setenv("SM_PROJECT_ROOT", str(tmp_path))
        assert parse_dotenv() == {"ROOTED": "yes"}

    def test_default_path_falls_back_to_cwd(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("CWD_KEY=present\n", encoding="utf-8")
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        assert parse_dotenv() == {"CWD_KEY": "present"}


class TestFindEnvFile:
    def test_home_lookup_failure_skips_boundary_check(self, tmp_path, monkeypatch):
        """``Path.home()`` raises ``RuntimeError`` when ``$HOME`` is unset and
        the UID has no passwd entry (rootless containers). ``find_env_file``
        must not propagate that — it just skips the home-boundary check and
        keeps walking.
        """

        def _raise_runtime_error() -> Path:
            raise RuntimeError("no home directory for this uid")

        monkeypatch.setattr(pathlib.Path, "home", staticmethod(_raise_runtime_error))
        monkeypatch.delenv("SM_PROJECT_ROOT", raising=False)
        monkeypatch.chdir(tmp_path)
        assert find_env_file() == Path(".env")


class TestLoadDotenvIntoEnviron:
    def test_setdefault_semantics_preserves_existing_env(self, tmp_path, monkeypatch):
        """Real ``os.environ`` wins over file values — same precedence as uvicorn."""
        (tmp_path / ".env").write_text("KEY=from_file\n", encoding="utf-8")
        monkeypatch.setenv("KEY", "from_shell")
        load_dotenv_into_environ(tmp_path / ".env")
        import os

        assert os.environ["KEY"] == "from_shell"

    def test_loads_missing_keys(self, tmp_path, monkeypatch):
        (tmp_path / ".env").write_text("NEW_KEY_FOR_LOAD_TEST=picked_up\n", encoding="utf-8")
        monkeypatch.delenv("NEW_KEY_FOR_LOAD_TEST", raising=False)
        load_dotenv_into_environ(tmp_path / ".env")
        import os

        assert os.environ["NEW_KEY_FOR_LOAD_TEST"] == "picked_up"


class TestEnvStr:
    def test_returns_value(self, monkeypatch):
        monkeypatch.setenv("X", "ok")
        assert env_str("X", "default") == "ok"

    def test_returns_default_when_unset(self, monkeypatch):
        monkeypatch.delenv("X", raising=False)
        assert env_str("X", "default") == "default"

    def test_returns_default_for_whitespace_only(self, monkeypatch):
        monkeypatch.setenv("X", "   ")
        assert env_str("X", "default") == "default"


class TestEnvBool:
    @pytest.mark.parametrize("raw", ["1", "true", "TRUE", "yes", "y", "on", "  T  "])
    def test_truthy(self, raw, monkeypatch):
        monkeypatch.setenv("X", raw)
        assert env_bool("X", default=False) is True

    @pytest.mark.parametrize("raw", ["0", "false", "FALSE", "no", "n", "off"])
    def test_falsy(self, raw, monkeypatch):
        monkeypatch.setenv("X", raw)
        assert env_bool("X", default=True) is False

    def test_unset_uses_default(self, monkeypatch):
        monkeypatch.delenv("X", raising=False)
        assert env_bool("X", default=True) is True
        assert env_bool("X", default=False) is False

    def test_unparseable_uses_default(self, monkeypatch):
        monkeypatch.setenv("X", "definitely-not-a-bool")
        assert env_bool("X", default=True) is True
