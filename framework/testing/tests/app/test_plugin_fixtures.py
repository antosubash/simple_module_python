"""GH #200: the published ``simple_module_test`` plugin must register the
headline fixtures its README/``__init__`` advertise — not just ``fake_event_bus``
+ ``build_test_app``. Before the fix those fixtures lived only in the framework
repo's root ``conftest.py``, so a consumer that installed the plugin (but wasn't
the framework repo) got "fixture not found".
"""

from __future__ import annotations

# The fixtures the plugin promises. Treat this set as the public fixture
# surface — dropping one breaks external modules' suites.
_HEADLINE_FIXTURES = (
    "fake_event_bus",
    "build_test_app",
    "settings",
    "db_state",
    "engine",
    "db_session",
    "app",
    "client",
    "authenticated_client",
)


def _is_pytest_fixture(obj) -> bool:
    """True if ``obj`` was produced by ``@pytest.fixture`` (version-robust).

    pytest >=8.4 returns a ``FixtureFunctionDefinition`` instance; older
    versions left the function in place with a ``_pytestfixturefunction``
    marker attribute. Cover both so this test doesn't pin a pytest version.
    """
    return hasattr(obj, "_pytestfixturefunction") or (
        type(obj).__name__ == "FixtureFunctionDefinition"
    )


def test_plugin_module_exports_every_headline_fixture():
    """Each advertised fixture is a real ``@pytest.fixture`` on the plugin module."""
    import simple_module_test.plugin as plugin

    for name in _HEADLINE_FIXTURES:
        obj = getattr(plugin, name, None)
        assert obj is not None, f"{name!r} is not exported by simple_module_test.plugin"
        # A plain function imported by mistake would not satisfy this.
        assert _is_pytest_fixture(obj), f"{name!r} is not a pytest fixture"


def test_plugin_is_registered_via_pytest11_entry_point(pytestconfig):
    """pytest discovered the plugin through its ``pytest11`` entry point, so a
    consumer gets the fixtures by installing the package alone."""
    assert pytestconfig.pluginmanager.hasplugin("simple_module_test")


async def test_db_session_fixture_injects_without_a_local_conftest(db_session):
    """``db_session`` resolves in this test dir, which has no conftest defining
    it — it can only come from the installed plugin (root conftest no longer
    provides it). Proves the moved fixture is genuinely shipped, not just
    re-exported on paper."""
    from sqlalchemy import text

    result = await db_session.execute(text("SELECT 1"))
    assert result.scalar_one() == 1
