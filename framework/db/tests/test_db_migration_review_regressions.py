"""Autogenerate must preserve model constraints and fail on broken imports."""

import sys
from enum import StrEnum
from types import SimpleNamespace

import pytest
import sqlalchemy as sa
from alembic.autogenerate import produce_migrations
from alembic.operations.ops import CreateForeignKeyOp
from alembic.runtime.migration import MigrationContext
from simple_module_db import migrations
from simple_module_db.migration_portability import iter_ops_recursive
from simple_module_db.migrations import make_include_object, render_item
from sqlalchemy.exc import IntegrityError


class Status(StrEnum):
    READY = "ready"
    DONE = "done"


def test_db_autogenerate_adds_fk_to_existing_column():
    old = sa.MetaData()
    sa.Table("parent", old, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "child",
        old,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer),
    )
    target = sa.MetaData()
    sa.Table("parent", target, sa.Column("id", sa.Integer, primary_key=True))
    sa.Table(
        "child",
        target,
        sa.Column("id", sa.Integer, primary_key=True),
        sa.Column("parent_id", sa.Integer, sa.ForeignKey("parent.id")),
    )
    engine = sa.create_engine("sqlite://")
    try:
        old.create_all(engine)
        with engine.connect() as conn:
            ctx = MigrationContext.configure(
                conn, opts={"include_object": make_include_object(target)}
            )
            script = produce_migrations(ctx, target)
        assert any(
            isinstance(op, CreateForeignKeyOp) for op in iter_ops_recursive(script.upgrade_ops)
        )
    finally:
        engine.dispose()


@pytest.mark.parametrize("labels", ["names", "values", "custom"])
@pytest.mark.parametrize(
    "native,constraint,length", [(True, False, "default"), (False, True, 20), (False, True, None)]
)
@pytest.mark.parametrize("name", ["status", None])
def test_db_enum_rendering_preserves_storage_and_constraints(
    labels, native, constraint, length, name
):
    options = {"name": name, "native_enum": native, "create_constraint": constraint}
    if length != "default":
        options["length"] = length
    if labels == "values":
        options["values_callable"] = lambda e: [m.value for m in e]
    elif labels == "custom":
        options["values_callable"] = lambda e: [m.value.upper() + "_label" for m in e]
    runtime = sa.Enum(Status, **options)
    rendered = eval(render_item("type", runtime, None), {"sa": sa})
    expected = {
        "names": ["READY", "DONE"],
        "values": ["ready", "done"],
        "custom": ["READY_label", "DONE_label"],
    }[labels]
    assert rendered.enums == expected
    assert rendered.name == name
    assert rendered.native_enum is native
    assert rendered.create_constraint is constraint
    assert rendered.length == (max(map(len, expected)) if length == "default" else length)
    assert (rendered.values_callable is not None) == (runtime.values_callable is not None)
    if runtime.values_callable:
        assert rendered.values_callable(Status) == expected
    engine = sa.create_engine("sqlite://")
    try:
        metadata = sa.MetaData()
        table = sa.Table("row", metadata, sa.Column("status", rendered))
        metadata.create_all(engine)
        with engine.begin() as conn:
            conn.execute(table.insert().values(status=expected[0]))
            assert (
                conn.execute(sa.select(sa.type_coerce(table.c.status, runtime))).scalar_one()
                == Status.READY
            )
            if constraint:
                with pytest.raises(IntegrityError):
                    conn.execute(sa.text("INSERT INTO row (status) VALUES ('INVALID')"))
    finally:
        engine.dispose()


def test_db_value_enum_rendering_keeps_existing_output():
    declared = sa.Enum(Status, values_callable=lambda e: [m.value for m in e])
    assert render_item("type", declared, None) == (
        "sa.Enum('ready', 'done', name='status', values_callable=lambda e: [m.value for m in e])"
    )


@pytest.mark.parametrize(
    "missing",
    [
        "db_review_models.models",
        "db_review_models",
        "uninstalled_dep",
        "db_review_models.helper",
        None,
    ],
)
def test_db_metadata_only_ignores_missing_models_module(tmp_path, monkeypatch, missing):
    package = tmp_path / "db_review_models"
    package.mkdir()
    (package / "__init__.py").write_text("")
    (package / "models.py").write_text(f'raise ModuleNotFoundError("missing", name={missing!r})')
    monkeypatch.delitem(sys.modules, "db_review_models", raising=False)
    monkeypatch.delitem(sys.modules, "db_review_models.models", raising=False)
    monkeypatch.syspath_prepend(str(tmp_path))
    monkeypatch.setattr(migrations, "get_module_package_name", lambda m: "db_review_models")
    module = SimpleNamespace(meta=SimpleNamespace(name="ReviewModels"))
    if missing in ("db_review_models", "db_review_models.models"):
        migrations.build_module_metadata([module])
    else:
        with pytest.raises(ModuleNotFoundError) as exc:
            migrations.build_module_metadata([module])
        assert exc.value.name == missing
