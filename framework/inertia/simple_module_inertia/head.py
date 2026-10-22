"""Server-rendered ``<head>`` (#535 step 1).

A view passes ``head=Head(...)`` to ``inertia.render``. The first (document)
response renders it into ``<head>`` so crawlers and link unfurlers that do not
run JS see the title, description, Open Graph tags, canonical and JSON-LD. The
same tags travel as the ``_head`` prop (a list of HTML strings); Inertia v3's
``serverHead`` option re-emits them on every client visit.

Every tag carries a ``data-inertia`` key, which is how Inertia's client head
manager recognises an element it may replace instead of appending a duplicate.
Nothing here trusts the request ``Host``: relative URLs are joined onto
``SiteInfo.base_url`` (the operator-set public URL), or dropped when it is unset.
"""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any
from urllib.parse import urljoin, urlsplit

from jinja2.utils import htmlsafe_json_dumps
from markupsafe import escape
from pydantic import BaseModel, Field, field_validator, model_validator
from starlette.requests import Request

HEAD_PROP = "_head"
TITLE_SEPARATOR = " — "
_KEY_ATTR = "data-inertia"
_KEY_RE = re.compile(r"^[a-z][a-z0-9_.:-]*$")
_ROBOTS_RE = re.compile(r"^[a-z][a-z0-9, -]*$")
_URL_KEYS = frozenset({"url", "image", "image:url", "image:secure_url", "video", "audio"})
_OG = "og"
_TWITTER = "twitter"


@dataclass(frozen=True)
class SiteInfo:
    """Per-request site facts the head needs; supplied by the host."""

    base_url: str = ""
    app_name: str = ""


SiteResolver = Callable[[Request], SiteInfo]


def _is_http_url(value: str) -> bool:
    parts = urlsplit(value)
    return parts.scheme in ("http", "https") and bool(parts.netloc)


def _is_site_path(value: str) -> bool:
    return value.startswith("/") and not value.startswith("//") and "\\" not in value


def _check_url(value: str, *, what: str) -> str:
    value = value.strip()
    if _is_http_url(value) or _is_site_path(value):
        return value
    raise ValueError(f"{what} must be an http(s) URL or a site-relative path")


class Head(BaseModel):
    """Head metadata for one page. URLs are http(s) only (or site-relative)."""

    title: str = ""
    description: str = ""
    canonical: str = ""
    robots: str = ""
    og: dict[str, str] = Field(default_factory=dict)
    twitter: dict[str, str] = Field(default_factory=dict)
    json_ld: list[dict[str, Any]] = Field(default_factory=list)

    @field_validator("canonical")
    @classmethod
    def _canonical(cls, value: str) -> str:
        return _check_url(value, what="canonical") if value else value

    @field_validator("robots")
    @classmethod
    def _robots(cls, value: str) -> str:
        value = value.strip().lower()
        if value and not _ROBOTS_RE.match(value):
            raise ValueError("robots must be a comma-separated list of directives")
        return value

    @model_validator(mode="after")
    def _check_maps(self) -> Head:
        for prefix, mapping in ((_OG, self.og), (_TWITTER, self.twitter)):
            for key, value in mapping.items():
                if not _KEY_RE.match(key):
                    raise ValueError(f"invalid {prefix} key {key!r}")
                if key in _URL_KEYS:
                    _check_url(value, what=f"{prefix}:{key}")
        return self


def _absolute(value: str, base_url: str) -> str | None:
    """``value`` as an absolute URL, or ``None`` when it needs a base we lack."""
    if _is_http_url(value):
        return value
    return urljoin(base_url.rstrip("/") + "/", value.lstrip("/")) if base_url else None


def _tag(name: str, key: str, attrs: dict[str, str]) -> str:
    parts = " ".join(f'{k}="{escape(v)}"' for k, v in {_KEY_ATTR: key, **attrs}.items())
    return f"<{name} {parts}>"


def _meta_tags(head: Head, base_url: str) -> list[str]:
    tags: list[str] = []
    if head.description:
        tags.append(
            _tag("meta", "sm-description", {"name": "description", "content": head.description})
        )
    if head.robots:
        tags.append(_tag("meta", "sm-robots", {"name": "robots", "content": head.robots}))
    canonical = _absolute(head.canonical, base_url) if head.canonical else None
    if canonical:
        tags.append(_tag("link", "sm-canonical", {"rel": "canonical", "href": canonical}))
    og = dict(head.og)
    if head.title:
        og.setdefault("title", head.title)
    if head.description:
        og.setdefault("description", head.description)
    if canonical:
        og.setdefault("url", canonical)
    for prefix, attr, mapping in ((_OG, "property", og), (_TWITTER, "name", head.twitter)):
        for key, value in mapping.items():
            if key in _URL_KEYS:
                resolved = _absolute(value, base_url)
                if resolved is None:
                    continue
                value = resolved
            full = f"{prefix}:{key}"
            tags.append(_tag("meta", f"sm-{prefix}-{key}", {attr: full, "content": value}))
    return tags


def head_tags(head: Head, site: SiteInfo) -> list[str]:
    """The escaped HTML tags for ``head``, each carrying a ``data-inertia`` key."""
    tags: list[str] = []
    if head.title:
        title = head.title.strip()
        full = f"{title}{TITLE_SEPARATOR}{site.app_name}" if site.app_name else title
        tags.append(f'<title {_KEY_ATTR}="">{escape(full)}</title>')
    tags.extend(_meta_tags(head, site.base_url))
    for index, doc in enumerate(head.json_ld):
        # htmlsafe_json_dumps escapes < > & ' so ``</script>`` and ``<!--`` in a
        # value cannot end the element or open an HTML comment.
        body = htmlsafe_json_dumps(doc)
        tags.append(
            f'<script {_KEY_ATTR}="sm-jsonld-{index}" type="application/ld+json">{body}</script>'
        )
    return tags
