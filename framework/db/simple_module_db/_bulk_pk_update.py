"""ORM bulk UPDATE by primary key: ``session.execute(update(Model), [{"id": …}, …])``.

SQLAlchemy runs that shape as an executemany keyed on the primary key and
does not apply loader criteria to it, so registered scope predicates are added
to the statement's ``WHERE`` instead: rows outside any scope stay unchanged.

SQLAlchemy refuses its own identity-map synchronization (``evaluate``) for a
bulk UPDATE with extra ``WHERE`` criteria, so it is switched off for the
statement and done here: matching objects already in the session get the new
values, as ``evaluate`` would have given them. Unevaluable predicates expire
objects instead of guessing which rows changed.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy import and_
from sqlalchemy.orm import ORMExecuteState
from sqlalchemy.orm.evaluator import UnevaluatableError, _EvaluatorCompiler

from simple_module_db.insert_guard import _param_rows

_NO_SYNC = (False, None)


def is_bulk_pk_update(execute_state: ORMExecuteState) -> bool:
    return (
        execute_state.is_update
        and getattr(execute_state.update_delete_options, "_dml_strategy", None) == "bulk"
    )


def scoped_bulk_pk_update(execute_state: ORMExecuteState, predicates: list[Any]) -> Any:
    stmt = execute_state.statement
    stmt = stmt.where(*predicates)
    execute_state.statement = stmt
    if execute_state.execution_options.get("synchronize_session", "auto") in _NO_SYNC:
        return None
    result = execute_state.invoke_statement(execution_options={"synchronize_session": False})
    _synchronize(execute_state)
    return result


def _synchronize(execute_state: ORMExecuteState) -> None:
    """``synchronize_session="evaluate"``, limited to objects matching every scope."""
    rows = _param_rows(execute_state)
    mapper = execute_state.update_delete_options._subject_mapper
    if mapper is None or not rows:
        return
    try:
        matches = _EvaluatorCompiler(mapper.class_).process(
            and_(*execute_state.statement._where_criteria)
        )
    except UnevaluatableError:
        matches = None
    pk_keys = [prop.key for prop in mapper._identity_key_props]
    identity_map = execute_state.session.identity_map
    for row in rows:
        if any(key not in row for key in pk_keys):
            continue
        state = identity_map.fast_get_state(
            mapper.identity_key_from_primary_key(tuple(row[key] for key in pk_keys))
        )
        if state is None:
            continue
        if matches is None:
            execute_state.session.expire(state.obj())
            continue
        if matches(state.obj()) is not True:
            continue
        evaluated = state.unmodified.intersection(set(row).difference(pk_keys))
        for key in evaluated:
            if key in state.dict:
                state.dict[key] = row[key]
        state.manager.dispatch.refresh(state, None, evaluated)
        state._commit(state.dict, list(evaluated))


__all__ = ["is_bulk_pk_update", "scoped_bulk_pk_update"]
