"""A module installed after the process started reports "restart", not a crash.

GH #915: with ``make dev`` running, ``smpy add`` installs a module as an
editable package. uvicorn's reloader keeps the ``sys.path`` it started with,
so the new entry point is listed but its package cannot be imported until a
restart. Discovery used to log ``No module named 'notes.module'`` with a
traceback, which reads as a broken module.
"""

from __future__ import annotations

import logging

import pytest
import simple_module_core.discovery as discovery_mod
from simple_module_core.discovery import InvalidModuleError, discover_modules


class _EntryPoint:
    def __init__(self, name: str, module: str, exc: Exception) -> None:
        self.name = name
        self.module = module
        self._exc = exc

    def load(self):
        raise self._exc


def _missing(name: str) -> ModuleNotFoundError:
    return ModuleNotFoundError(f"No module named {name!r}", name=name)


@pytest.mark.parametrize("missing", ["notes", "notes.module"])
def test_unimportable_own_package_says_restart(monkeypatch, caplog, missing) -> None:
    ep = _EntryPoint("notes", "notes.module", _missing(missing))
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [ep])

    with caplog.at_level(logging.ERROR, logger="simple_module_core.discovery"):
        assert discover_modules(strict=False) == []

    (record,) = [r for r in caplog.records if "notes" in r.getMessage()]
    assert "restart" in record.getMessage()
    assert record.exc_info is None  # no traceback: the module is not broken


def test_strict_mode_still_refuses(monkeypatch) -> None:
    ep = _EntryPoint("notes", "notes.module", _missing("notes.module"))
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [ep])

    with pytest.raises(InvalidModuleError, match="restart"):
        discover_modules(strict=True)


def test_a_missing_third_party_import_is_still_a_failure(monkeypatch, caplog) -> None:
    """The module's own code importing something absent is a real bug."""
    ep = _EntryPoint("notes", "notes.module", _missing("somelib"))
    monkeypatch.setattr(discovery_mod, "entry_points", lambda group: [ep])

    with caplog.at_level(logging.ERROR, logger="simple_module_core.discovery"):
        discover_modules(strict=False)

    (record,) = [r for r in caplog.records if "notes" in r.getMessage()]
    assert "restart" not in record.getMessage()
    assert record.exc_info is not None
