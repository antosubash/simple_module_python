from simple_module_cli.scaffolding import create_host


def test_scaffolded_app_excludes_spa_mounts_from_link_interception(tmp_path):
    dest = tmp_path / "demo"
    create_host(dest, name="demo-host", modules=[])
    app_tsx = (dest / "client_app" / "app.tsx").read_text(encoding="utf-8")
    assert "readNativePrefixes" in app_tsx
    assert "startSpaLinkInterception({ exclude" in app_tsx
