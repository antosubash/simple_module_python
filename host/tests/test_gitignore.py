"""Generated TypeScript projects remain ignored when the path is a symlink."""

import subprocess
from pathlib import Path


def test_module_tsconfig_symlink_is_ignored(tmp_path):
    root = Path(__file__).resolve().parents[2]
    (tmp_path / ".gitignore").write_text((root / ".gitignore").read_text())
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True, capture_output=True)
    generated = tmp_path / "host/client_app/.module-tsconfig"
    generated.parent.mkdir(parents=True)
    generated.symlink_to("/dev/null")
    result = subprocess.run(
        ["git", "check-ignore", "--no-index", "host/client_app/.module-tsconfig"],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=10,
    )
    assert result.returncode == 0, result.stdout + result.stderr
