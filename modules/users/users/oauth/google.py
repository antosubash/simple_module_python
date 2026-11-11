"""Google client that also reads the person's name (#877).

``httpx_oauth``'s ``GoogleOAuth2.get_profile`` asks the People API for
``emailAddresses`` only, so the IdP display name never arrives. The ``profile``
scope it already requests covers ``names``.
"""

from __future__ import annotations

from typing import Any, cast

from httpx_oauth.clients.google import PROFILE_ENDPOINT, GoogleOAuth2
from httpx_oauth.exceptions import GetProfileError

PERSON_FIELDS = "emailAddresses,names"


class GoogleWithNames(GoogleOAuth2):
    async def get_profile(self, token: str) -> dict[str, Any]:
        async with self.get_httpx_client() as client:
            response = await client.get(
                PROFILE_ENDPOINT,
                params={"personFields": PERSON_FIELDS},
                headers={**self.request_headers, "Authorization": f"Bearer {token}"},
            )
            if response.status_code >= 400:
                raise GetProfileError(response=response)
            return cast(dict[str, Any], response.json())
