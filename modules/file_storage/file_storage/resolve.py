"""Turn the user id stored on a file row into a name a reader recognises.

``StoredFile.created_by`` holds an opaque user id. That is right for a
permanent record — display names change, ids do not — and useless in a table:
a column of uuids names nobody.

Names come from the app's user directory (``simple_module_core.user_directory``),
whichever auth provider installed it; ``file_storage`` imports no user module.
With no directory, or ids from another id space, the screen falls back to
showing what it stored rather than failing the page (GH #501).
"""

from __future__ import annotations

from simple_module_core.user_directory import resolve_user_labels as resolve_uploader_labels

from file_storage import constants


def label_for(user_id: str | None, labels: dict[str, str]) -> str:
    """Display label for one row's uploader.

    ``None`` is a different thing from "unresolved": no uploader was ever
    recorded, so there is no id to fall back to and the cell reads as unknown.
    """
    if not user_id:
        return constants.UNKNOWN_UPLOADER
    return labels.get(user_id, user_id)


__all__ = ["label_for", "resolve_uploader_labels"]
