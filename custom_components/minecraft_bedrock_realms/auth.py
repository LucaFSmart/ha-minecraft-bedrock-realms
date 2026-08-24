"""Microsoft device-code -> Xbox Live user token -> XSTS token authentication chain."""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

import aiohttp

from .const import (
    DEFAULT_CLIENT_ID,
    MS_DEVICE_CODE_URL,
    MS_OAUTH_SCOPE,
    MS_TOKEN_URL,
    REQUEST_TIMEOUT_SECONDS,
    XBL_AUTH_RELYING_PARTY,
    XBL_USER_AUTH_URL,
    XBL_XSTS_AUTH_URL,
)
from .exceptions import AuthenticationError, DeviceCodeExpiredError, XboxLiveError
from .models import DeviceCodeInfo, OAuthToken, XboxToken

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


class MicrosoftAuth:
    """Performs and refreshes the MSA device code -> XBL -> XSTS token chain.

    Never logs or exposes token values - only presence/validity is logged.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str = DEFAULT_CLIENT_ID,
    ) -> None:
        self._session = session
        self._client_id = client_id

    async def request_device_code(self) -> DeviceCodeInfo:
        try:
            async with self._session.post(
                MS_DEVICE_CODE_URL,
                data={"client_id": self._client_id, "scope": MS_OAUTH_SCOPE},
                timeout=_TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    detail = data.get("error_description") or data.get("error") or ""
                    raise AuthenticationError(
                        f"Failed to request device code: HTTP {resp.status}"
                        + (f" — {detail}" if detail else "")
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AuthenticationError(f"Network error: {err}") from err
        _LOGGER.debug("Received device code (expires_in=%s)", data.get("expires_in"))
        return DeviceCodeInfo.from_response(data)

    async def poll_for_token(self, device_code_info: DeviceCodeInfo) -> OAuthToken:
        interval = device_code_info.interval
        while True:
            await asyncio.sleep(interval)
            if datetime.now(timezone.utc) > device_code_info.expires_at:
                raise DeviceCodeExpiredError("Device code expired before login completed")

            try:
                async with self._session.post(
                    MS_TOKEN_URL,
                    data={
                        "client_id": self._client_id,
                        "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                        "device_code": device_code_info.device_code,
                    },
                    timeout=_TIMEOUT,
                ) as resp:
                    data = await resp.json(content_type=None)
            except (aiohttp.ClientError, TimeoutError) as err:
                raise AuthenticationError(f"Network error: {err}") from err

            error = data.get("error")
            if error is None:
                _LOGGER.debug("Device code login succeeded")
                return OAuthToken.from_response(data)
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error in ("authorization_declined", "expired_token", "bad_verification_code"):
                raise AuthenticationError(f"Device code login failed: {error}")
            raise AuthenticationError(f"Unexpected device code error: {error}")

    async def refresh_oauth_token(self, token: OAuthToken) -> OAuthToken:
        try:
            async with self._session.post(
                MS_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "grant_type": "refresh_token",
                    "refresh_token": token.refresh_token,
                    "scope": MS_OAUTH_SCOPE,
                },
                timeout=_TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status != 200:
                    raise AuthenticationError(
                        f"Failed to refresh Microsoft token: HTTP {resp.status}"
                    )
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AuthenticationError(f"Network error: {err}") from err
        _LOGGER.debug("Refreshed Microsoft OAuth token")
        return OAuthToken.from_response(data)

    async def get_xbox_user_token(self, oauth_token: OAuthToken) -> XboxToken:
        return await self._xbl_authenticate(
            relying_party=XBL_AUTH_RELYING_PARTY,
            url=XBL_USER_AUTH_URL,
            properties={
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={oauth_token.access_token}",
            },
        )

    async def get_xsts_token(self, xbl_user_token: XboxToken, relying_party: str) -> XboxToken:
        return await self._xbl_authenticate(
            relying_party=relying_party,
            url=XBL_XSTS_AUTH_URL,
            properties={"UserTokens": [xbl_user_token.token], "SandboxId": "RETAIL"},
        )

    async def _xbl_authenticate(self, *, relying_party: str, url: str, properties: dict) -> XboxToken:
        try:
            async with self._session.post(
                url,
                json={
                    "RelyingParty": relying_party,
                    "TokenType": "JWT",
                    "Properties": properties,
                },
                headers={"x-xbl-contract-version": "1"},
                timeout=_TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)
                if resp.status == 401:
                    raise XboxLiveError.from_response(data)
                if resp.status not in (200, 201):
                    raise AuthenticationError(f"Xbox Live auth failed: HTTP {resp.status}")
                return XboxToken.from_response(data)
        except (aiohttp.ClientError, TimeoutError) as err:
            raise AuthenticationError(f"Network error: {err}") from err
