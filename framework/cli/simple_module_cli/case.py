"""Identifier case-conversion helpers used by every scaffolder.

Module/host names are accepted in any case style and normalized to the
three forms the templates need: snake_case (Python package + entry-point
key), kebab-case (PyPI slug), and PascalCase (display name in Meta).
"""

from __future__ import annotations

import re

__all__ = ["to_kebab_case", "to_pascal_case", "to_snake_case"]


def to_snake_case(name: str) -> str:
    """'MyFeature' / 'my-feature' / 'My Feature' / 'URLPath' -> 'my_feature' / 'url_path'.

    Handles acronyms by treating ``Acronym|Word`` and ``word|Capital`` as
    boundaries: ``URLPath`` -> ``url_path``, ``APIClient`` -> ``api_client``,
    ``HTTPServer2`` -> ``http_server2``. The single-pass ``(?=[A-Z])`` form
    that preceded this would emit ``u_r_l_path`` and propagate the typo
    into the PyPI slug + display name.
    """
    s = re.sub(r"[\s\-]+", "_", name)
    s = re.sub(r"(.)([A-Z][a-z]+)", r"\1_\2", s)
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", s)
    # Collapse runs of underscores that the boundary regexes can introduce
    # when the input already contained a separator (e.g. ``My Feature`` →
    # ``My_Feature`` → ``My__Feature``). Without this the PyPI slug emits a
    # double hyphen.
    s = re.sub(r"_+", "_", s)
    return s.lower()


def to_kebab_case(name: str) -> str:
    """'MyFeature' / 'my_feature' -> 'my-feature' (used as the PyPI slug)."""
    return to_snake_case(name).replace("_", "-")


def to_pascal_case(name: str) -> str:
    """'my-feature' / 'my_feature' -> 'MyFeature' (the display name in Meta)."""
    snake = to_snake_case(name)
    return "".join(part.capitalize() for part in snake.split("_") if part)
