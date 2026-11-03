"""Fluent assertions and follow-up requests for Inertia page responses."""

from __future__ import annotations

import json
from collections.abc import Callable, Sized
from copy import copy
from html.parser import HTMLParser
from typing import Any, Self

import httpx


class _PageScript(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=False)
        self.collecting = False
        self.chunks: list[str] = []
        self.page_json: str | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag == "script":
            self.collecting = (
                attributes.get("data-page") == "app"
                and attributes.get("type") == "application/json"
            )
            if self.collecting:
                self.chunks = []

    def handle_data(self, data: str) -> None:
        if self.collecting:
            self.chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag == "script" and self.collecting:
            self.page_json = "".join(self.chunks)
            self.collecting = False


_MISSING = object()


class InertiaPage:
    """A page's props and protocol metadata, independent of its transport."""

    def __init__(self, page: dict[str, Any]) -> None:
        self.component: str = page["component"]
        self.props: dict[str, Any] = page["props"]
        self.url: str = page["url"]
        self.version: str | None = page.get("version", "")
        self.deferred_props: dict[str, list[str]] = page.get("deferredProps", {})
        self.merge_props: list[str] = page.get("mergeProps", [])
        self.prepend_props: list[str] = page.get("prependProps", [])
        self.deep_merge_props: list[str] = page.get("deepMergeProps", [])
        self.match_props_on: list[str] = page.get("matchPropsOn", [])
        self.once_props: dict[str, Any] = page.get("onceProps", {})
        self.scroll_props: dict[str, Any] = page.get("scrollProps", {})
        self.shared_props: list[str] = page.get("sharedProps", [])
        self.rescued_props: list[str] = page.get("rescuedProps", [])
        self.encrypt_history: bool = page.get("encryptHistory", False)
        self.clear_history: bool = page.get("clearHistory", False)

    @classmethod
    def from_response(cls, response: httpx.Response) -> Self:
        """Read an X-Inertia JSON response or the document's app page script."""
        try:
            if response.headers.get("X-Inertia", "").lower() == "true":
                page = response.json()
            else:
                parser = _PageScript()
                parser.feed(response.text)
                if parser.page_json is None:
                    raise ValueError("no <script data-page='app' type='application/json'>")
                page = json.loads(parser.page_json)
        except (ValueError, UnicodeError) as exc:
            raise AssertionError(f"Not a valid Inertia response: {exc}") from exc
        assert isinstance(page, dict), "Not a valid Inertia response: page must be an object"
        assert isinstance(page.get("component"), str) and isinstance(page.get("url"), str), (
            f"Not a valid Inertia response: expected component and url strings; "
            f"available keys: {list(page)}"
        )
        assert isinstance(page.get("props"), dict), (
            f"Not a valid Inertia response: expected props object; available keys: {list(page)}"
        )
        return cls(page)

    def assert_component(self, name: str) -> Self:
        assert self.component == name, f"Expected component {name!r}, got {self.component!r}"
        return self

    def assert_url(self, path: str) -> Self:
        assert self.url == path, f"Expected url {path!r}, got {self.url!r}"
        return self

    def assert_version(self, version: str | None) -> Self:
        assert self.version == version, f"Expected version {version!r}, got {self.version!r}"
        return self

    def _lookup(self, path: str) -> tuple[Any, str]:
        value: Any = self.props
        for part in path.split("."):
            if isinstance(value, dict):
                available = f"Available keys: {list(value)}"
                value = value.get(part, _MISSING)
            elif isinstance(value, list):
                available = f"Available indices: {list(range(len(value)))}"
                index = int(part) if part.isascii() and part.isdigit() else -1
                value = value[index] if 0 <= index < len(value) else _MISSING
            else:
                return _MISSING, f"Available keys: none ({value!r} is not a container)"
            if value is _MISSING:
                return _MISSING, available
        return value, f"Available keys: {list(self.props)}"

    def _value(self, path: str) -> Any:
        value, available = self._lookup(path)
        assert value is not _MISSING, f"Missing prop {path!r}. {available}"
        return value

    def has(self, path: str, count: int | None = None) -> Self:
        """Assert presence, optionally checking the length of a prop."""
        value = self._value(path)
        if count is not None:
            assert isinstance(value, Sized), f"Prop {path!r} has no count: {value!r}"
            assert len(value) == count, f"Expected prop {path!r} count {count}, got {len(value)}"
        return self

    def missing(self, path: str) -> Self:
        value, available = self._lookup(path)
        assert value is _MISSING, f"Prop {path!r} is present: {value!r}. {available}"
        return self

    def where(self, path: str, expected_or_predicate: Any | Callable[[Any], bool]) -> Self:
        value = self._value(path)
        if callable(expected_or_predicate):
            assert expected_or_predicate(value), f"Prop {path!r} failed predicate; got {value!r}"
        else:
            assert value == expected_or_predicate, (
                f"Expected prop {path!r} to equal {expected_or_predicate!r}, got {value!r}"
            )
        return self

    def deferred(self, group: str, *props: str) -> Self:
        """Assert a deferred group exists and contains the named props."""
        assert group in self.deferred_props, (
            f"Missing deferred group {group!r}. Available groups: {list(self.deferred_props)}"
        )
        for prop in props:
            assert prop in self.deferred_props[group], (
                f"Missing deferred prop {prop!r} in {group!r}. "
                f"Available props: {self.deferred_props[group]}"
            )
        return self

    async def _reload(
        self, client: httpx.AsyncClient, header: str, props: tuple[str, ...]
    ) -> InertiaPage:
        response = await client.get(
            self.url,
            headers={
                "X-Inertia": "true",
                "X-Inertia-Version": self.version or "",
                "X-Inertia-Partial-Component": self.component,
                header: ",".join(props),
            },
        )
        return self.from_response(response)

    async def reload_only(self, client: httpx.AsyncClient, *props: str) -> InertiaPage:
        """Request only these props; the result is the unmerged response page."""
        return await self._reload(client, "X-Inertia-Partial-Data", props)

    async def reload_except(self, client: httpx.AsyncClient, *props: str) -> InertiaPage:
        """Request a partial page excluding these props."""
        return await self._reload(client, "X-Inertia-Partial-Except", props)

    async def load_deferred(
        self, client: httpx.AsyncClient, group: str | None = None
    ) -> InertiaPage:
        """Load one deferred group, or all groups when omitted."""
        if group is not None:
            self.deferred(group)
            props = self.deferred_props[group]
        else:
            props = [prop for group_props in self.deferred_props.values() for prop in group_props]
        if not props:
            return copy(self)
        return await self.reload_only(client, *props)


def inertia_page(response: httpx.Response) -> InertiaPage:
    """Short form of :meth:`InertiaPage.from_response`."""
    return InertiaPage.from_response(response)
