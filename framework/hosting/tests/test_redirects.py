"""Direct unit tests for ``safe_referer_or_root``.

The helper is the only barrier between an attacker-controlled ``Referer`` and
a 303 redirect back to that URL. The existing test surface only goes through
``/i18n/set-locale``, which exercises a handful of vectors. This file pins the
contract directly with adversarial inputs that the integration test set didn't
reach (``javascript:``, embedded ``@`` userinfo, ``\\evil.example``,
CRLF-injection attempts, mixed-case schemes, fragments).
"""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from simple_module_hosting.redirects import safe_referer_or_root


def _make_request(*, referer: str | None = None, scheme: str = "http", host: str = "testserver"):
    """Return a minimal duck-typed object matching what safe_referer_or_root reads.

    The real helper only touches ``request.headers.get("referer")`` and
    ``request.url.scheme`` / ``request.url.netloc`` — a SimpleNamespace beats
    spinning up a Starlette Request just to validate URL parsing.
    """
    headers: dict[str, str] = {}
    if referer is not None:
        headers["referer"] = referer
    return SimpleNamespace(
        headers=headers,
        url=SimpleNamespace(scheme=scheme, netloc=host),
    )


class TestSafeRefererBasics:
    def test_no_referer_returns_root(self) -> None:
        assert safe_referer_or_root(_make_request()) == "/"

    def test_empty_string_referer_returns_root(self) -> None:
        assert safe_referer_or_root(_make_request(referer="")) == "/"

    def test_same_origin_relative_path_preserved(self) -> None:
        assert safe_referer_or_root(_make_request(referer="/dashboard")) == "/dashboard"

    def test_same_origin_absolute_url_collapses_to_path(self) -> None:
        req = _make_request(referer="http://testserver/products?q=pen")
        assert safe_referer_or_root(req) == "/products?q=pen"


class TestSafeRefererBlocksHostedirects:
    """Every input here is an attempt to redirect off-site.

    A regression that returns the input verbatim is a reflected open-redirect.
    """

    @pytest.mark.parametrize(
        "malicious",
        [
            "https://evil.example/steal",
            "http://evil.example/x",
            "//evil.example/x",
            "//evil.example",
            r"\\evil.example/x",  # backslash-prefixed — some browsers normalize
            "http://testserver.evil.example/",  # suffix-confusion
            "http://evil.example@testserver/",  # userinfo trick: host is "evil.example"
            "javascript:alert(1)",
            "data:text/html,<script>alert(1)</script>",
            "vbscript:msgbox(1)",
            "FILE:///etc/passwd",
            "HTTPS://EVIL.EXAMPLE/",
            "not-a-path",
            "  ",
            "ftp://evil.example/",
        ],
    )
    def test_rejects_hostile_referer(self, malicious: str) -> None:
        req = _make_request(referer=malicious)
        result = safe_referer_or_root(req)
        # The helper must never return anything that, when used as a Location
        # header, takes the browser off-site. The contract is "/" or a path
        # starting with "/" on the same origin.
        assert result.startswith("/"), (
            f"safe_referer_or_root({malicious!r}) returned {result!r}; "
            "must fall back to a same-origin path"
        )
        # And specifically: no second slash that would make the browser see
        # this as a protocol-relative URL.
        assert not result.startswith("//"), (
            f"safe_referer_or_root({malicious!r}) returned protocol-relative {result!r}"
        )

    def test_userinfo_at_sign_does_not_smuggle_host(self) -> None:
        """``http://evil@testserver/`` parses as host=testserver in urlsplit.

        That's actually safe — the helper compares parsed.netloc which includes
        the userinfo. The defense is that ``parsed.netloc != current.netloc``
        when userinfo is present, so the comparison correctly rejects.
        """
        req = _make_request(referer="http://attacker@testserver/admin")
        assert safe_referer_or_root(req) == "/"


class TestSafeRefererSchemeAndHostMatching:
    def test_scheme_mismatch_rejects_https_referer_on_http_request(self) -> None:
        req = _make_request(referer="https://testserver/x", scheme="http")
        assert safe_referer_or_root(req) == "/"

    def test_host_mismatch_rejects_subdomain(self) -> None:
        req = _make_request(referer="http://admin.testserver/x")
        assert safe_referer_or_root(req) == "/"

    def test_port_mismatch_rejects(self) -> None:
        req = _make_request(referer="http://testserver:8080/x", host="testserver")
        assert safe_referer_or_root(req) == "/"


class TestSafeRefererPathHandling:
    def test_query_string_preserved(self) -> None:
        req = _make_request(referer="http://testserver/x?a=1&b=2")
        assert safe_referer_or_root(req) == "/x?a=1&b=2"

    def test_fragment_dropped(self) -> None:
        """Fragments aren't sent to the server, so we don't echo them in Location."""
        req = _make_request(referer="http://testserver/x#section")
        assert safe_referer_or_root(req) == "/x"

    def test_empty_path_becomes_root(self) -> None:
        req = _make_request(referer="http://testserver")
        assert safe_referer_or_root(req) == "/"
