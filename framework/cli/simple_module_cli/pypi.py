"""PyPI release lookup for ``smpy package-update``.

Split out of ``package_update`` so the network half is separately testable and
neither file approaches the 300-line cap. The ``Fetcher`` indirection is what
lets the CLI tests run without touching the network.
"""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from collections.abc import Callable
from typing import Any

from packaging.version import InvalidVersion, Version

__all__ = ["PYPI_URL", "Fetcher", "default_fetcher", "fetch_latest"]

Fetcher = Callable[[str], dict[str, Any]]

PYPI_URL = "https://pypi.org/pypi/{name}/json"

# PEP 440 release segments contain only digits + dots; any letter signals
# a pre/post/dev release (a, b, rc, post, dev). Keep the existing stable filter.
_PRE_RELEASE_RE = re.compile(r"[a-zA-Z]")


def fetch_latest(name: str, *, include_pre: bool, fetcher: Fetcher) -> str | None:
    """Latest non-yanked release of ``name``, or ``None`` if PyPI doesn't have it."""
    try:
        data = fetcher(PYPI_URL.format(name=name))
    except (urllib.error.HTTPError, urllib.error.URLError):
        return None
    releases = data.get("releases") or {}
    candidates: list[str] = []
    for version, files in releases.items():
        if not files:
            continue
        if any(f.get("yanked") for f in files):
            continue
        if not include_pre and _PRE_RELEASE_RE.search(version):
            continue
        try:
            Version(version)
        except InvalidVersion:
            continue
        candidates.append(version)
    if candidates:
        return max(candidates, key=Version)
    if releases:
        return None
    info = data.get("info") or {}
    fallback = info.get("version")
    try:
        Version(fallback)
    except (InvalidVersion, TypeError):
        return None
    return fallback


def default_fetcher(url: str) -> dict[str, Any]:
    with urllib.request.urlopen(url, timeout=10) as resp:
        return json.loads(resp.read().decode("utf-8"))
