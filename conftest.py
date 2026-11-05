"""Root conftest — intentionally thin.

The shared app/db/client fixtures (``settings``, ``db_state``, ``engine``,
``db_session``, ``app``, ``client``, ``authenticated_client``) live in the
``simple_module_test`` package and are auto-registered via its ``pytest11``
entry point — installing the package is enough, no conftest import needed. They
used to be duplicated here; they were moved so the *published* plugin actually
ships what its README advertises (GH #200), and this repo now dogfoods that
plugin like any consumer would.

Add genuinely repo-local fixtures here if the need arises; shared ones belong in
``framework/testing/simple_module_test/fixtures.py``.
"""

from __future__ import annotations
