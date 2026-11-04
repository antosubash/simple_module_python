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
    * Renders Python ``StrEnum`` columns using their configured labels and
      storage options, without importing application enums into revisions.
      Value-based labels require ``values_callable`` on the runtime type too;
      plain enum columns keep SQLAlchemy's member-name labels.
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
            members = ", ".join(repr(label) for label in obj.enums)
            options = [f"name={obj.name!r}"]
            if not obj.native_enum:
                options.append("native_enum=False")
            if obj.create_constraint:
                options.append("create_constraint=True")
            if obj.length != max((len(label) for label in obj.enums), default=0):
                options.append(f"length={obj.length!r}")
            if obj.values_callable is not None:
                # Freeze custom labels; revisions must not import application callables.
                values = [member.value for member in python_type]
                callable_body = "[m.value for m in e]" if obj.enums == values else repr(obj.enums)
                options.append(f"values_callable=lambda e: {callable_body}")
            return f"sa.Enum({members}, {', '.join(options)})"

    return False  # let alembic use its default rendering
