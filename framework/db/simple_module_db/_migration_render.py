"""Alembic ``render_item`` callback for SQLModel + extension types."""

from __future__ import annotations

from enum import StrEnum

import sqlalchemy as sa
from sqlmodel.sql.sqltypes import UTCDateTime

from simple_module_db.extensions import render_extension_type
from simple_module_db.migration_portability import render_boolean_default


def render_item(type_, obj, autogen_context):
    """Alembic ``render_item`` callback for SQLModel + extension types.

    * Collapses SQLModel's ``AutoString`` to ``sa.String`` and ``UTCDateTime``
      to ``sa.DateTime(timezone=True)`` so migrations don't need to
      ``import sqlmodel`` (GH #440). Any other ``sqlmodel`` type still gets
      the import added, so the migration stays importable.
    * Renders Python ``StrEnum`` columns with ``values_callable`` so the
      Postgres enum labels match the lowercase ``StrEnum`` values rather than
      SQLAlchemy's default of using uppercase attribute names. This means raw
      SQL like ``WHERE status = 'ready'`` actually works against the live DB.
    * Renders ``true()``/``false()`` server defaults as ``sa.true()``/``sa.false()``
      instead of the dialect-specific ``sa.text('1')``/``sa.text('0')`` (GH #342).
    * Renders ``LTree``/``TSVector`` through ``simple_module_db.types`` (with
      the import) so one revision upgrades on Postgres and SQLite alike.
    * Adds the necessary imports for ``fastapi_users_db_sqlalchemy.generics``
      and ``geoalchemy2`` types (rendered by their own classes elsewhere) so
      the generated migration is importable.

    Pass to :func:`alembic.context.configure` as ``render_item=render_item``.
    """
    if type_ == "server_default":
        return render_boolean_default(obj, autogen_context)
    if type_ != "type":
        return False
    cls_name = type(obj).__name__
    cls_module = type(obj).__module__ or ""
    imports = autogen_context.imports if autogen_context is not None else None

    if cls_name == "AutoString":
        length = getattr(obj, "length", None)
        return f"sa.String(length={length})" if length is not None else "sa.String()"
    if isinstance(obj, UTCDateTime):  # includes our ``AwareDateTime`` subclass
        return "sa.DateTime(timezone=True)"

    if (rendered := render_extension_type(obj, imports)) is not None:
        return rendered

    if imports is not None and cls_module.startswith("sqlmodel"):
        imports.add("import sqlmodel")

    if imports is not None and cls_module.startswith("fastapi_users_db_sqlalchemy"):
        imports.add("import fastapi_users_db_sqlalchemy.generics")
    if imports is not None and cls_module.startswith("geoalchemy2"):
        imports.add("import geoalchemy2")

    # Match by isinstance, not class-name string — a user-defined ``Enum``
    # class elsewhere in the project would otherwise be matched here and
    # render with ``values_callable`` against an unrelated ``enum_class``.
    if isinstance(obj, sa.Enum):
        python_type = getattr(obj, "enum_class", None)
        if isinstance(python_type, type) and issubclass(python_type, StrEnum):
            name = getattr(obj, "name", None) or python_type.__name__.lower()
            members = ", ".join(repr(m.value) for m in python_type)
            return (
                f"sa.Enum({members}, name={name!r}, values_callable=lambda e: [m.value for m in e])"
            )

    return False  # let alembic use its default rendering
