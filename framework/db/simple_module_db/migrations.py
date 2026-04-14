"""Helpers for Alembic integration with module-based schemas.

A host's ``migrations/env.py`` should call :func:`build_module_metadata` to
obtain the combined ``target_metadata`` for autogenerate, and
:func:`make_include_object` to obtain an ``include_object`` filter that
protects non-module tables from being touched by autogenerate.

This abstraction decouples the host from the import mechanics and is the
single place where a pip-installed module's ``<pkg>.models`` submodule gets
loaded — so every host scaffolded by ``sm create-host`` behaves identically
whether the module was installed via workspace path, PyPI wheel, or
``pip install -e``.
"""

from __future__ import annotations

import importlib
import logging
from collections.abc import Callable, Sequence
from typing import Literal

from simple_module_core import ModuleBase
from simple_module_core.discovery import discover_modules, get_module_package_name
from sqlalchemy import MetaData
from sqlalchemy.schema import SchemaItem

from simple_module_db.base import all_module_bases

logger = logging.getLogger(__name__)

# Matches alembic.context.configure's include_object signature exactly so
# type-checkers accept the returned filter without casts or ignores.
_SchemaItemType = Literal[
    "schema", "table", "column", "index", "unique_constraint", "foreign_key_constraint"
]
IncludeObjectFn = Callable[[SchemaItem, str | None, _SchemaItemType, bool, SchemaItem | None], bool]


def build_module_metadata(modules: Sequence[ModuleBase] | None = None) -> MetaData:
    """Import every installed module's ``models`` submodule and return combined MetaData.

    Returns a single :class:`MetaData` containing every ``Table`` declared by
    every installed module's SQLAlchemy models. Modules without a ``models``
    submodule are skipped without error.

    :param modules: Optional list of already-discovered modules. When ``None``,
        :func:`discover_modules` is called to find them. Callers that already
        have the list (e.g. an env.py that shares state with the app) should
        pass it in to avoid re-parsing entry_points and re-running the
        framework version check.
    """
    if modules is None:
        modules = discover_modules()
    for mod in modules:
        pkg = get_module_package_name(mod)
        try:
            importlib.import_module(f"{pkg}.models")
        except ModuleNotFoundError:
            logger.debug("No models submodule for module '%s' (pkg=%s)", mod.meta.name, pkg)

    combined = MetaData()
    for base in all_module_bases:
        for table in base.metadata.tables.values():
            table.to_metadata(combined)
    return combined


def make_include_object(metadata: MetaData) -> IncludeObjectFn:
    """Return an Alembic ``include_object`` filter scoped to the module tables.

    Call as ``context.configure(..., include_object=make_include_object(meta))``.
    The filter accepts only table names present in ``metadata``, preventing
    autogenerate from diffing — and potentially dropping — tables that exist
    in the database but aren't owned by any installed module (e.g. a user
    table added by the host developer outside the module system).
    """
    allowlist = {t.name for t in metadata.tables.values()}

    def include_object(
        object: SchemaItem,
        name: str | None,
        type_: _SchemaItemType,
        reflected: bool,
        compare_to: SchemaItem | None,
    ) -> bool:
        if type_ == "table":
            return name in allowlist
        parent_table = getattr(object, "table", None)
        if parent_table is not None:
            return parent_table.name in allowlist
        return True

    return include_object
