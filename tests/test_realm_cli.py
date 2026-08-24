import aiohttp
from aioresponses import aioresponses
from yarl import URL

from custom_components.minecraft_bedrock_realms.const import (
    REALMS_API_BASE,
    REALMS_XSTS_RELYING_PARTY,
    XBL_USER_AUTH_URL,
    XBL_XSTS_AUTH_URL,
    XBOX_LIVE_XSTS_RELYING_PARTY,
)
from custom_components.minecraft_bedrock_realms.models import OAuthToken
from poc import realm_cli


async def test_run_prints_realm_status_and_online_players(monkeypatch, capsys):
    monkeypatch.setattr(
        realm_cli,
        "load_token",
        lambda: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600),
    )
    monkeypatch.setattr(realm_cli, "save_token", lambda token: None)

    xbox_token_payload = {
        "Token": "usertoken",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "hash", "xid": "1", "gtg": "Steve"}]},
    }

    with aioresponses() as mocked:
        mocked.post(XBL_USER_AUTH_URL, payload=xbox_token_payload)
        mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Realms XSTS
        mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Xbox Live XSTS

        mocked.get(
            f"{REALMS_API_BASE}/worlds",
            payload={
                "servers": [
                    {
                        "id": 1112223,
                        "name": "Ron5468's Realm",
                        "state": "OPEN",
                        "maxPlayers": 10,
                        "activeSlot": 1,
                        "member": True,
                        "ownerUUID": "x",
                    }
                ]
            },
        )
        mocked.get(
            f"{REALMS_API_BASE}/activities/live/players",
            payload={
                "servers": [
                    {"id": 1112223, "full": False, "players": [{"uuid": "111", "online": True}]}
                ]
            },
        )
        mocked.get(
            "https://profile.xboxlive.com/users/xuid(111)/profile/settings?settings=Gamertag",
            payload={
                "profileUsers": [{"id": "111", "settings": [{"id": "Gamertag", "value": "BigW"}]}]
            },
        )

        exit_code = await realm_cli._run(None)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "Ron5468's Realm" in out
    assert "OPEN" in out
    assert "BigW" in out


async def test_run_continues_when_gamertag_lookup_fails(monkeypatch, capsys):
    monkeypatch.setattr(
        realm_cli,
        "load_token",
        lambda: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600),
    )
    monkeypatch.setattr(realm_cli, "save_token", lambda token: None)

    xbox_token_payload = {
        "Token": "usertoken",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "hash", "xid": "1", "gtg": "Steve"}]},
    }

    with aioresponses() as mocked:
        mocked.post(XBL_USER_AUTH_URL, payload=xbox_token_payload)
        mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Realms XSTS
        mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Xbox Live XSTS

        mocked.get(
            f"{REALMS_API_BASE}/worlds",
            payload={
                "servers": [
                    {
                        "id": 1112223,
                        "name": "Ron5468's Realm",
                        "state": "OPEN",
                        "maxPlayers": 10,
                        "activeSlot": 1,
                        "member": True,
                        "ownerUUID": "x",
                    }
                ]
            },
        )
        mocked.get(
            f"{REALMS_API_BASE}/activities/live/players",
            payload={
                "servers": [
                    {"id": 1112223, "full": False, "players": [{"uuid": "111", "online": True}]}
                ]
            },
        )
        mocked.get(
            "https://profile.xboxlive.com/users/xuid(111)/profile/settings?settings=Gamertag",
            status=429,
            payload={},
        )

        exit_code = await realm_cli._run(None)

    assert exit_code == 0
    out = capsys.readouterr().out
    assert "(unknown XUID 111)" in out


async def test_authenticate_sends_realms_and_xbox_live_xsts_to_the_right_relying_parties(
    monkeypatch,
):
    """Regression test for the auth-chain relying-party split.

    _authenticate() makes two XSTS requests against the same URL
    (XBL_XSTS_AUTH_URL) - one scoped to the Realms API, one scoped to
    general Xbox Live (used for gamertag resolution). Nothing previously
    distinguished "each request went to the correct relying party" from an
    accidental swap of either the relying-party arguments in realm_cli.py's
    two auth.get_xsts_token(...) calls, or the return-tuple order. Capture
    the actual outgoing request bodies via aioresponses and assert on the
    RelyingParty each one carried.
    """
    monkeypatch.setattr(
        realm_cli,
        "load_token",
        lambda: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600),
    )
    monkeypatch.setattr(realm_cli, "save_token", lambda token: None)

    xbox_token_payload = {
        "Token": "usertoken",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "hash", "xid": "1", "gtg": "Steve"}]},
    }

    async with aiohttp.ClientSession() as session:
        with aioresponses() as mocked:
            mocked.post(XBL_USER_AUTH_URL, payload=xbox_token_payload)
            mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Realms XSTS
            mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_token_payload)  # Xbox Live XSTS

            await realm_cli._authenticate(session, None)

            xsts_calls = mocked.requests[("POST", URL(XBL_XSTS_AUTH_URL))]
            assert len(xsts_calls) == 2

            relying_parties = {call.kwargs["json"]["RelyingParty"] for call in xsts_calls}
            assert relying_parties == {REALMS_XSTS_RELYING_PARTY, XBOX_LIVE_XSTS_RELYING_PARTY}


async def test_run_reports_when_account_has_no_realms(monkeypatch):
    async def fake_authenticate(
        session: aiohttp.ClientSession, client_id: str | None
    ) -> tuple[str, str]:
        return "realms-auth", "xbox-auth"

    monkeypatch.setattr(realm_cli, "_authenticate", fake_authenticate)

    with aioresponses() as mocked:
        mocked.get(f"{REALMS_API_BASE}/worlds", payload={"servers": []})
        exit_code = await realm_cli._run(None)

    assert exit_code == 0
