"""Readers of generated frontend files must never observe a partial rewrite."""

import json
import sys
from pathlib import Path

import pytest
from simple_module_hosting.frontend.assets import ModuleAssets
from simple_module_hosting.frontend.manifest import _write_if_changed
from simple_module_hosting.frontend.module_tsconfig import write_module_tsconfigs


@pytest.mark.skipif(sys.platform == "win32", reason="Windows readers do not grant delete sharing")
@pytest.mark.parametrize("kind", ["manifest", "tsconfig"])
def test_generated_file_replacement_preserves_open_readers(tmp_path: Path, kind: str):
    if kind == "manifest":
        path = tmp_path / "modules.manifest.json"

        def write():
            _write_if_changed(path, '{"Orders": "/orders/pages"}\n')

    else:
        package = tmp_path / "orders"
        package.mkdir()
        (package / "widget.ts").write_text("export {}")
        asset = ModuleAssets("Orders", "orders", package, None, None, None)
        (path,) = write_module_tsconfigs([asset], tmp_path)

        def write():
            write_module_tsconfigs([asset], tmp_path)

    path.write_text("old content")
    with path.open(encoding="utf-8") as reader:
        write()
        assert reader.read() == "old content"
    assert isinstance(json.loads(path.read_text()), dict)
    stamp = path.stat().st_mtime_ns
    write()
    assert path.stat().st_mtime_ns == stamp
    assert not list(path.parent.glob("*.tmp"))


def test_failed_replacement_keeps_original_and_removes_temporary_file(tmp_path, monkeypatch):
    path = tmp_path / "modules.assets.json"
    path.write_text("old content")

    def fail_replace(self, target):
        raise OSError("replacement failed")

    monkeypatch.setattr(Path, "replace", fail_replace)
    with pytest.raises(OSError, match="replacement failed"):
        _write_if_changed(path, "new content")
    assert path.read_text() == "old content"
    assert list(tmp_path.iterdir()) == [path]
