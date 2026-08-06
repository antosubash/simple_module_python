"""Gate page rendering, escaping, and next-target sanitisation."""

from __future__ import annotations

import pytest
from site_lock.page import render_unlock_page, safe_next


@pytest.mark.parametrize(
    "raw",
    [
        None,
        "",
        "//evil.example/path",
        "https://evil.example",
        "http://evil.example",
        "/\\evil.example",
        "evil",
        "/ok\r\nSet-Cookie: x=1",
    ],
)
def test_safe_next_rejects_offsite_and_injection(raw: str | None) -> None:
    assert safe_next(raw) == "/"


@pytest.mark.parametrize("raw", ["/", "/dashboard/", "/users/me"])
def test_safe_next_allows_same_site_paths(raw: str) -> None:
    assert safe_next(raw) == raw


def test_message_is_html_escaped() -> None:
    html = render_unlock_page(message="<script>alert(1)</script>")
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_error_is_rendered_and_escaped() -> None:
    html = render_unlock_page(error="Bad <b>password</b>")
    assert "&lt;b&gt;" in html
    assert "<b>password</b>" not in html


def test_no_error_block_when_no_error() -> None:
    assert 'role="alert"' not in render_unlock_page()


def test_next_is_embedded_as_a_hidden_field() -> None:
    html = render_unlock_page(next_url="/dashboard/")
    assert 'name="next"' in html
    assert "/dashboard/" in html


def test_offsite_next_is_neutralised_in_the_form() -> None:
    html = render_unlock_page(next_url="//evil.example")
    assert "evil.example" not in html


def test_page_is_self_contained() -> None:
    html = render_unlock_page()
    # No external assets: a locked site must serve exactly one document.
    assert "<script" not in html.lower()
    assert "src=" not in html.lower()
    assert 'rel="stylesheet"' not in html.lower()
    assert 'method="post"' in html.lower()
    assert 'name="password"' in html
