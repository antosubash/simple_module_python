"""Identifier case-conversion helpers used by every scaffolder.

Module/host names are accepted in any case style and normalized to the
three forms the templates need: snake_case (Python package + entry-point
key), kebab-case (PyPI slug), and PascalCase (display name in Meta).
"""

from __future__ import annotations

import re

__all__ = [
    "InvalidScaffoldNameError",
    "to_kebab_case",
    "to_pascal_case",
    "to_snake_case",
    "validate_scaffold_name",
]


class InvalidScaffoldNameError(ValueError):
    """Raised when a user-supplied scaffold name can't be canonicalized.

    Names that mix case, lead with a digit, contain spaces or non
    ``[a-z0-9_-]`` characters, or mix ``_`` and ``-`` separators within
    the same identifier are ambiguous: the scaffolder would have to guess
    a canonical form, and the directory name would diverge from the
    READMEs that reference it. Reject up front instead.
    """


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


_VALID_NAME_RE = re.compile(r"^[a-z][a-z0-9]*(?:[_-][a-z0-9]+)*$")


def validate_scaffold_name(name: str) -> str:
    """Reject ambiguous host/module names; return the canonical display form.

    A valid name is lowercase alphanumerics with at most one separator
    style — either ``_`` or ``-``, not both. Examples:

    * ``simple_module_chat`` -> ``simple_module_chat``
    * ``simple-module-chat`` -> ``simple-module-chat``
    * ``MyApp`` -> rejected (mixed case is ambiguous: ``my-app`` or ``my_app``?)
    * ``1chat`` -> rejected (must start with a letter)
    * ``foo_bar-baz`` -> rejected (mixed separators leave no canonical form)
    """
    if not name or not _VALID_NAME_RE.match(name) or ("_" in name and "-" in name):
        raise InvalidScaffoldNameError(
            f"{name!r} is not a valid scaffold name. Use lowercase letters and "
            "digits with at most one separator style (all '_' or all '-'), "
            "starting with a letter. e.g. 'my_app', 'my-app', or 'myapp'."
        )
    return name
