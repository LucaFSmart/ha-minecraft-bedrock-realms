from datetime import datetime, timedelta, timezone

import aiohttp
import pytest
from aioresponses import aioresponses

from custom_components.minecraft_bedrock_realms.auth import MicrosoftAuth
from custom_components.minecraft_bedrock_realms.const import (
    MS_DEVICE_CODE_URL,
    MS_TOKEN_URL,
    XBL_USER_AUTH_URL,
    XBL_XSTS_AUTH_URL,
)
from custom_components.minecraft_bedrock_realms.exceptions import (
    DeviceCodeExpiredError,
    XboxLiveError,
)
from custom_components.minecraft_bedrock_realms.models import DeviceCodeInfo, OAuthToken, XboxToken


async def test_request_device_code_returns_parsed_info():
    with aioresponses() as mocked:
        mocked.post(
            MS_DEVICE_CODE_URL,
            payload={
                "device_code": "devcode123",
                "user_code": "ABCD1234",
                "verification_uri": "https://microsoft.com/link",
                "expires_in": 900,
                "interval": 5,
                "message": "Go to https://microsoft.com/link and enter ABCD1234",
            },
        )
        async with aiohttp.ClientSession() as session:
            auth = MicrosoftAuth(session)
            info = await auth.request_device_code()

    assert info.user_code == "ABCD1234"
    assert info.interval == 5


async def test_poll_for_token_retries_on_authorization_pending_then_succeeds():
    device_code = DeviceCodeInfo(
        device_code="devcode123",
        user_code="ABCD1234",
        verification_uri="https://microsoft.com/link",
        expires_in=900,
        interval=0,
        message="",
    )

    with aioresponses() as mocked:
        mocked.post(MS_TOKEN_URL, payload={"error": "authorization_pending"})
        mocked.post(
            MS_TOKEN_URL,
            payload={"access_token": "at", "refresh_token": "rt", "expires_in": 3600},
        )
        async with aiohttp.ClientSession() as session:
            auth = MicrosoftAuth(session)
            token = await auth.poll_for_token(device_code)

    assert token.access_token == "at"


async def test_poll_for_token_raises_on_expired_device_code():
    device_code = DeviceCodeInfo(
        device_code="devcode123",
        user_code="ABCD1234",
        verification_uri="https://microsoft.com/link",
        expires_in=0,
        interval=0,
        message="",
        requested_at=datetime.now(timezone.utc) - timedelta(seconds=10),
    )

    async with aiohttp.ClientSession() as session:
        auth = MicrosoftAuth(session)
        with pytest.raises(DeviceCodeExpiredError):
            await auth.poll_for_token(device_code)


async def test_get_xbox_user_token_parses_response():
    with aioresponses() as mocked:
        mocked.post(
            XBL_USER_AUTH_URL,
            payload={
                "Token": "usertoken",
                "NotAfter": "2026-08-24T12:00:00.0000000Z",
                "DisplayClaims": {"xui": [{"uhs": "hash", "xid": "1", "gtg": "Steve"}]},
            },
        )
        async with aiohttp.ClientSession() as session:
            auth = MicrosoftAuth(session)
            token = await auth.get_xbox_user_token(
                OAuthToken(access_token="at", refresh_token="rt", expires_in=3600)
            )

    assert token.token == "usertoken"


async def test_get_xsts_token_raises_xbox_live_error_on_401():
    fake_xbl_token = XboxToken(
        token="usertoken",
        userhash="hash",
        xuid="1",
        gamertag="Steve",
        not_after=datetime.now(timezone.utc) + timedelta(hours=1),
    )

    with aioresponses() as mocked:
        mocked.post(
            XBL_XSTS_AUTH_URL,
            status=401,
            payload={"XErr": 2148916233, "Message": "no profile"},
        )
        async with aiohttp.ClientSession() as session:
            auth = MicrosoftAuth(session)
            with pytest.raises(XboxLiveError) as exc_info:
                await auth.get_xsts_token(
                    fake_xbl_token, relying_party="https://pocket.realms.minecraft.net/"
                )

    assert exc_info.value.xerr == 2148916233
