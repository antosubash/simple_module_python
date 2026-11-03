"""A static SPA shell gets the request's CSP nonce on its script tags (#785).

The production script policy is ``'nonce-…' 'strict-dynamic'``; a CSP3 browser
then ignores ``'self'``, so a shell served byte-for-byte could not run its own
entry script.
"""

from __future__ import annotations

from simple_module_hosting._spa_mount import SpaStaticFiles

_SHELL = (
    '<html><head><script type="module" src="/legacy/assets/index-3f9a8c21b.js"></script>'
    '<script nonce="kept">window.a = 1</script></head><body></body></html>'
)


def _scope(nonce: str | None) -> dict:
    state = {"csp_nonce": nonce} if nonce else {}
    return {"type": "http", "method": "GET", "path": "/", "headers": [], "state": state}


async def test_index_scripts_carry_the_request_nonce(tmp_path) -> None:
    (tmp_path / "index.html").write_text(_SHELL, encoding="utf-8")
    spa = SpaStaticFiles(directory=tmp_path, index="index.html")

    response = await spa.get_response("", _scope("abc123"))

    body = response.body.decode()
    assert '<script nonce="abc123" type="module" src="/legacy/assets/' in body
    assert '<script nonce="kept">' in body  # an author's own nonce is left alone
    # The nonce changes per response, so no validator may revive an old shell.
    assert "etag" not in response.headers
    assert "last-modified" not in response.headers
    assert response.headers["content-type"].startswith("text/html")


async def test_without_a_nonce_the_shell_is_served_unchanged(tmp_path) -> None:
    (tmp_path / "index.html").write_text(_SHELL, encoding="utf-8")
    spa = SpaStaticFiles(directory=tmp_path, index="index.html")

    response = await spa.get_response("", _scope(None))

    assert "etag" in response.headers  # still the plain FileResponse
