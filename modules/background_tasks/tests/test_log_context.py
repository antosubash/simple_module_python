"""Tests for the Celery log-context layer."""

from __future__ import annotations

import logging
import uuid
from pathlib import Path
from types import SimpleNamespace

import pytest
from background_tasks.log_context import (
    LogContextFilter,
    _signal_tokens,
    bind_task_context,
    get_log_context,
    install_log_filter,
)
from background_tasks.signals import on_task_postrun, on_task_prerun


def _make_record() -> logging.LogRecord:
    return logging.LogRecord(
        name="test",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg="hello",
        args=(),
        exc_info=None,
    )


def _fake_task(name: str) -> SimpleNamespace:
    return SimpleNamespace(name=name)


@pytest.fixture(autouse=True)
def _reset_signal_tokens() -> None:
    """Clear the prerun/postrun bookkeeping in case a prior test panicked."""
    _signal_tokens.clear()


class TestBindTaskContext:
    def test_layers_identifiers_and_restores_on_exit(self) -> None:
        assert get_log_context() == {}

        with bind_task_context(job_id=42, tenant_id="acme"):
            assert get_log_context() == {"job_id": 42, "tenant_id": "acme"}

        assert get_log_context() == {}

    def test_nests_cleanly(self) -> None:
        with bind_task_context(job_id=1):
            with bind_task_context(step="ingest"):
                assert get_log_context() == {"job_id": 1, "step": "ingest"}
            assert get_log_context() == {"job_id": 1}

    def test_inner_shadows_outer_then_restores(self) -> None:
        with bind_task_context(job_id=1), bind_task_context(job_id=2):
            assert get_log_context()["job_id"] == 2
        assert get_log_context() == {}

    def test_restores_even_when_block_raises(self) -> None:
        with pytest.raises(RuntimeError, match="boom"), bind_task_context(job_id=99):
            raise RuntimeError("boom")
        assert get_log_context() == {}

    def test_rejects_keys_that_collide_with_logrecord_attrs(self) -> None:
        """`record.name` is the logger name; binding `name=...` would be shadowed."""
        with pytest.raises(ValueError, match="name"), bind_task_context(name="oops"):
            pass


class TestLogContextFilter:
    def test_injects_bound_keys_onto_record(self) -> None:
        log_filter = LogContextFilter()
        record = _make_record()

        with bind_task_context(task_id="t-1", task_name="reports.ingest", job_id=99):
            log_filter.filter(record)

        assert record.task_id == "t-1"  # type: ignore[attr-defined]
        assert record.task_name == "reports.ingest"  # type: ignore[attr-defined]
        assert record.job_id == 99  # type: ignore[attr-defined]

    def test_no_op_when_unbound(self) -> None:
        log_filter = LogContextFilter()
        record = _make_record()
        log_filter.filter(record)
        assert not hasattr(record, "task_id")
        assert not hasattr(record, "job_id")

    def test_does_not_overwrite_explicit_extra(self) -> None:
        log_filter = LogContextFilter()
        record = _make_record()
        record.job_id = "from-extra"  # type: ignore[attr-defined]

        with bind_task_context(job_id="from-context"):
            log_filter.filter(record)

        assert record.job_id == "from-extra"  # type: ignore[attr-defined]


class TestInstallLogFilter:
    def test_idempotent(self) -> None:
        scratch = logging.getLogger("bg_tasks_test_install")
        scratch.filters.clear()
        try:
            first = install_log_filter(scratch)
            second = install_log_filter(scratch)
            assert first is second
            count = sum(1 for f in scratch.filters if isinstance(f, LogContextFilter))
            assert count == 1
        finally:
            scratch.filters.clear()


class TestSignalBinding:
    def test_prerun_binds_and_postrun_unbinds(self, sync_sqlite: Path) -> None:
        task_id = str(uuid.uuid4())
        task = _fake_task("demo.ingest")

        assert get_log_context() == {}

        on_task_prerun(sender=task, task_id=task_id, task=task, args=[], kwargs={})

        assert get_log_context() == {"task_id": task_id, "task_name": "demo.ingest"}

        on_task_postrun(sender=task, task_id=task_id, task=task)

        assert get_log_context() == {}
        assert _signal_tokens == {}

    def test_postrun_without_prerun_is_noop(self, sync_sqlite: Path) -> None:
        task = _fake_task("demo.detached")
        on_task_postrun(sender=task, task_id="never-bound", task=task)
        assert get_log_context() == {}

    def test_bind_task_context_layers_on_top_of_signal_binding(self, sync_sqlite: Path) -> None:
        task_id = str(uuid.uuid4())
        task = _fake_task("demo.layered")

        on_task_prerun(sender=task, task_id=task_id, task=task, args=[], kwargs={})
        try:
            with bind_task_context(job_id=7):
                assert get_log_context() == {
                    "task_id": task_id,
                    "task_name": "demo.layered",
                    "job_id": 7,
                }
            assert get_log_context() == {
                "task_id": task_id,
                "task_name": "demo.layered",
            }
        finally:
            on_task_postrun(sender=task, task_id=task_id, task=task)
