"""DataUpdateCoordinator for Minecraft Bedrock Realms."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .auth import MicrosoftAuth
from .const import (
    CONF_OAUTH_TOKEN,
    DOMAIN,
    EVENT_PLAYER_JOINED,
    EVENT_PLAYER_LEFT,
    REALMS_XSTS_RELYING_PARTY,
    XBOX_LIVE_XSTS_RELYING_PARTY,
)
from .exceptions import RealmsAPIError, RealmsClientError
from .models import OAuthToken, RealmSnapshot, TrackedPlayerStatus
from .realms_api import RealmsAPI
from .xbox_profile import XboxProfileClient

_LOGGER = logging.getLogger(__name__)


class RealmsDataUpdateCoordinator(DataUpdateCoordinator[dict[int, RealmSnapshot]]):
    """Polls the Minecraft Bedrock Realms API for one Microsoft account."""

    def __init__(
        self,
        hass: HomeAssistant,
        config_entry: ConfigEntry,
        auth: MicrosoftAuth,
        realms_api: RealmsAPI,
        profile_client: XboxProfileClient,
        oauth_token: OAuthToken,
        realm_ids: set[int],
        tracked_gamertags: list[str],
        enable_events: bool,
        update_interval: int,
    ) -> None:
        from datetime import timedelta

        super().__init__(
            hass,
            _LOGGER,
            name=DOMAIN,
            config_entry=config_entry,
            update_interval=timedelta(seconds=update_interval),
        )
        self._auth = auth
        self._realms_api = realms_api
        self._profile_client = profile_client
        self._oauth_token = oauth_token
        self._realm_ids = realm_ids
        self._tracked_gamertags = tracked_gamertags
        self._enable_events = enable_events

        self._previous_online: dict[int, set[str]] = {}
        self._baseline_done: set[int] = set()
        self._gamertag_cache: dict[str, str] = {}
        self._tracked_xuid_cache: dict[str, str | None] = {}
        self.tracked_player_status: dict[str, TrackedPlayerStatus] = {
            gt: TrackedPlayerStatus(gamertag=gt, xuid=None, online=False) for gt in tracked_gamertags
        }

    async def _async_update_data(self) -> dict[int, RealmSnapshot]:
        await self._ensure_token_valid()

        try:
            realms = await self._realms_api.list_realms()
        except RealmsAPIError as err:
            if err.status == 401:
                raise ConfigEntryAuthFailed("Realms API rejected the stored token") from err
            raise UpdateFailed(f"Failed to list Realms: {err}") from err
        except RealmsClientError as err:
            raise UpdateFailed(f"Failed to list Realms: {err}") from err

        realms_by_id = {r.id: r for r in realms if r.id in self._realm_ids}

        activity_error: str | None = None
        try:
            activities = await self._realms_api.get_live_activities()
        except RealmsClientError as err:
            activities = []
            activity_error = "rate_limited"
            _LOGGER.warning("Failed to fetch live player activity: %s", err)

        activity_by_realm = {a.realm_id: a for a in activities}
        now = datetime.now(timezone.utc)
        result: dict[int, RealmSnapshot] = {}
        all_online_xuids: set[str] = set()

        for realm_id in self._realm_ids:
            realm = realms_by_id.get(realm_id)
            if realm is None:
                previous = self.data.get(realm_id) if self.data else None
                result[realm_id] = RealmSnapshot(
                    realm=previous.realm if previous else None,
                    available=False,
                    error_category="not_found",
                    last_update=previous.last_update if previous else None,
                )
                continue

            if activity_error is not None:
                previous = self.data.get(realm_id) if self.data else None
                result[realm_id] = RealmSnapshot(
                    realm=realm,
                    online_gamertags=previous.online_gamertags if previous else {},
                    last_update=previous.last_update if previous else None,
                    available=True,
                    error_category=activity_error,
                )
                continue

            activity = activity_by_realm.get(realm_id)
            online_xuids = set(activity.online_xuids) if activity else set()
            all_online_xuids |= online_xuids

            gamertags = await self._resolve_gamertags(online_xuids)
            self._diff_and_fire_events(realm, realm_id, online_xuids, gamertags, now)

            result[realm_id] = RealmSnapshot(
                realm=realm,
                online_gamertags=gamertags,
                last_update=now,
                available=True,
                error_category=None,
            )

        if activity_error is None:
            await self._update_tracked_players(all_online_xuids, now)
        return result

    async def _ensure_token_valid(self) -> None:
        if self._oauth_token.is_valid():
            return
        try:
            self._oauth_token = await self._auth.refresh_oauth_token(self._oauth_token)
        except RealmsClientError as err:
            raise ConfigEntryAuthFailed("Failed to refresh Microsoft token") from err

        self.hass.config_entries.async_update_entry(
            self.config_entry,
            data={**self.config_entry.data, CONF_OAUTH_TOKEN: self._oauth_token.to_dict()},
        )

        try:
            xbl_user_token = await self._auth.get_xbox_user_token(self._oauth_token)
            realms_xsts = await self._auth.get_xsts_token(xbl_user_token, REALMS_XSTS_RELYING_PARTY)
            xbox_live_xsts = await self._auth.get_xsts_token(xbl_user_token, XBOX_LIVE_XSTS_RELYING_PARTY)
        except RealmsClientError as err:
            raise ConfigEntryAuthFailed("Failed to re-derive Xbox Live tokens after refresh") from err

        self._realms_api.update_authorization(realms_xsts.authorization_header)
        self._profile_client.update_authorization(xbox_live_xsts.authorization_header)

    async def _resolve_gamertags(self, online_xuids: set[str]) -> dict[str, str]:
        gamertags: dict[str, str] = {}
        for xuid in online_xuids:
            if xuid not in self._gamertag_cache:
                try:
                    gamertag = await self._profile_client.get_gamertag(xuid)
                except RealmsClientError:
                    gamertag = None
                if gamertag:
                    self._gamertag_cache[xuid] = gamertag
            gamertags[xuid] = self._gamertag_cache.get(xuid, f"(unknown XUID {xuid})")
        return gamertags

    def _diff_and_fire_events(
        self,
        realm,
        realm_id: int,
        online_xuids: set[str],
        gamertags: dict[str, str],
        now: datetime,
    ) -> None:
        previous = self._previous_online.get(realm_id, set())

        if realm_id not in self._baseline_done:
            self._baseline_done.add(realm_id)
            self._previous_online[realm_id] = online_xuids
            return

        if self._enable_events:
            for xuid in online_xuids - previous:
                self.hass.bus.async_fire(
                    EVENT_PLAYER_JOINED,
                    {
                        "realm_id": realm_id,
                        "realm_name": realm.name,
                        "player_xuid": xuid,
                        "player_name": gamertags.get(xuid),
                        "timestamp": now.isoformat(),
                    },
                )
            for xuid in previous - online_xuids:
                self.hass.bus.async_fire(
                    EVENT_PLAYER_LEFT,
                    {
                        "realm_id": realm_id,
                        "realm_name": realm.name,
                        "player_xuid": xuid,
                        "player_name": self._gamertag_cache.get(xuid),
                        "timestamp": now.isoformat(),
                    },
                )

        self._previous_online[realm_id] = online_xuids

    async def _update_tracked_players(self, all_online_xuids: set[str], now: datetime) -> None:
        for gamertag in self._tracked_gamertags:
            if gamertag not in self._tracked_xuid_cache:
                try:
                    xuid = await self._profile_client.get_xuid(gamertag)
                except RealmsClientError:
                    xuid = None
                self._tracked_xuid_cache[gamertag] = xuid

            xuid = self._tracked_xuid_cache[gamertag]
            was_online = self.tracked_player_status.get(gamertag)
            online = xuid is not None and xuid in all_online_xuids

            joined_at = was_online.joined_at if was_online and was_online.online and online else None
            if online and joined_at is None:
                joined_at = now

            self.tracked_player_status[gamertag] = TrackedPlayerStatus(
                gamertag=gamertag,
                xuid=xuid,
                online=online,
                last_seen=now if online else (was_online.last_seen if was_online else None),
                joined_at=joined_at,
            )
