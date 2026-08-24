"""Async client for the Minecraft Bedrock Realms REST API."""
from __future__ import annotations

import asyncio
import logging
import random

import aiohttp

from .const import (
    REALMS_API_BASE,
    REALMS_CLIENT_VERSION,
    REALMS_USER_AGENT,
    REQUEST_TIMEOUT_SECONDS,
)
from .exceptions import RealmsAPIError, RealmsRateLimitedError
from .models import Realm, RealmActivity

_LOGGER = logging.getLogger(__name__)

_RETRYABLE_STATUS = {502, 503, 504}
_MAX_BACKOFF_SECONDS = 30.0
_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


class RealmsAPI:
    """Async client for https://pocket.realms.minecraft.net.

    Retries 5xx and 429 responses with exponential backoff (honoring
    Retry-After when present), matching the behavior confirmed in
    docs/research.md SS4 for both reference implementations.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        authorization_header: str,
        *,
        backoff_base_seconds: float = 1.0,
        max_attempts: int = 4,
    ) -> None:
        self._session = session
        self._authorization_header = authorization_header
        self._backoff_base_seconds = backoff_base_seconds
        self._max_attempts = max_attempts

    def update_authorization(self, authorization_header: str) -> None:
        self._authorization_header = authorization_header

    async def list_realms(self) -> list[Realm]:
        data = await self._request("GET", "/worlds")
        return [Realm.from_api(entry) for entry in data.get("servers", [])]

    async def get_realm(self, realm_id: int) -> Realm:
        data = await self._request("GET", f"/worlds/{realm_id}")
        return Realm.from_api(data)

    async def get_live_activities(self) -> list[RealmActivity]:
        data = await self._request("GET", "/activities/live/players")
        return [RealmActivity.from_api(entry) for entry in data.get("servers", [])]

    async def _request(self, method: str, path: str) -> dict:
        url = f"{REALMS_API_BASE}{path}"
        headers = {
            "Authorization": self._authorization_header,
            "Client-Version": REALMS_CLIENT_VERSION,
            "User-Agent": REALMS_USER_AGENT,
            "Accept": "application/json",
        }

        last_error: Exception | None = None
        for attempt in range(1, self._max_attempts + 1):
            try:
                async with self._session.request(
                    method, url, headers=headers, timeout=_TIMEOUT
                ) as resp:
                    if resp.status == 429:
                        retry_after = _parse_retry_after(resp.headers.get("Retry-After"))
                        if attempt == self._max_attempts:
                            raise RealmsRateLimitedError(retry_after)
                        delay = retry_after if retry_after is not None else self._backoff_delay(attempt)
                        _LOGGER.debug("Realms API rate limited, retrying in %.2fs", delay)
                        await asyncio.sleep(delay)
                        continue
                    if resp.status in _RETRYABLE_STATUS:
                        if attempt == self._max_attempts:
                            text = await resp.text()
                            raise RealmsAPIError(resp.status, text)
                        delay = self._backoff_delay(attempt)
                        _LOGGER.debug(
                            "Realms API returned %s, retrying in %.2fs", resp.status, delay
                        )
                        await asyncio.sleep(delay)
                        continue
                    if resp.status == 401:
                        raise RealmsAPIError(401, "Unauthorized (token expired or invalid)")
                    if resp.status >= 400:
                        text = await resp.text()
                        raise RealmsAPIError(resp.status, text)
                    if resp.content_length == 0:
                        return {}
                    return await resp.json(content_type=None)
            except aiohttp.ClientError as err:
                last_error = err
                if attempt == self._max_attempts:
                    raise RealmsAPIError(0, f"Network error: {err}") from err
                await asyncio.sleep(self._backoff_delay(attempt))

        if last_error:
            raise RealmsAPIError(0, f"Network error: {last_error}") from last_error
        raise RealmsAPIError(0, "Exhausted retries with no response")

    def _backoff_delay(self, attempt: int) -> float:
        delay = min(self._backoff_base_seconds * (2 ** (attempt - 1)), _MAX_BACKOFF_SECONDS)
        jitter = delay * 0.1 * random.choice((-1, 1))
        return max(0.01, delay + jitter)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return float(value)
    except ValueError:
        return None
