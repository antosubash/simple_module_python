"""Pure metadata readers for a single pydantic settings field.

Split out of ``_module_settings`` so that file keeps one job — walking the app
for settings classes — while the fiddly "what did pydantic actually record for
this field?" questions live together and are testable without a FastAPI app.
"""

from __future__ import annotations

import re
from typing import Any

from pydantic_settings import BaseSettings

# ``^(console|smtp)$`` and nothing more adventurous: an alternation of literals
# anchored at both ends is the only pattern shape that maps cleanly onto a
# select. Anything else (character classes, quantifiers, sub-groups) stays a
# free-text input rather than becoming a list that silently omits valid values.
_ENUM_PATTERN = re.compile(r"^\^\(([^()|]+(?:\|[^()|]+)+)\)\$$")


def resolve_default(info) -> Any:
    """Return the effective default, handling ``default_factory`` fields.

    Pydantic sets ``info.default`` to ``PydanticUndefined`` when
    ``default_factory`` is used. We call the factory to get the concrete
    default so the settings UI can serialize it.
    """
    from pydantic_core import PydanticUndefined

    if info.default is not PydanticUndefined:
        return info.default
    if info.default_factory is not None:
        return info.default_factory()
    return None


def env_readable_var(settings: BaseSettings, name: str) -> str | None:
    """Env var pydantic would actually read for ``name``, or ``None``.

    ``env_var`` on the view is a *label* — the ``SM_<PACKAGE>_<FIELD>`` name the
    ``smpy settings import-from-env`` CLI looks for, kept from before settings
    moved into the DB. It is not evidence that pydantic reads it: the bundled
    module settings classes subclass ``DbBackedSettings``, which drops the env
    source entirely, so ``SM_FILE_STORAGE_BACKEND`` has no effect on
    ``FileStorageSettings()``. (Until GH #283 those classes subclassed
    ``BaseSettings`` and merely omitted ``env_prefix``, which left pydantic
    reading each field from its *bare* name instead of not at all.) Deriving
    env-readability from the class's own ``env_prefix`` keeps the "From
    environment" badge honest, and works as-is for the classes that do declare
    one — the host's ``Settings`` (``SM_``), ``BackgroundTasksSettings``
    (``SM_BG_TASKS_``), and every module built from the scaffold, whose
    template ships ``env_prefix="SM_<PACKAGE>_"``.
    """
    env_prefix = str(type(settings).model_config.get("env_prefix") or "")
    if not env_prefix:
        return None
    return f"{env_prefix}{name.upper()}"


def choices_for(info) -> list[str] | None:
    """The closed set of values this field accepts, or ``None`` if open.

    Read from an explicit ``json_schema_extra={"choices": [...]}`` first, then
    inferred from a simple alternation ``pattern``. A field constrained to
    ``console`` or ``smtp`` renders as a select; without this it is a text box
    whose only feedback on a typo is a 422 after Save.
    """
    extra = info.json_schema_extra if isinstance(info.json_schema_extra, dict) else {}
    declared = extra.get("choices")
    if isinstance(declared, (list, tuple)) and declared:
        return [str(choice) for choice in declared]

    for constraint in info.metadata:
        pattern = getattr(constraint, "pattern", None)
        if not isinstance(pattern, str):
            continue
        match = _ENUM_PATTERN.match(pattern)
        if match:
            return match.group(1).split("|")
    return None
