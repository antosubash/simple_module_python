"""A published Vite config dependency must run as JavaScript in Node."""

import json
import shutil
import subprocess
from pathlib import Path


def test_published_plugin_loads_without_typescript_stripping(tmp_path, require_cli_asset):
    root = Path(__file__).resolve().parents[4]
    package = root / "packages/vite-plugin"
    require_cli_asset(shutil.which("node") is not None, "node absent")
    require_cli_asset((package / "dist/index.js").is_file(), "build the Vite plugin first")
    installed = tmp_path / "node_modules/@simple-module-py/vite-plugin"
    installed.mkdir(parents=True)
    shutil.copy2(package / "package.json", installed / "package.json")
    metadata = json.loads((package / "package.json").read_text())
    for name in metadata["files"]:
        source = package / name
        if source.is_dir():
            shutil.copytree(source, installed / name)
        else:
            shutil.copy2(source, installed / name)
    (tmp_path / "node_modules/vite").symlink_to(root / "node_modules/vite")
    result = subprocess.run(
        [
            "node",
            "--input-type=module",
            "-e",
            "import { simpleModule } from '@simple-module-py/vite-plugin'; "
            "console.log(typeof simpleModule);",
        ],
        cwd=tmp_path,
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "function"
