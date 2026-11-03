"""Provider entry point for the shared JWKS validator."""

import time

from auth.oidc_common.jwks import JWKSCache as SharedJWKSCache


class JWKSCache(SharedJWKSCache):
    @staticmethod
    def _now() -> float:
        return time.monotonic()
