"""GH #199: a consumer module can register Celery beat entries by shipping a
``tasks.py`` that exports a module-level ``BEAT_SCHEDULE`` dict — ``build_celery``
merges them into the beat schedule, worker-safe and declarative (no reliance on
the broken ``on_after_configure`` signal).
"""

from __future__ import annotations

import sys
import types

from background_tasks import celery_app
from background_tasks.constants import INTERNAL_TASK_SWEEP_STUCK
from background_tasks.settings import BackgroundTasksSettings


def _install_fake_module(monkeypatch, pkg: str, beat_schedule: dict | None) -> None:
    """Register ``pkg`` + ``pkg.tasks`` in sys.modules for the test duration.

    When ``beat_schedule`` is None the tasks module ships no ``BEAT_SCHEDULE``
    attribute (a module that has tasks but no periodic work).
    """
    parent = types.ModuleType(pkg)
    tasks = types.ModuleType(f"{pkg}.tasks")
    if beat_schedule is not None:
        tasks.BEAT_SCHEDULE = beat_schedule
    monkeypatch.setitem(sys.modules, pkg, parent)
    monkeypatch.setitem(sys.modules, f"{pkg}.tasks", tasks)


class TestCollectModuleBeatSchedules:
    def test_merges_module_beat_schedule(self, monkeypatch):
        entry = {"task": "fakepkg.daily", "schedule": 3600}
        _install_fake_module(monkeypatch, "fakepkg", {"fakepkg-daily": entry})

        merged = celery_app._collect_module_beat_schedules(["fakepkg"])
        assert merged == {"fakepkg-daily": entry}

    def test_skips_package_without_beat_schedule_attr(self, monkeypatch):
        _install_fake_module(monkeypatch, "nobeat", None)
        assert celery_app._collect_module_beat_schedules(["nobeat"]) == {}

    def test_skips_package_without_tasks_module(self):
        # A package with no importable ``.tasks`` submodule is ignored, not fatal.
        assert celery_app._collect_module_beat_schedules(["definitely_not_a_real_pkg"]) == {}

    def test_ignores_non_dict_beat_schedule(self, monkeypatch):
        _install_fake_module(monkeypatch, "weird", None)
        sys.modules["weird.tasks"].BEAT_SCHEDULE = ["not", "a", "dict"]
        assert celery_app._collect_module_beat_schedules(["weird"]) == {}


class TestBuildCeleryBeatSchedule:
    def test_module_beat_entry_lands_in_schedule(self, monkeypatch):
        entry = {"task": "fakeinv.generate_recurring", "schedule": 3600}
        _install_fake_module(monkeypatch, "fakeinv", {"fakeinv-gen-daily": entry})
        monkeypatch.setattr(
            celery_app, "_discover_task_packages", lambda: ["background_tasks", "fakeinv"]
        )

        app = celery_app.build_celery(BackgroundTasksSettings(task_always_eager=True))
        schedule = app.conf.beat_schedule

        assert schedule["fakeinv-gen-daily"] == entry
        # The two built-in entries still ship.
        assert "background-tasks-sweep-stuck" in schedule
        assert "background-tasks-purge-old" in schedule

    def test_builtin_entries_win_on_name_clash(self, monkeypatch):
        # A module that reuses a built-in entry name must not clobber it.
        rogue = {"task": "rogue.evil", "schedule": 1}
        _install_fake_module(monkeypatch, "rogue", {"background-tasks-sweep-stuck": rogue})
        monkeypatch.setattr(
            celery_app, "_discover_task_packages", lambda: ["background_tasks", "rogue"]
        )

        app = celery_app.build_celery(BackgroundTasksSettings(task_always_eager=True))
        assert (
            app.conf.beat_schedule["background-tasks-sweep-stuck"]["task"]
            == INTERNAL_TASK_SWEEP_STUCK
        )
