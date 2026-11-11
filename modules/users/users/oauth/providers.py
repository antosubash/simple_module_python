"""OAuth/OIDC provider client factory.

Constructs the ``httpx_oauth`` clients for every provider that has both
``client_id`` and ``client_secret`` set in :class:`UsersSettings`. A provider
with no credentials is silently skipped — that's the "feature flag" knob.

Lives in its own module so :func:`UsersModule.register_routes` can import it
without dragging the heavy ``httpx_oauth`` packages into the cold-start path
when no provider is configured.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING, Any, NamedTuple, TypedDict

from auth.oidc_common.session import pkce_challenge

from users.core.oauth_settings import is_tenant_guid

if TYPE_CHECKING:
    from httpx_oauth.oauth2 import BaseOAuth2

    from users.core.settings import UsersSettings

logger = logging.getLogger(__name__)


class LoginSecrets(TypedDict):
    """Per-login PKCE verifier and OIDC nonce, kept in the session with the state."""

    verifier: str
    nonce: str


class OAuthProvider(NamedTuple):
    """One configured provider — name is the URL segment (``/auth/<name>``)."""

    name: str
    display_name: str
    client: BaseOAuth2
    # Microsoft only: the operator trusts member UPNs of the pinned tenant (#873).
    trust_email: bool = False

    @property
    def uses_pkce(self) -> bool:
        """Whether a login carries a PKCE verifier and an OIDC nonce (#876)."""
        return getattr(self.client, "uses_pkce", False) is True

    async def authorization_url(self, callback: str, state: str, login: LoginSecrets | None) -> str:
        """The IdP URL to send the browser to, bound to this login's secrets."""
        if login is None:
            return await self.client.get_authorization_url(callback, state)
        return await self.client.get_authorization_url(
            callback,
            state,
            code_challenge=pkce_challenge(login["verifier"]),
            code_challenge_method="S256",
            extras_params={"nonce": login["nonce"]},
        )

    async def exchange_code(
        self, code: str, callback: str, login: LoginSecrets | None
    ) -> dict[str, Any]:
        """The token endpoint's response for this authorization code."""
        if login is None:
            return await self.client.get_access_token(code, callback)
        return await self.client.get_access_token(code, callback, code_verifier=login["verifier"])

    async def get_identity(
        self, token: dict[str, Any], login: LoginSecrets | None = None
    ) -> tuple[str, str | None, bool]:
        """Return subject, email, and proof that the provider verified that email.

        ``token`` is the whole token response, so an OIDC provider can read its
        ID token (#876). ``get_id_email`` drops verification metadata, so each
        provider reads it from its own profile shape. Only a positive proof
        links an existing account or marks a new one verified (#622).
        """
        if self.uses_pkce:
            nonce = login["nonce"] if login else None
            return await self.client.identity(token, nonce, trust_email=self.trust_email)
        access_token = token["access_token"]
        if self.name == "oidc":
            profile = await self.client.get_profile(access_token)
            return str(profile["sub"]), profile.get("email"), profile.get("email_verified") is True
        if self.name == "google":
            return _google_identity(await self.client.get_profile(access_token))
        account_id, email = await self.client.get_id_email(access_token)
        if email is None:
            return account_id, None, False
        if self.name == "github":
            return account_id, email, await _github_verified(self.client, access_token, email)
        return account_id, email, False


def _google_identity(profile: dict[str, Any]) -> tuple[str, str | None, bool]:
    """People API profile → (resourceName, primary email, its ``metadata.verified``)."""
    primary = next(
        (e for e in profile.get("emailAddresses", []) if e.get("metadata", {}).get("primary")),
        None,
    )
    if primary is None:
        return str(profile["resourceName"]), None, False
    verified = primary.get("metadata", {}).get("verified") is True
    return str(profile["resourceName"]), primary.get("value"), verified


async def _github_verified(client: Any, token: str, email: str) -> bool:
    try:
        emails = await client.get_emails(token)
    except Exception:
        return False
    return any(e.get("email") == email and e.get("verified") is True for e in emails)


def build_clients(settings: UsersSettings) -> list[OAuthProvider]:
    """Return one entry per provider that has both id and secret configured.

    The generic OIDC provider also requires a discovery URL. If discovery
    fetch fails at construction time, the provider is logged and skipped
    rather than raising — a misconfigured IdP must not break boot.
    """
    out: list[OAuthProvider] = []

    if settings.oauth_google_client_id and settings.oauth_google_client_secret:
        from httpx_oauth.clients.google import GoogleOAuth2

        out.append(
            OAuthProvider(
                "google",
                "Google",
                GoogleOAuth2(
                    settings.oauth_google_client_id,
                    settings.oauth_google_client_secret,
                ),
            )
        )

    if settings.oauth_github_client_id and settings.oauth_github_client_secret:
        from httpx_oauth.clients.github import GitHubOAuth2

        out.append(
            OAuthProvider(
                "github",
                "GitHub",
                GitHubOAuth2(
                    settings.oauth_github_client_id,
                    settings.oauth_github_client_secret,
                ),
            )
        )

    if settings.oauth_microsoft_client_id and settings.oauth_microsoft_client_secret:
        from users.oauth.microsoft import MicrosoftOidc

        out.append(
            OAuthProvider(
                "microsoft",
                "Microsoft",
                MicrosoftOidc(
                    settings.oauth_microsoft_client_id,
                    settings.oauth_microsoft_client_secret,
                    settings.oauth_microsoft_tenant or "common",
                ),
                trust_email=settings.oauth_microsoft_trust_tenant_upn
                and is_tenant_guid(settings.oauth_microsoft_tenant),
            )
        )

    if (
        settings.oauth_oidc_client_id
        and settings.oauth_oidc_client_secret
        and settings.oauth_oidc_discovery_url
    ):
        from httpx_oauth.clients.openid import OpenID, OpenIDConfigurationError

        try:
            client = OpenID(
                settings.oauth_oidc_client_id,
                settings.oauth_oidc_client_secret,
                settings.oauth_oidc_discovery_url,
                name="oidc",
            )
        except OpenIDConfigurationError:
            logger.exception(
                "OIDC discovery failed for %s — provider disabled",
                settings.oauth_oidc_discovery_url,
            )
        else:
            out.append(
                OAuthProvider(
                    "oidc",
                    settings.oauth_oidc_display_name or "OIDC",
                    client,
                )
            )

    return out


def build_client_map(settings: UsersSettings) -> dict[str, OAuthProvider]:
    """Configured providers keyed by name for O(1) request-time lookup."""
    return {p.name: p for p in build_clients(settings)}


def provider_buttons(clients: dict[str, OAuthProvider]) -> list[dict[str, str]]:
    """Login-button descriptors derived from a built client map."""
    return [{"name": p.name, "display_name": p.display_name} for p in clients.values()]
