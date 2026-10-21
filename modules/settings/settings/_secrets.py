"""Re-export of :mod:`simple_module_core.secret_fields` (moved there in #500)."""

from __future__ import annotations

from simple_module_core.secret_fields import (  # noqa: F401
    _NEVER_SECRET_TYPES,
    _SECRET_PATTERNS,
    _TYPED_SECRET_KEYS,
    SECRET_MASK,
    annotation_holds_secret,
    conceals_secret,
    embeds_credential,
    is_named_secret,
    is_secret_field,
    mask,
    register_typed_secrets,
)
