"""Doctor runs on real data — no fixtures anywhere in the payload.

Every panel on the screen has to name its source: the checks come from the
diagnostics run the boot kept, the migrations from Alembic's script directory,
the dev-server rows from settings and the request, the worker from the
background_tasks module when it is installed.
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

import httpx
import pytest
from dashboard.doctor import CHECKS, MIGRATION_CHECK_ID
from dashboard.stats import invalidate_stats_cache
from simple_module_core.diagnostics import Diagnostic, DiagnosticLevel
from simple_module_test.fixtures import forge_session_cookie

_DOCTOR = "/admin/doctor/"
_RERUN = "/admin/doctor/rerun"
_INERTIA = {"X-Inertia": "true", "X-Inertia-Version": "1.0"}


@pytest.fixture(autouse=True)
def _clear_stats_cache():
    invalidate_stats_cache()
    yield
    invalidate_stats_cache()


async def _props(client: httpx.AsyncClient) -> dict:
    resp = await client.get(_DOCTOR, headers=_INERTIA)
    assert resp.status_code == 200, resp.text
    return resp.json()["props"]


@pytest.fixture
async def plain_user_client(app):
    """A signed-in non-admin — the re-run action must be as guarded as the page."""
    from users.models import User

    async with app.state.sm.db.session_factory() as session:
        user = User(
            email="plain-rerun@example.com", hashed_password="x", is_active=True, is_verified=True
        )
        session.add(user)
        await session.commit()
        user_id = str(user.id)

    signed = forge_session_cookie(app.state.sm.settings.secret_key, {"user_id": user_id})
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
        cookies={"session": signed},
    ) as client:
        yield client


class TestChecks:
    async def test_every_declared_check_is_reported(self, authenticated_client) -> None:
        props = await _props(authenticated_client)

        assert [c["id"] for c in props["checks"]] == [c.id for c in CHECKS]
        assert props["stats"]["checks_total"] == len(CHECKS)

    async def test_a_clean_run_passes_every_check(self, app, authenticated_client) -> None:
        app.state.sm.diagnostics.runner = list
        app.state.sm.diagnostics.results = []

        props = await _props(authenticated_client)

        assert {c["status"] for c in props["checks"]} == {"pass"}
        assert props["stats"]["checks_passing"] == len(CHECKS)

    async def test_a_finding_lands_on_the_check_that_owns_its_code(
        self, app, authenticated_client
    ) -> None:
        app.state.sm.diagnostics.runner = list
        app.state.sm.diagnostics.results = [
            Diagnostic(
                level=DiagnosticLevel.WARNING,
                code="SM011",
                message="Table 'demo_thing' has no migration",
                module_name="Demo",
                suggestion="Run make migrations",
            )
        ]

        props = await _props(authenticated_client)
        checks = {c["id"]: c for c in props["checks"]}

        drift = checks[MIGRATION_CHECK_ID]
        assert drift["status"] == "warn"
        assert drift["findings"][0]["code"] == "SM011"
        assert drift["findings"][0]["module"] == "Demo"
        # Deck's "Fix" copies a command rather than running Alembic from a
        # web request.
        assert drift["command"] == "make migrations"
        assert props["stats"]["checks_passing"] == len(CHECKS) - 1
        for check_id, check in checks.items():
            if check_id != MIGRATION_CHECK_ID:
                assert check["status"] == "pass", check

    async def test_a_check_with_no_remediation_command_offers_no_action(
        self, authenticated_client
    ) -> None:
        """Five of the eight have no single line that fixes them. A "Fix" that
        copied ``make doctor`` would be a button that re-runs what you are
        already looking at, so those rows carry no command at all."""
        checks = {c["id"]: c for c in (await _props(authenticated_client))["checks"]}

        assert checks["metadata"]["command"] is None
        assert checks["coupling"]["command"] is None
        assert checks["pages"]["command"] == "make gen-pages"
        assert checks["locales"]["command"] == "make gen-i18n"

    async def test_an_error_finding_fails_its_check(self, app, authenticated_client) -> None:
        app.state.sm.diagnostics.runner = list
        app.state.sm.diagnostics.results = [
            Diagnostic(
                level=DiagnosticLevel.ERROR,
                code="SM009",
                message="framework imports a plugin",
                module_name="Core",
            )
        ]

        checks = {c["id"]: c for c in (await _props(authenticated_client))["checks"]}

        assert [c["status"] for c in checks.values()].count("fail") == 1

    async def test_info_findings_do_not_fail_a_check(self, app, authenticated_client) -> None:
        """SM007 says a module overrides no hooks — a remark, not a defect."""
        app.state.sm.diagnostics.runner = list
        app.state.sm.diagnostics.results = [
            Diagnostic(
                level=DiagnosticLevel.INFO,
                code="SM007",
                message="overrides no hooks",
                module_name="Demo",
            )
        ]

        props = await _props(authenticated_client)

        assert props["stats"]["checks_passing"] == len(CHECKS)

    async def test_outside_development_the_checks_are_unavailable(
        self, authenticated_client
    ) -> None:
        """The test app runs in ``testing``, where diagnostics are skipped at
        boot — the screen must say so rather than claim eight clean passes."""
        props = await _props(authenticated_client)

        assert props["checks_available"] is False
        assert props["stats"]["checks_passing"] == 0
        assert all(c["status"] == "unknown" for c in props["checks"])


class TestMigrations:
    async def test_rows_come_from_the_alembic_script_directory(self, authenticated_client) -> None:
        from simple_module_hosting.migrations import list_migrations

        props = await _props(authenticated_client)

        assert [row["id"] for row in props["migrations"]] == [
            row["id"] for row in list_migrations()
        ]

    async def test_the_fixtures_stamp_head_so_every_row_reads_applied(
        self, authenticated_client
    ) -> None:
        props = await _props(authenticated_client)

        assert props["migrations"], "the repository ships migrations"
        assert all(row["applied"] for row in props["migrations"])
        assert props["stats"]["pending_migrations"] == 0


class TestDevServer:
    async def test_vite_and_api_come_from_settings_and_the_request(
        self, app, authenticated_client
    ) -> None:
        props = await _props(authenticated_client)
        rows = {row["name"]: row["value"] for row in props["dev_server"]["rows"]}

        assert list(rows) == ["vite", "api", "worker"]
        assert rows["vite"] == ":5050"
        assert app.state.sm.settings.vite_dev_url.endswith(":5050")
        # httpx's ASGI transport talks to http://testserver, i.e. the default port.
        assert rows["api"] == ":80"

    async def test_the_worker_is_a_dash_when_nothing_reports_one(
        self, authenticated_client
    ) -> None:
        props = await _props(authenticated_client)
        rows = {row["name"]: row["value"] for row in props["dev_server"]["rows"]}

        assert rows["worker"] == "—"

    async def test_the_worker_comes_from_the_background_tasks_snapshot(
        self, app, authenticated_client, monkeypatch
    ) -> None:
        """Read duck-typed off ``app.state.background_tasks`` so the dashboard
        never imports the module — it is optional."""
        monkeypatch.setattr(
            app.state,
            "background_tasks",
            SimpleNamespace(
                last_worker_snapshot=SimpleNamespace(
                    workers=[SimpleNamespace(hostname="celery@w1", online=True)]
                )
            ),
            raising=False,
        )

        props = await _props(authenticated_client)
        rows = {row["name"]: row["value"] for row in props["dev_server"]["rows"]}

        assert rows["worker"] == "celery@w1"

    async def test_an_offline_worker_is_not_reported_as_the_fleet(
        self, app, authenticated_client, monkeypatch
    ) -> None:
        """A worker the broker remembers but that no longer answers is not
        something this row may claim is running."""
        monkeypatch.setattr(
            app.state,
            "background_tasks",
            SimpleNamespace(
                last_worker_snapshot=SimpleNamespace(
                    workers=[
                        SimpleNamespace(hostname="celery@gone", online=False),
                        SimpleNamespace(hostname="celery@w2", online=True),
                    ]
                )
            ),
            raising=False,
        )

        props = await _props(authenticated_client)
        rows = {row["name"]: row["value"] for row in props["dev_server"]["rows"]}

        assert rows["worker"] == "celery@w2"


class TestStats:
    async def test_the_four_deck_figures_are_real(self, app, authenticated_client) -> None:
        props = await _props(authenticated_client)
        stats = props["stats"]

        assert stats["modules_loaded"] == len(app.state.sm.modules)
        assert stats["python_version"].startswith(
            f"{sys.version_info.major}.{sys.version_info.minor}"
        )
        assert stats["pending_migrations"] == app.state.migration["pending_count"]
        assert 0 <= stats["checks_passing"] <= stats["checks_total"]

    async def test_the_transcript_panel_has_a_routed_page_count(self, authenticated_client) -> None:
        props = await _props(authenticated_client)

        assert props["pages_routed"] >= 1


class TestRerun:
    async def test_it_reruns_the_diagnostics_and_redirects_back(
        self, app, authenticated_client
    ) -> None:
        calls: list[int] = []

        def runner():
            calls.append(1)
            return []

        app.state.sm.diagnostics.runner = runner

        resp = await authenticated_client.post(_RERUN, follow_redirects=False)

        assert resp.status_code == 303, resp.text
        assert resp.headers["location"] == _DOCTOR
        assert calls == [1]

    async def test_a_non_admin_cannot_rerun(self, plain_user_client) -> None:
        resp = await plain_user_client.post(_RERUN, follow_redirects=False)

        assert resp.status_code == 403, resp.text[:400]
