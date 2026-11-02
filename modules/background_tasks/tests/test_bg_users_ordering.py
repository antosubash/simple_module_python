"""``background_tasks`` no longer depends on ``users``, and order does not matter.

The dependency was declared but never used (GH #501). The one thing this module
reads that ``users`` contributes is the invalidation channel list, which every
module registers in ``register_invalidations`` before any ``on_startup`` runs,
so sorting ``BackgroundTasks`` ahead of ``Users`` changes nothing.
"""

from __future__ import annotations

from background_tasks.module import BackgroundTasksModule
from simple_module_core.discovery import topological_sort
from users.module import UsersModule
from users.session_revocation import CHANNEL


def test_users_is_not_a_dependency():
    assert "Users" not in BackgroundTasksModule.meta.depends_on


def test_sorts_without_users_installed():
    ordered = topological_sort([BackgroundTasksModule()])
    assert [m.meta.name for m in ordered] == ["BackgroundTasks"]


async def test_users_channel_is_subscribed_when_background_tasks_sorts_first(app):
    names = [m.meta.name for m in app.state.sm.modules]
    assert names.index("BackgroundTasks") < names.index(UsersModule.meta.name)
    # What the Redis invalidation transport fans out at on_startup.
    assert CHANNEL in app.state.sm.invalidation.channels
