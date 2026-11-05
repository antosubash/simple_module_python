"""Provider-scoped refresh-token encryption; preserves existing session ciphertext."""

from auth.oidc_common.tokens import provider_tokens

from oidc.core.constants import SESSION_REFRESH_TOKEN_KEY

_TOKENS = provider_tokens(info=b"oidc-refresh-token", session_key=SESSION_REFRESH_TOKEN_KEY)
seal_refresh_token = _TOKENS.seal_refresh_token
open_refresh_token = _TOKENS.open_refresh_token
store_refresh_token = _TOKENS.store_refresh_token
