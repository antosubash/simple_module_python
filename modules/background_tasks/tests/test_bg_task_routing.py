"""GH #447/#448/#450: task_config routing, tuning settings, per-worker subset."""

from __future__ import annotations

import logging
import sys
import types

import pytest
from background_tasks import celery_app
from background_tasks.settings import BackgroundTasksSettings
from background_tasks.task_routing import (
    ModuleTaskConfig,
    load_task_config,
    merge_routes,
    select_packages,
)


def _pkg(monkeypatch, name: str, *, config: dict | None = None, tasks: dict | None = None):
    """Install fake ``name`` / ``name.task_config`` / ``name.tasks`` modules."""
    monkeypatch.setitem(sys.modules, name, types.ModuleType(name))
    if config is not None:
        mod = types.ModuleType(f"{name}.task_config")
        for k, v in config.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, f"{name}.task_config", mod)
    if tasks is not None:
        mod = types.ModuleType(f"{name}.tasks")
        for k, v in tasks.items():
            setattr(mod, k, v)
        monkeypatch.setitem(sys.modules, f"{name}.tasks", mod)


def _settings(**kw) -> BackgroundTasksSettings:
    return BackgroundTasksSettings(task_always_eager=True, **kw)


class TestLoadTaskConfig:
    def test_reads_routes_queues_and_beat(self, monkeypatch):
        _pkg(
            monkeypatch,
            "tc_a",
            config={
                "TASK_ROUTES": {"tc_a.*": "heavy"},
                "QUEUES": {"heavy"},
                "BEAT_SCHEDULE": {"x": {"task": "tc_a.x", "schedule": 5}},
            },
        )
        cfg = load_task_config("tc_a")
        assert cfg is not None
        assert cfg.routes == {"tc_a.*": "heavy"}
        assert cfg.queues == frozenset({"heavy"})
        assert cfg.beat_schedule == {"x": {"task": "tc_a.x", "schedule": 5}}

    def test_none_without_task_config(self, monkeypatch):
        _pkg(monkeypatch, "tc_none")
        assert load_task_config("tc_none") is None

    def test_broken_task_config_surfaces(self, monkeypatch):
        _pkg(monkeypatch, "tc_bad")
        import importlib

        real = importlib.import_module

        def fake(name, *a, **k):
            if name == "tc_bad.task_config":
                raise ModuleNotFoundError("No module named 'dep'", name="dep")
            return real(name, *a, **k)

        monkeypatch.setattr(importlib, "import_module", fake)
        with pytest.raises(ModuleNotFoundError):
            load_task_config("tc_bad")


class TestMergeRoutes:
    def test_first_module_wins_and_warns(self, caplog):
        configs = {
            "b": ModuleTaskConfig("b", routes={"shared.*": "qb"}),
            "a": ModuleTaskConfig("a", routes={"shared.*": "qa", "a.*": {"queue": "qa2"}}),
        }
        with caplog.at_level(logging.WARNING):
            routes, info = merge_routes(configs, {})
        assert routes == {"shared.*": "qa", "a.*": {"queue": "qa2"}}
        assert {"pattern": "shared.*", "queue": "qa", "module": "a"} in info
        assert {"pattern": "a.*", "queue": "qa2", "module": "a"} in info
        assert "shared.*" in caplog.text and "a" in caplog.text and "b" in caplog.text

    def test_override_wins_and_is_attributed(self):
        configs = {"a": ModuleTaskConfig("a", routes={"a.*": "qa"})}
        routes, info = merge_routes(configs, {"a.*": "other"})
        assert routes == {"a.*": "other"}
        assert info == [{"pattern": "a.*", "queue": "other", "module": "override"}]


class TestSelectPackages:
    CONFIGS = {  # noqa: RUF012
        "light": ModuleTaskConfig("light", queues=frozenset({"default"})),
        "heavy": ModuleTaskConfig("heavy", queues=frozenset({"gpu"})),
    }
    PKGS = ["heavy", "light", "plain"]  # noqa: RUF012

    def pick(self, **kw):
        return select_packages(self.PKGS, self.CONFIGS, _settings(**kw))

    def test_everything_by_default(self):
        assert self.pick() == self.PKGS

    def test_queue_overlap(self):
        assert self.pick(worker_queues=["gpu"]) == ["heavy"]

    def test_module_without_queues_defaults_to_default_queue(self):
        assert self.pick(worker_queues=["default"]) == ["light", "plain"]

    def test_include_beats_queue_filter_and_exclude_beats_include(self):
        assert self.pick(worker_queues=["gpu"], include_modules=["light"]) == ["heavy", "light"]
        assert self.pick(include_modules=["light"], exclude_modules=["light"]) == [
            "heavy",
            "plain",
        ]


