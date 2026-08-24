import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.minecraft_bedrock_realms.const import REALMS_API_BASE
from custom_components.minecraft_bedrock_realms.exceptions import (
    RealmsAPIError,
    RealmsRateLimitedError,
)
from custom_components.minecraft_bedrock_realms.realms_api import RealmsAPI

_AUTH = "XBL3.0 x=hash;token"


async def test_list_realms_parses_servers():
    with aioresponses() as mocked:
        mocked.get(
            f"{REALMS_API_BASE}/worlds",
            payload={
                "servers": [
                    {
                        "id": 1,
                        "name": "Test Realm",
                        "state": "OPEN",
                        "maxPlayers": 10,
                        "activeSlot": 1,
                        "member": True,
                        "ownerUUID": "x",
                    }
                ]
            },
        )
        async with aiohttp.ClientSession() as session:
            api = RealmsAPI(session, _AUTH)
            realms = await api.list_realms()

    assert len(realms) == 1
    assert realms[0].name == "Test Realm"


async def test_get_live_activities_parses_servers():
    with aioresponses() as mocked:
        mocked.get(
            f"{REALMS_API_BASE}/activities/live/players",
            payload={
                "servers": [{"id": 1, "full": False, "players": [{"uuid": "111", "online": True}]}]
            },
        )
        async with aiohttp.ClientSession() as session:
            api = RealmsAPI(session, _AUTH)
            activities = await api.get_live_activities()

    assert activities[0].online_xuids == ["111"]


async def test_retries_on_503_then_succeeds():
    with aioresponses() as mocked:
        mocked.get(f"{REALMS_API_BASE}/worlds", status=503)
        mocked.get(f"{REALMS_API_BASE}/worlds", payload={"servers": []})
        async with aiohttp.ClientSession() as session:
            api = RealmsAPI(session, _AUTH, backoff_base_seconds=0.01)
            realms = await api.list_realms()

    assert realms == []


async def test_exhausts_retries_and_raises():
    with aioresponses() as mocked:
        for _ in range(4):
            mocked.get(f"{REALMS_API_BASE}/worlds", status=503)
        async with aiohttp.ClientSession() as session:
            api = RealmsAPI(session, _AUTH, backoff_base_seconds=0.01)
            with pytest.raises(RealmsAPIError):
                await api.list_realms()


async def test_429_raises_rate_limited_error_after_retries():
    with aioresponses() as mocked:
        for _ in range(4):
            mocked.get(f"{REALMS_API_BASE}/worlds", status=429, headers={"Retry-After": "0"})
        async with aiohttp.ClientSession() as session:
            api = RealmsAPI(session, _AUTH, backoff_base_seconds=0.01)
            with pytest.raises(RealmsRateLimitedError):
                await api.list_realms()
