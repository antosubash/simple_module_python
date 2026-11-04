"""Per-process loader counters, deliberately observable by the e2e tests."""

from collections.abc import Callable
from typing import Any

counters: dict[str, int] = {}


def count(name: str) -> int:
    counters[name] = counters.get(name, 0) + 1
    return counters[name]


def loader(name: str, value: Any = None) -> Callable[[], Any]:
    def load():
        call = count(name)
        return call if value is None else value

    return load