class TestSettings:
    def test_csv_env(self, monkeypatch):
        monkeypatch.setenv("SM_BG_TASKS_WORKER_QUEUES", "gpu, default")
        monkeypatch.setenv("SM_BG_TASKS_EXCLUDE_MODULES", "a,b")
        s = BackgroundTasksSettings()
        assert s.worker_queues == ["gpu", "default"]
        assert s.exclude_modules == ["a", "b"]

    def test_tuning_defaults_are_none(self):
        s = BackgroundTasksSettings()
        for name in (
            *celery_app._TUNING_KEYS,
            "visibility_timeout_seconds",
        ):
            assert getattr(s, name) is None


class TestBuildCelery:
    def _build(self, monkeypatch, packages, **kw):
        monkeypatch.setattr(celery_app, "_discover_task_packages", lambda: packages)
        return celery_app.build_celery(_settings(**kw))

    def test_routes_tuning_and_overrides_land_in_conf(self, monkeypatch):
        _pkg(monkeypatch, "bc_a", config={"TASK_ROUTES": {"bc_a.*": "heavy"}})
        c = self._build(
            monkeypatch,
            ["bc_a"],
            task_routes_override={"bc_a.fast": "quick"},
            visibility_timeout_seconds=7200,
            worker_max_tasks_per_child=10,
            worker_max_memory_per_child_kb=5000,
            task_reject_on_worker_lost=True,
            task_soft_time_limit=30,
            task_time_limit=60,
            worker_concurrency=3,
            celery_overrides={"task_acks_late": False, "result_expires": 99},
        )
        assert c.conf.task_routes == {"bc_a.*": "heavy", "bc_a.fast": "quick"}
        assert c.conf.broker_transport_options == {"visibility_timeout": 7200}
        assert c.conf.worker_max_tasks_per_child == 10
        assert c.conf.worker_max_memory_per_child == 5000
        assert c.conf.task_reject_on_worker_lost is True
        assert c.conf.task_soft_time_limit == 30
        assert c.conf.task_time_limit == 60
        assert c.conf.worker_concurrency == 3
        # celery_overrides is applied last, over the framework's own defaults.
        assert c.conf.task_acks_late is False
        assert c.conf.result_expires == 99

    def test_unset_tuning_leaves_celery_defaults(self, monkeypatch):
        c = self._build(monkeypatch, [])
        assert c.conf.worker_concurrency is None or c.conf.worker_concurrency == 0
        assert not (c.conf.broker_transport_options or {}).get("visibility_timeout")

    def test_task_config_beat_wins_over_tasks_beat(self, monkeypatch):
        _pkg(
            monkeypatch,
            "bc_b",
            config={"BEAT_SCHEDULE": {"job": {"task": "bc_b.new", "schedule": 1}}},
            tasks={"BEAT_SCHEDULE": {"job": {"task": "bc_b.old", "schedule": 1}}},
        )
        c = self._build(monkeypatch, ["bc_b"])
        assert c.conf.beat_schedule["job"]["task"] == "bc_b.new"

    def test_subset_filters_autodiscover_and_beat_import(self, monkeypatch):
        _pkg(
            monkeypatch,
            "bc_heavy",
            config={"QUEUES": {"gpu"}},
            tasks={"BEAT_SCHEDULE": {"heavy-job": {"task": "bc_heavy.t", "schedule": 1}}},
        )
        _pkg(
            monkeypatch,
            "bc_light",
            config={"QUEUES": {"default"}},
            tasks={"BEAT_SCHEDULE": {"light-job": {"task": "bc_light.t", "schedule": 1}}},
        )
        discovered: list[list[str]] = []
        monkeypatch.setattr(
            "celery.Celery.autodiscover_tasks",
            lambda self, pkgs=None, **kw: discovered.append(list(pkgs)),
        )
        c = self._build(monkeypatch, ["bc_heavy", "bc_light"], worker_queues=["default"])
        assert discovered == [["bc_light"]]
        assert "light-job" in c.conf.beat_schedule
        assert "heavy-job" not in c.conf.beat_schedule

    def test_describe_routes(self, monkeypatch):
        _pkg(monkeypatch, "bc_c", config={"TASK_ROUTES": {"bc_c.*": "q"}})
        monkeypatch.setattr(celery_app, "_discover_task_packages", lambda: ["bc_c"])
        s = BackgroundTasksSettings(task_routes_override={"x.*": "y"})
        assert celery_app.describe_routes(s) == [
            {"pattern": "bc_c.*", "queue": "q", "module": "bc_c"},
            {"pattern": "x.*", "queue": "y", "module": "override"},
        ]
