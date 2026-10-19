"""The request/task correlation id, shared by every layer.

Lives in core rather than ``simple_module_hosting.logging`` (which re-exports
it) so the db layer can stamp audit records with it without importing the
hosting package (#498).
"""

from __future__ import annotations

from contextvars import ContextVar

correlation_id: ContextVar[str] = ContextVar("correlation_id", default="")
