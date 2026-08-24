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
    general Xbox Live (used for gamertag resolution). A *set* comparison of
    the two RelyingParty values cannot tell "each request went to the
    correct relying party" apart from an accidental swap of either the
    relying-party arguments in realm_cli.py's two auth.get_xsts_token(...)
    calls, or the return-tuple order - a set equals either way. This test
    instead:

      - gives the two mocked XSTS responses distinct Token/uhs values, and
      - asserts *positionally* on the captured outgoing request bodies:
        aioresponses serves repeated registrations for the same URL in
        registration order, which matches _authenticate's actual call
        order (Realms relying party requested first, then Xbox Live), and
      - runs the full request flow (_run) and asserts the Authorization
        header actually sent to the Realms API (/worlds,
        /activities/live/players) and to the Xbox profile endpoint
        carries the token/userhash for its own relying party, not the
        other one - this end-to-end check would also catch a swap hidden
        in the return-tuple order rather than the request bodies.
    """
    monkeypatch.setattr(
        realm_cli,
        "load_token",
        lambda: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600),
    )
    monkeypatch.setattr(realm_cli, "save_token", lambda token: None)

    xbl_user_token_payload = {
        "Token": "usertoken",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "hash", "xid": "1", "gtg": "Steve"}]},
    }
    realms_xsts_payload = {
        "Token": "realms-token",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "realms-hash", "xid": "1", "gtg": "Steve"}]},
    }
    xbox_live_xsts_payload = {
        "Token": "xbox-token",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "xbox-hash", "xid": "1", "gtg": "Steve"}]},
    }

    with aioresponses() as mocked:
        mocked.post(XBL_USER_AUTH_URL, payload=xbl_user_token_payload)
        # Registration order matters: aioresponses serves repeated
        # registrations for the same URL in the order they were registered,
        # and _authenticate requests the Realms relying party first.
        mocked.post(XBL_XSTS_AUTH_URL, payload=realms_xsts_payload)  # Realms XSTS
        mocked.post(XBL_XSTS_AUTH_URL, payload=xbox_live_xsts_payload)  # Xbox Live XSTS

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

        xsts_calls = mocked.requests[("POST", URL(XBL_XSTS_AUTH_URL))]
        assert len(xsts_calls) == 2
        assert xsts_calls[0].kwargs["json"]["RelyingParty"] == REALMS_XSTS_RELYING_PARTY
        assert xsts_calls[1].kwargs["json"]["RelyingParty"] == XBOX_LIVE_XSTS_RELYING_PARTY

        realms_auth_header = "XBL3.0 x=realms-hash;realms-token"
        xbox_auth_header = "XBL3.0 x=xbox-hash;xbox-token"

        worlds_calls = mocked.requests[("GET", URL(f"{REALMS_API_BASE}/worlds"))]
        assert worlds_calls[-1].kwargs["headers"]["Authorization"] == realms_auth_header

        activities_calls = mocked.requests[
            ("GET", URL(f"{REALMS_API_BASE}/activities/live/players"))
        ]
        assert activities_calls[-1].kwargs["headers"]["Authorization"] == realms_auth_header

        profile_calls = mocked.requests[
            (
                "GET",
                URL(
                    "https://profile.xboxlive.com/users/xuid(111)/profile/settings"
                    "?settings=Gamertag"
                ),
            )
        ]
        assert profile_calls[-1].kwargs["headers"]["Authorization"] == xbox_auth_header


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
