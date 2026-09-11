from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from pydantic import BaseModel
from simple_module_inertia.page import (
    PropEncodingError,
    build_page,
    encode_page,
    to_relative_url,
)
from simple_module_inertia.resolve import ResolvedProps


class TestToRelativeUrl:
    @pytest.mark.parametrize(
        ("absolute", "expected"),
        [
            ("http://py.simplemodule.dev/", "/"),
            ("https://py.simplemodule.dev/dashboard/", "/dashboard/"),
            ("http://host:8000/files?q=logo&page=2", "/files?q=logo&page=2"),
            ("http://host:8000", "/"),
        ],
    )
    def test_keeps_only_path_and_query(self, absolute: str, expected: str) -> None:
        assert to_relative_url(absolute) == expected

    @pytest.mark.parametrize("relative", ["/", "/admin/users/", "/files?q=1"])
    def test_a_relative_url_is_unchanged(self, relative: str) -> None:
        assert to_relative_url(relative) == relative


class TestBuildPage:
    def test_required_fields_and_errors_always_prop(self) -> None:
        page = build_page(
            component="Users/Index",
            resolved=ResolvedProps(props={"users": [1]}),
            url="http://host:8000/admin/users/",
            version="v1",
            errors={},
        )
        assert page == {
            "component": "Users/Index",
            "props": {"users": [1], "errors": {}},
            "url": "/admin/users/",
            "version": "v1",
        }

    def test_conditional_fields_appear_only_when_set(self) -> None:
        resolved = ResolvedProps(
            props={},
            deferred={"default": ["feed"]},
            merge=["posts"],
            prepend=["notices"],
            deep_merge=["settings"],
            match_on=["posts.id"],
            once={"plans": {"prop": "plans", "expiresAt": None}},
            scroll={
                "posts": {
                    "pageName": "page",
                    "currentPage": 1,
                    "previousPage": None,
                    "nextPage": 2,
                    "reset": False,
                }
            },
            shared=["auth"],
        )
        page = build_page(
            component="C",
            resolved=resolved,
            url="/",
            version="v",
            errors={"email": "taken"},
            encrypt_history=True,
            clear_history=True,
            preserve_fragment=True,
        )
        assert page["deferredProps"] == {"default": ["feed"]}
        assert page["mergeProps"] == ["posts"]
        assert page["prependProps"] == ["notices"]
        assert page["deepMergeProps"] == ["settings"]
        assert page["matchPropsOn"] == ["posts.id"]
        assert page["onceProps"] == {"plans": {"prop": "plans", "expiresAt": None}}
        assert page["scrollProps"]["posts"]["nextPage"] == 2
        assert page["sharedProps"] == ["auth"]
        assert page["encryptHistory"] is True
        assert page["clearHistory"] is True
        assert page["preserveFragment"] is True
        assert page["props"]["errors"] == {"email": "taken"}

    def test_false_flags_and_empty_metadata_are_omitted(self) -> None:
        page = build_page(component="C", resolved=ResolvedProps(), url="/", version="v", errors={})
        for absent in (
            "deferredProps",
            "mergeProps",
            "prependProps",
            "deepMergeProps",
            "matchPropsOn",
            "onceProps",
            "scrollProps",
            "sharedProps",
            "encryptHistory",
            "clearHistory",
            "preserveFragment",
        ):
            assert absent not in page


class TestEncodePage:
    def test_rich_values_become_json_safe(self) -> None:
        class Settings(BaseModel):
            media_root: Path

        page = {
            "component": "C",
            "props": {
                "when": datetime(2026, 9, 10, tzinfo=UTC),
                "id": uuid.UUID(int=1),
                "price": Decimal("1.50"),
                "path": Path("/srv/media"),
                "settings": Settings(media_root=Path("/m")),
            },
            "url": "/",
            "version": "v",
        }
        encoded = encode_page(page)
        assert encoded["props"]["when"].startswith("2026-09-10")
        assert encoded["props"]["id"] == "00000000-0000-0000-0000-000000000001"
        assert encoded["props"]["price"] == 1.5
        assert encoded["props"]["path"] == "/srv/media"
        assert encoded["props"]["settings"] == {"media_root": "/m"}

    def test_an_unencodable_prop_names_its_path(self) -> None:
        class Opaque:
            # No __dict__, so jsonable_encoder's dict()/vars() fallbacks both fail.
            __slots__ = ()

        page = {
            "component": "C",
            "props": {"user": {"avatar": Opaque()}},
            "url": "/",
            "version": "v",
        }
        with pytest.raises(PropEncodingError, match=r"props\.user\.avatar"):
            encode_page(page)
