"""Override rows must be reachable from the audit log.

Every toggle is written to the audit trail (``FeatureFlagOverride`` carries
``AuditMixin``), and the browse screen now says so in its footer. That claim is
only useful if the reader can get back from an audit row to the screen that
produced it — which is what the audit-link registry is for.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import httpx
from feature_flags.constants import (
    AUDIT_LOG_MODULE,
    AUDIT_LOG_VIEW_URL,
    MENU_URL,
    PAGE_BROWSE,
    TABLE_OVERRIDE,
    VIEW_PREFIX,
)
from feature_flags.endpoints.views import _audit_log_url
from feature_flags.models import FeatureFlagOverride
from feature_flags.module import FeatureFlagsModule
from simple_module_core.audit_links import AuditLinkRegistry


def _request_with_modules(*names: str):
    """Minimal stand-in for the parts of ``Request`` the helper reads.

    ``app.state.sm`` is a frozen dataclass, so an installed-module list cannot
    be edited on a live app fixture — and rebuilding the app without the audit
    log module would rebuild every other module with it.
    """
    modules = [SimpleNamespace(meta=SimpleNamespace(name=name)) for name in names]
    state = SimpleNamespace(sm=SimpleNamespace(modules=modules))
    return SimpleNamespace(app=SimpleNamespace(state=state))


def _registered() -> AuditLinkRegistry:
    registry = AuditLinkRegistry()
    FeatureFlagsModule().register_audit_links(registry)
    return registry


def test_override_rows_declare_a_link() -> None:
    link = _registered().get(FeatureFlagOverride.__name__)

    assert link is not None
    assert link.label


async def test_following_the_link_renders_the_flags_screen(
    authenticated_client: httpx.AsyncClient,
) -> None:
    """The template carries an "{id}" the browse route does not declare. That
    is fine — FastAPI ignores query params a handler does not ask for — but it
    is exactly the kind of "fine" that stops being true silently."""
    link = _registered().get(FeatureFlagOverride.__name__)
    assert link is not None
    assert link.url_for("7").startswith(f"{VIEW_PREFIX}/")

    resp = await authenticated_client.get(
        link.url_for("7"), headers={"X-Inertia": "true", "Accept": "application/json"}
    )

    assert resp.status_code == 200, resp.text
    assert resp.json()["component"] == PAGE_BROWSE


def test_link_is_keyed_by_class_name_not_table_name() -> None:
    """``snapshot_changes`` records ``type(obj).__name__``, so a table-name key
    would silently never match — and an unmatched lookup still renders a label,
    which makes the mistake look like it worked."""
    assert _registered().get(TABLE_OVERRIDE) is None


def test_label_key_resolves_in_the_shipped_catalog() -> None:
    link = _registered().get(FeatureFlagOverride.__name__)
    assert link is not None

    catalog = json.loads(
        (Path(__file__).resolve().parents[1] / "feature_flags/locales/en.json").read_text()
    )
    namespace, *path = link.label_key.split(".")
    assert namespace == "feature_flags"
    node = catalog
    for part in path:
        node = node[part]
    assert isinstance(node, str) and node


class TestChangeHistoryLink:
    """The scope card offers "View change history →". Where it points is a
    server decision: the audit log is an installable module, and a link to a
    screen this install does not have is a 404 with extra steps."""

    async def test_browse_offers_the_filtered_audit_log(
        self, authenticated_client: httpx.AsyncClient
    ) -> None:
        resp = await authenticated_client.get(
            MENU_URL, headers={"X-Inertia": "true", "Accept": "application/json"}
        )

        assert resp.status_code == 200, resp.text
        url = resp.json()["props"]["audit_log_url"]
        assert url == f"{AUDIT_LOG_VIEW_URL}?entity_type={FeatureFlagOverride.__name__}"

    def test_link_is_withheld_when_no_audit_log_is_installed(self) -> None:
        assert _audit_log_url(_request_with_modules()) is None

    def test_link_is_offered_once_an_audit_log_is_installed(self) -> None:
        url = _audit_log_url(_request_with_modules(AUDIT_LOG_MODULE))

        assert url == f"{AUDIT_LOG_VIEW_URL}?entity_type={FeatureFlagOverride.__name__}"
