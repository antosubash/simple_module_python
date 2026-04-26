"""Identifier case-conversion helpers used by every scaffolder.

Module/host names are accepted in any case style and normalized to the
three forms the templates need: snake_case (Python package + entry-point
key), kebab-case (PyPI slug), and PascalCase (display name in Meta).
"""

from __future__ import annotations

import re

__all__ = ["to_kebab_case", "to_pascal_case", "to_snake_case"]


def to_snake_case(name: str) -> str:
    """'MyFeature' / 'my-feature' / 'My Feature' -> 'my_feature'."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    s = re.sub(r"[\s\-]+", "_", s)
    return s.lower()


def to_kebab_case(name: str) -> str:
    """'MyFeature' / 'my_feature' -> 'my-feature' (used as the PyPI slug)."""
    return to_snake_case(name).replace("_", "-")


def to_pascal_case(name: str) -> str:
    """'my-feature' / 'my_feature' -> 'MyFeature' (the display name in Meta)."""
    snake = to_snake_case(name)
    return "".join(part.capitalize() for part in snake.split("_") if part)
