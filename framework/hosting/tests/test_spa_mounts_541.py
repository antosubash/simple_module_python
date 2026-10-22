"""Legacy SPA mounts (GH #541): deep-link fallback, auth, overlap diagnostic."""

from __future__ import annotations

import json
import re

import pytest
from simple_module_core import ModuleBase, ModuleMeta
from simple_module_core.diagnostics._spa_mount import check_spa_mount_overlaps
from simple_module_core.spa_mount import SpaMount
from simple_module_hosting import app_builder

_HTML = {"Accept": "text/html"}
_INDEX = "<html><body>legacy spa</body></html>"


def _module(mounts: list[SpaMount], name: str = "LegacyFake") -> ModuleBase:
    class FakeSpaModule(ModuleBase):
        meta = ModuleMeta(name=name)

        def spa_mounts(self):
            return mounts

    return FakeSpaModule()


@pytest.fixture
def dist(tmp_path):
    root = tmp_path / "dist"
    (root / "assets").mkdir(parents=True)
    (root / "index.html").write_text(_INDEX, encoding="utf-8")
    (root / "assets" / "index-3f9a8c21b.js").write_text("console.log(1)", encoding="utf-8")
    (tmp_path / "secret.txt").write_text("TOPSECRET-CONTENT", encoding="utf-8")
    return root


@pytest.fixture(autouse=True)
def _mount_legacy(monkeypatch, dist, tmp_path):
    public_dist = tmp_path / "public_dist"
    public_dist.mkdir()
    (public_dist / "index.html").write_text("<html>open</html>", encoding="utf-8")
    real = app_builder.discover_modules

    def fake(enabled=None, *, strict=False):
        extra = _module(
            [
                SpaMount("/legacy", dist),
                SpaMount("/openspa/", public_dist, auth="public"),
            ]
        )
        return [*real(enabled=enabled, strict=strict), extra]

    monkeypatch.setattr(app_builder, "discover_modules", fake)


async def test_deep_link_serves_index(authenticated_client):
    r = await authenticated_client.get("/legacy/a/b/c", headers=_HTML)
    assert r.status_code == 200
    assert "legacy spa" in r.text
    assert r.headers["cache-control"] == "no-cache"


async def test_root_serves_index_and_head_works(authenticated_client):
    assert (await authenticated_client.get("/legacy/", headers=_HTML)).status_code == 200
    assert (await authenticated_client.head("/legacy/a/b", headers=_HTML)).status_code == 200


async def test_missing_asset_is_404_not_html(authenticated_client):
    r = await authenticated_client.get("/legacy/missing.js", headers=_HTML)
    assert r.status_code == 404
    assert "legacy spa" not in r.text


async def test_extensionless_without_html_accept_is_404(authenticated_client):
    r = await authenticated_client.get("/legacy/a/b", headers={"Accept": "application/json"})
    assert r.status_code == 404


async def test_hashed_asset_is_immutable(authenticated_client):
    r = await authenticated_client.get("/legacy/assets/index-3f9a8c21b.js")
    assert r.status_code == 200
    assert "immutable" in r.headers["cache-control"]


@pytest.mark.parametrize(
    "path",
    [
        "/legacy/../secret.txt",
        "/legacy/%2e%2e/secret.txt",
        "/legacy/..%2fsecret",
        "/legacy/%2e%2e/x",
    ],
)
async def test_traversal_is_refused(authenticated_client, path):
    r = await authenticated_client.get(path, headers=_HTML)
    assert "TOPSECRET-CONTENT" not in r.text
    assert "legacy spa" not in r.text


async def test_write_methods_refused(authenticated_client):
    r = await authenticated_client.post("/legacy/a")
    assert r.status_code in (404, 405)


async def test_required_mount_redirects_anonymous_to_login(client):
    r = await client.get("/legacy/a/b/c", headers=_HTML)
    assert r.status_code in (302, 303, 307)
    assert "login" in r.headers["location"]


async def test_public_mount_is_reachable_anonymously(client):
    r = await client.get("/openspa/x/y", headers=_HTML)
    assert r.status_code == 200
    assert "open" in r.text


async def test_public_mount_post_is_still_gated(client):
    r = await client.post("/openspa/x")
    assert r.status_code != 200


async def test_native_prefixes_shared_prop(client):
    r = await client.get("/users/login", headers=_HTML)
    found = re.search(
        r'<script data-page="[^"]*" type="application/json">(.*?)</script>', r.text, re.DOTALL
    )
    assert found is not None
    page = json.loads(found.group(1))
    props = page["props"]
    assert "/legacy/" in props.get("nativePrefixes", [])


def test_overlap_with_router_prefix_is_an_error(tmp_path):
    clash = _module([SpaMount("/api/legacy", tmp_path)], name="Clash")
    codes = [d.code for d in check_spa_mount_overlaps([clash])]
    assert codes == ["SM032"]


def test_overlap_between_two_mounts_is_an_error(tmp_path):
    a = _module([SpaMount("/legacy", tmp_path)], name="A")
    b = _module([SpaMount("/legacy/inner", tmp_path)], name="B")
    assert any(d.code == "SM032" for d in check_spa_mount_overlaps([a, b]))


def test_sibling_prefix_is_not_an_overlap(tmp_path):
    mod = _module([SpaMount("/legacy", tmp_path), SpaMount("/legacy2", tmp_path)])
    assert check_spa_mount_overlaps([mod]) == []


async def test_overlap_fails_boot(settings, monkeypatch, tmp_path):
    from simple_module_hosting._spa_mount import SpaMountError

    (tmp_path / "index.html").write_text("x", encoding="utf-8")
    real = app_builder.discover_modules
    bad = _module([SpaMount("/admin/legacy", tmp_path)], name="Bad")
    monkeypatch.setattr(
        app_builder,
        "discover_modules",
        lambda enabled=None, *, strict=False: [*real(enabled=enabled, strict=strict), bad],
    )
    with pytest.raises(SpaMountError, match="SM032"):
        app_builder.create_app(settings)


def test_invalid_prefix_and_auth_rejected(tmp_path):
    with pytest.raises(ValueError):
        SpaMount("legacy", tmp_path)
    with pytest.raises(ValueError):
        SpaMount("/legacy", tmp_path, auth="nope")


async def test_traversal_segment_refused_by_the_mount_itself(dist):
    from simple_module_hosting._spa_mount import SpaStaticFiles
    from starlette.exceptions import HTTPException

    files = SpaStaticFiles(directory=dist, index="index.html")
    scope = {"method": "GET", "headers": [(b"accept", b"text/html")]}
    for path in ("../secret", "a/../../secret", "a\\..\\secret"):
        with pytest.raises(HTTPException) as exc:
            await files.get_response(path, scope)
        assert exc.value.status_code == 404
