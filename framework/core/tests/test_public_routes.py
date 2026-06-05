"""Tests for PublicRouteRegistry — method-aware anonymous-access rules.

The registry is the extension point modules use (via
``ModuleBase.register_public_routes``) to declare routes the auth layer must
let through unauthenticated. Unlike the legacy provider ``get_public_paths``
contract, a rule can be scoped to specific HTTP methods so a read route nested
under a mutation-bearing prefix can be exempted without opening the mutations.
"""

from __future__ import annotations

from simple_module_core.public_routes import PublicRoute, PublicRouteRegistry


class TestPublicRouteMatching:
    def test_prefix_matches_any_subpath(self):
        route = PublicRoute("/api/gis/stac")
        assert route.matches("GET", "/api/gis/stac")
        assert route.matches("GET", "/api/gis/stac/collections")
        assert not route.matches("GET", "/api/gis/datasets")

    def test_exact_matches_only_full_path(self):
        route = PublicRoute("/api/gis/catalog/search", kind="exact")
        assert route.matches("GET", "/api/gis/catalog/search")
        assert not route.matches("GET", "/api/gis/catalog/search/extra")

    def test_suffix_matches_path_tail(self):
        route = PublicRoute("/tilejson", kind="suffix")
        assert route.matches("GET", "/api/gis/datasets/42/tilejson")
        assert not route.matches("GET", "/api/gis/datasets/42/visibility")

    def test_regex_is_anchored_at_start(self):
        route = PublicRoute(r"/api/gis/datasets/[^/]+/tilejson$", kind="regex")
        assert route.matches("GET", "/api/gis/datasets/42/tilejson")
        assert not route.matches("GET", "/api/gis/datasets/42/tilejson/extra")
        assert not route.matches("GET", "/prefix/api/gis/datasets/42/tilejson")

    def test_methods_none_matches_every_verb(self):
        route = PublicRoute("/api/gis/stac")
        for method in ("GET", "POST", "PATCH", "DELETE"):
            assert route.matches(method, "/api/gis/stac")

    def test_methods_restrict_to_listed_verbs(self):
        route = PublicRoute("/api/gis/datasets/", methods={"GET"})
        assert route.matches("GET", "/api/gis/datasets/42/tilejson")
        assert not route.matches("PATCH", "/api/gis/datasets/42/visibility")
        assert not route.matches("POST", "/api/gis/datasets/42/reprocess")

    def test_method_matching_is_case_insensitive(self):
        route = PublicRoute("/api/gis/stac", methods={"get"})
        assert route.matches("GET", "/api/gis/stac")


class TestPublicRouteRegistry:
    def test_empty_registry_matches_nothing(self):
        registry = PublicRouteRegistry()
        assert not registry.matches("GET", "/api/gis/stac")

    def test_add_prefix(self):
        registry = PublicRouteRegistry()
        registry.add_prefix("/api/gis/ogc/")
        assert registry.matches("GET", "/api/gis/ogc/collections")
        assert not registry.matches("GET", "/api/gis/datasets")

    def test_add_exact(self):
        registry = PublicRouteRegistry()
        registry.add_exact("/api/gis/catalog/search")
        assert registry.matches("POST", "/api/gis/catalog/search")
        assert not registry.matches("POST", "/api/gis/catalog/search/x")

    def test_add_regex_with_method(self):
        registry = PublicRouteRegistry()
        registry.add_regex(r"/api/gis/datasets/[^/]+/tilejson$", methods={"GET"})
        assert registry.matches("GET", "/api/gis/datasets/7/tilejson")
        assert not registry.matches("PATCH", "/api/gis/datasets/7/tilejson")

    def test_matches_is_true_if_any_route_matches(self):
        registry = PublicRouteRegistry()
        registry.add_prefix("/api/gis/ogc/")
        registry.add_exact("/api/gis/catalog/search")
        assert registry.matches("GET", "/api/gis/ogc/tiles")
        assert registry.matches("GET", "/api/gis/catalog/search")

    def test_routes_exposes_registered_rules(self):
        registry = PublicRouteRegistry()
        registry.add_prefix("/a")
        registry.add_exact("/b")
        assert len(registry.routes) == 2
        assert all(isinstance(r, PublicRoute) for r in registry.routes)

    def test_add_accepts_a_prebuilt_route(self):
        registry = PublicRouteRegistry()
        registry.add(PublicRoute("/api/gis/stac"))
        assert registry.matches("GET", "/api/gis/stac")
