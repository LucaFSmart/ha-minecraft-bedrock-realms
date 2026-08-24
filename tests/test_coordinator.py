"""Tests for RealmsDataUpdateCoordinator."""
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock

import pytest
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryAuthFailed
from homeassistant.helpers.update_coordinator import UpdateFailed
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.minecraft_bedrock_realms.const import (
    DOMAIN,
    EVENT_PLAYER_JOINED,
    EVENT_PLAYER_LEFT,
)
from custom_components.minecraft_bedrock_realms.coordinator import RealmsDataUpdateCoordinator
from custom_components.minecraft_bedrock_realms.exceptions import RealmsAPIError
from custom_components.minecraft_bedrock_realms.models import (
    OAuthToken,
    Realm,
    RealmActivity,
)


def _make_realm(realm_id: int = 1) -> Realm:
    return Realm(
        id=realm_id, name="Test Realm", owner="X", owner_xuid="owner-xuid",
        state="OPEN", max_players=10, active_slot=1, member=True,
    )


def _make_coordinator(hass: HomeAssistant, *, realm_ids=None, tracked_gamertags=None, enable_events=True):
    entry = MockConfigEntry(domain=DOMAIN, data={}, options={})
    entry.add_to_hass(hass)

    auth = AsyncMock()
    realms_api = AsyncMock()
    profile_client = AsyncMock()
    token = OAuthToken(access_token="at", refresh_token="rt", expires_in=3600)

    coordinator = RealmsDataUpdateCoordinator(
        hass, entry, auth, realms_api, profile_client, token,
        realm_ids=realm_ids or {1}, tracked_gamertags=tracked_gamertags or [],
        enable_events=enable_events, update_interval=60,
    )
    return coordinator, realms_api, profile_client


async def test_first_refresh_establishes_baseline_without_events(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    profile_client.get_gamertag.return_value = "PlayerOne"

    events = []
    hass.bus.async_listen(EVENT_PLAYER_JOINED, lambda e: events.append(e))
    hass.bus.async_listen(EVENT_PLAYER_LEFT, lambda e: events.append(e))

    data = await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert data[1].online_gamertags == {"p1": "PlayerOne"}
    assert events == []  # no join/leave events on the first-ever poll


async def test_second_refresh_fires_join_event_for_new_player(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    profile_client.get_gamertag.return_value = "PlayerOne"

    realms_api.get_live_activities.return_value = []
    await coordinator._async_update_data()  # baseline: nobody online

    joined_events = []
    hass.bus.async_listen(EVENT_PLAYER_JOINED, lambda e: joined_events.append(e.data))

    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(joined_events) == 1
    assert joined_events[0]["player_xuid"] == "p1"
    assert joined_events[0]["player_name"] == "PlayerOne"
    assert joined_events[0]["realm_id"] == 1
    assert joined_events[0]["realm_name"] == "Test Realm"


async def test_leave_event_fires_when_player_drops_off(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    profile_client.get_gamertag.return_value = "PlayerOne"

    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    await coordinator._async_update_data()  # baseline: p1 online

    left_events = []
    hass.bus.async_listen(EVENT_PLAYER_LEFT, lambda e: left_events.append(e.data))

    realms_api.get_live_activities.return_value = []
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert len(left_events) == 1
    assert left_events[0]["player_xuid"] == "p1"


async def test_events_suppressed_when_enable_events_false(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass, enable_events=False)
    realms_api.list_realms.return_value = [_make_realm()]
    profile_client.get_gamertag.return_value = "PlayerOne"

    realms_api.get_live_activities.return_value = []
    await coordinator._async_update_data()

    events = []
    hass.bus.async_listen(EVENT_PLAYER_JOINED, lambda e: events.append(e))

    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    await coordinator._async_update_data()
    await hass.async_block_till_done()

    assert events == []


async def test_failed_realm_list_raises_update_failed_and_keeps_previous_state(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    profile_client.get_gamertag.return_value = "PlayerOne"

    first = await coordinator._async_update_data()
    assert first[1].online_gamertags == {"p1": "PlayerOne"}

    realms_api.list_realms.side_effect = RealmsAPIError(503, "temporarily unavailable")
    with pytest.raises(UpdateFailed):
        await coordinator._async_update_data()

    # coordinator's own online-player bookkeeping must not have been reset by the failure
    assert coordinator._previous_online[1] == {"p1"}


async def test_401_raises_config_entry_auth_failed(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.side_effect = RealmsAPIError(401, "Unauthorized")

    with pytest.raises(ConfigEntryAuthFailed):
        await coordinator._async_update_data()


async def test_live_activities_failure_degrades_gracefully(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    realms_api.get_live_activities.side_effect = RealmsAPIError(503, "unavailable")

    data = await coordinator._async_update_data()

    assert data[1].online_gamertags == {}
    assert data[1].error_category == "rate_limited"


async def test_tracked_gamertag_status_reflects_online_state(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass, tracked_gamertags=["PlayerOne"])
    realms_api.list_realms.return_value = [_make_realm()]
    realms_api.get_live_activities.return_value = [RealmActivity(realm_id=1, online_xuids=["p1"])]
    profile_client.get_gamertag.return_value = "PlayerOne"
    profile_client.get_xuid.return_value = "p1"

    await coordinator._async_update_data()

    status = coordinator.tracked_player_status["PlayerOne"]
    assert status.online is True
    assert status.xuid == "p1"
    assert status.last_seen is not None


async def test_expired_token_is_refreshed_and_persisted(hass: HomeAssistant):
    coordinator, realms_api, profile_client = _make_coordinator(hass)
    realms_api.list_realms.return_value = [_make_realm()]
    realms_api.get_live_activities.return_value = []

    coordinator._oauth_token = OAuthToken(
        access_token="expired", refresh_token="rt", expires_in=10,
        obtained_at=datetime.now(timezone.utc) - timedelta(seconds=20),
    )
    new_token = OAuthToken(access_token="fresh", refresh_token="rt2", expires_in=3600)
    coordinator._auth.refresh_oauth_token = AsyncMock(return_value=new_token)

    await coordinator._async_update_data()

    coordinator._auth.refresh_oauth_token.assert_awaited_once()
    assert coordinator.config_entry.data.get("oauth_token", {}).get("access_token") == "fresh"
