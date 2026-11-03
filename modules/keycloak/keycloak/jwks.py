"""Provider entry point for the shared JWKS validator."""

from auth.oidc_common.jwks import JWKSCache

__all__ = ["JWKSCache"]
