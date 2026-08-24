import aiohttp
from aioresponses import aioresponses

from custom_components.minecraft_bedrock_realms.xbox_profile import XboxProfileClient

_AUTH = "XBL3.0 x=hash;token"


async def test_get_gamertag_parses_profile_settings():
    with aioresponses() as mocked:
        mocked.get(
            "https://profile.xboxlive.com/users/xuid(123)/profile/settings?settings=Gamertag",
            payload={
                "profileUsers": [
                    {"id": "123", "settings": [{"id": "Gamertag", "value": "SteveGT"}]}
                ]
            },
        )
        async with aiohttp.ClientSession() as session:
            client = XboxProfileClient(session, _AUTH)
            gamertag = await client.get_gamertag("123")

    assert gamertag == "SteveGT"


async def test_get_gamertag_returns_none_on_404():
    with aioresponses() as mocked:
        mocked.get(
            "https://profile.xboxlive.com/users/xuid(999)/profile/settings?settings=Gamertag",
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            client = XboxProfileClient(session, _AUTH)
            gamertag = await client.get_gamertag("999")

    assert gamertag is None


async def test_get_xuid_parses_profile_users_id():
    with aioresponses() as mocked:
        mocked.get(
            "https://profile.xboxlive.com/users/gt(SteveGT)/profile/settings?settings=Gamertag",
            payload={"profileUsers": [{"id": "123456", "settings": []}]},
        )
        async with aiohttp.ClientSession() as session:
            client = XboxProfileClient(session, _AUTH)
            xuid = await client.get_xuid("SteveGT")

    assert xuid == "123456"


async def test_get_xuid_returns_none_on_404():
    with aioresponses() as mocked:
        mocked.get(
            "https://profile.xboxlive.com/users/gt(NoSuchGamertag)/profile/settings?settings=Gamertag",
            status=404,
        )
        async with aiohttp.ClientSession() as session:
            client = XboxProfileClient(session, _AUTH)
            xuid = await client.get_xuid("NoSuchGamertag")

    assert xuid is None
