"""NUL characters are stripped from retained logs (Postgres text/JSON rejects them)."""

from __future__ import annotations

import logging

from background_tasks import log_sink


def test_to_row_strips_nul_from_message_ids_and_extra():
    record = logging.LogRecord("app\x00x", logging.INFO, __file__, 1, "bad\x00msg", None, None)
    record.task_id = "t\x00id"
    record.job_id = "j\x00id"
    record.tenant_id = "ten\x00ant"
    record.correlation_id = "c\x00id"
    record.custom = "va\x00lue"

    row = log_sink.to_row(record)

    assert row.message == "badmsg"
    assert row.task_id == "tid"
    assert row.job_id == "jid"
    assert row.tenant_id == "tenant"
    assert row.correlation_id == "cid"
    assert "\x00" not in str(row.extra)
    assert "\x00" not in row.logger
