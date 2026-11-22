"""The installed plugin isolates a consumer project before its conftest loads."""

import os
import subprocess
import sys


def _pytest(project):
    env = os.environ.copy()
    for key in (
        "PYTEST_ADDOPTS",
        "PYTEST_XDIST_WORKER",
        "SM_PROJECT_ROOT",
        "SM_VITE_DEV_URL",
        "SM_PUBLIC_BASE_URL",
        "SM_TEST_DOTENV_LEAK",
        "SM_DEBUG",
    ):
        env.pop(key, None)
    return subprocess.run(
        [sys.executable, "-m", "pytest", "-q"],
        cwd=project,
        env=env,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_plugin_ignores_project_dotenv_before_conftest_and_in_fixtures(tmp_path):
    (tmp_path / "pyproject.toml").write_text("[tool.pytest.ini_options]\n")
    (tmp_path / ".env").write_text(
        "SM_VITE_DEV_URL=http://localhost:9999\n"
        "SM_PUBLIC_BASE_URL=https://dotenv.example\n"
        "SM_TEST_DOTENV_LEAK=leaked\n"
    )
    (tmp_path / "conftest.py").write_text(
        "from simple_module_hosting.settings import Settings\n"
        "assert Settings().vite_dev_url == 'http://localhost:5050'\n"
    )
    (tmp_path / "test_settings.py").write_text(
        "import os\n"
        "import pytest\n"
        "from simple_module_core.settings.dotenv import load_dotenv_into_environ\n"
        "from simple_module_hosting.settings import Settings\n"
        "def test_settings(settings, monkeypatch, tmp_path):\n"
        "    load_dotenv_into_environ()\n"
        "    assert 'SM_TEST_DOTENV_LEAK' not in os.environ\n"
        "    assert settings.vite_dev_url == 'http://localhost:5050'\n"
        "    assert settings.public_base_url == ''\n"
        "    monkeypatch.setenv('SM_PUBLIC_BASE_URL', 'https://shell.example')\n"
        "    assert Settings().public_base_url == 'https://shell.example'\n"
        "    monkeypatch.setenv('SM_VITE_DEV_URL', 'http://localhost:8888')\n"
        "    assert Settings().vite_dev_url == 'http://localhost:8888'\n"
        "    custom = tmp_path / 'custom.env'\n"
        "    custom.write_text('SM_DEBUG=true\\n')\n"
        "    assert Settings(_env_file=custom).debug is True\n"
        "@pytest.fixture\n"
        "def vite_export(monkeypatch):\n"
        "    monkeypatch.setenv('SM_VITE_DEV_URL', 'http://localhost:8888')\n"
        "def test_pinned_vite(vite_export, settings):\n"
        "    assert settings.vite_dev_url == 'http://localhost:5050'\n"
    )
    result = _pytest(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout


def test_plugin_imports_duplicate_basenames_with_conftests_and_plugins(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.pytest.ini_options]\npythonpath = ["."]\n')
    (tmp_path / "conftest.py").write_text('pytest_plugins = ["support"]\n')
    (tmp_path / "support.py").write_text(
        "import pytest\n@pytest.fixture\ndef shared():\n    return 42\n"
    )
    for area in ("alpha", "beta"):
        directory = tmp_path / area
        directory.mkdir()
        (directory / "conftest.py").write_text(
            f"import pytest\n@pytest.fixture\ndef area():\n    return '{area}'\n"
        )
        (directory / "test_same.py").write_text(
            f"def test_value(shared, area):\n    assert (shared, area) == (42, '{area}')\n"
        )
    result = _pytest(tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "2 passed" in result.stdout
