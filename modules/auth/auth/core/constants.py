"""Shared browser session keys."""

SESSION_AUTHORITY_KEY = "oidc_authority"
SESSION_ID_KEY = "oidc_session_id"
# Cooldown after a transient refresh failure or skipped coordination.
REFRESH_RETRY_AFTER_SECONDS = 30
