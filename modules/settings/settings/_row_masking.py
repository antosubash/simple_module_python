"""Whether a stored row's value may be shown, and how the mask is honoured.

Split out of ``service`` so the "is this a secret, and is this write the mask
being echoed back?" question lives in one file, next to the field-level rules in
``_secrets`` that it delegates to. ``service`` imports these; nothing else
should need to, because the point of funnelling every read through ``out`` is
that there is no second way to serialize a row.
"""

from __future__ import annotations

from settings._secrets import conceals_secret
from settings.constants import SENSITIVE_KEYS, SENSITIVE_PLACEHOLDER
from settings.contracts.schemas import SettingOut
from settings.models import Setting


def is_masked(entity: Setting) -> bool:
    """Whether this row's stored value must not leave the service.

    :data:`SENSITIVE_KEYS` names the one key the hosting layer owns
    (``host.secret_key``). Everything else is judged by the same name/value
    rule the module editor uses, because the store is the *same data* seen
    through a different screen: an override named ``users.smtp_password``, or
    any override holding a ``postgresql://user:pw@host/db``, was rendered in
    clear text in the browse table and pre-filled into the edit form purely
    because the allowlist had a single entry in it.
    """
    return entity.key in SENSITIVE_KEYS or conceals_secret(
        entity.key, entity.value, entity.value_type
    )


def out(entity: Setting) -> SettingOut:
    """Serialize a row, masking values that must not leave the service.

    Every read path funnels through here so a secret cannot be read back by
    listing it, resolving it, or fetching it by id.
    """
    out = SettingOut.model_validate(entity)
    if is_masked(entity):
        return out.model_copy(update={"value": SENSITIVE_PLACEHOLDER})
    return out


def is_placeholder_write(entity: Setting, value: object) -> bool:
    """Whether this write is the mask being echoed back, not a real new value.

    The admin edit form GETs the row, pre-fills its input from the response,
    and PUTs it back. For a masked row that response carries ``"********"``, so
    an admin who opens the row and clicks Save — without touching the field —
    would otherwise overwrite a real credential with a fixed, publicly-known
    string. On ``host.secret_key`` that silently invalidates every session and
    makes every future cookie forgeable.

    Gated on the stored row rather than on the sentinel alone, so a non-secret
    row whose real value happens to be eight asterisks still saves.

    Treated as "leave it alone" rather than rejected, so the rest of the form
    still saves and an admin who genuinely types a new value can still set one.
    """
    return is_masked(entity) and value == SENSITIVE_PLACEHOLDER


def drop_placeholder_write(entity: Setting, changes: dict) -> None:
    """Strip a masked-value echo out of an update payload, in place."""
    if "value" in changes and is_placeholder_write(entity, changes["value"]):
        del changes["value"]
