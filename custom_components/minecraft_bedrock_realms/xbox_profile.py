"""Resolve Xbox User IDs (XUIDs) to gamertags via the Xbox Live Profile API.

The Realms activities endpoint (see realms_api.get_live_activities) returns
XUIDs but never gamertags (confirmed in docs/research.md SS3), so a second,
separately rate-limited lookup is required to show a human-readable name.
"""
from __future__ import annotations

import logging

import aiohttp

from .const import REQUEST_TIMEOUT_SECONDS, XBOX_PROFILE_CONTRACT_VERSION
from .exceptions import RealmsAPIError

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
_PROFILE_SETTINGS_URL = (
    "https://profile.xboxlive.com/users/xuid({xuid})/profile/settings?settings=Gamertag"
)


class XboxProfileClient:
    """Async client for resolving a single XUID to a gamertag."""

    def __init__(self, session: aiohttp.ClientSession, authorization_header: str) -> None:
        self._session = session
        self._authorization_header = authorization_header

    def update_authorization(self, authorization_header: str) -> None:
        self._authorization_header = authorization_header

    async def get_gamertag(self, xuid: str) -> str | None:
        url = _PROFILE_SETTINGS_URL.format(xuid=xuid)
        headers = {
            "Authorization": self._authorization_header,
            "x-xbl-contract-version": XBOX_PROFILE_CONTRACT_VERSION,
            "Accept": "application/json",
        }
        async with self._session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            if resp.status == 404:
                return None
            if resp.status >= 400:
                text = await resp.text()
                raise RealmsAPIError(resp.status, text)
            data = await resp.json(content_type=None)

        try:
            settings = data["profileUsers"][0]["settings"]
            return next(s["value"] for s in settings if s["id"] == "Gamertag")
        except (KeyError, IndexError, StopIteration):
            _LOGGER.debug("Profile response for XUID %s had no Gamertag setting", xuid)
            return None
