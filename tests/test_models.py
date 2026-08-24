from datetime import datetime, timedelta, timezone

from custom_components.minecraft_bedrock_realms.models import (
    OAuthToken,
    Realm,
    RealmActivity,
    XboxToken,
)


def test_oauth_token_is_valid_before_expiry():
    token = OAuthToken(access_token="a", refresh_token="r", expires_in=3600)
    assert token.is_valid() is True


def test_oauth_token_is_invalid_past_expiry():
    token = OAuthToken(
        access_token="a",
        refresh_token="r",
        expires_in=10,
        obtained_at=datetime.now(timezone.utc) - timedelta(seconds=20),
    )
    assert token.is_valid() is False


def test_oauth_token_roundtrips_through_dict():
    token = OAuthToken(access_token="a", refresh_token="r", expires_in=3600)
    restored = OAuthToken.from_dict(token.to_dict())
    assert restored.access_token == token.access_token
    assert restored.refresh_token == token.refresh_token
    assert restored.expires_in == token.expires_in


def test_xbox_token_parses_display_claims():
    data = {
        "Token": "the-token",
        "NotAfter": "2026-08-24T12:00:00.0000000Z",
        "DisplayClaims": {"xui": [{"uhs": "hash123", "xid": "123456", "gtg": "SteveGT"}]},
    }
    token = XboxToken.from_response(data)
    assert token.token == "the-token"
    assert token.userhash == "hash123"
    assert token.xuid == "123456"
    assert token.gamertag == "SteveGT"
    assert token.authorization_header == "XBL3.0 x=hash123;the-token"


def test_realm_from_api_parses_core_fields_and_players():
    data = {
        "id": 1112223,
        "name": "Ron5468's Realm",
        "owner": "Ron5468",
        "ownerUUID": "1111222233334444",
        "state": "OPEN",
        "maxPlayers": 10,
        "activeSlot": 1,
        "member": True,
        "daysLeft": 30,
        "expired": False,
        "players": [
            {
                "uuid": "111",
                "online": True,
                "operator": False,
                "accepted": True,
                "permission": "MEMBER",
            }
        ],
    }
    realm = Realm.from_api(data)
    assert realm.id == 1112223
    assert realm.name == "Ron5468's Realm"
    assert realm.state == "OPEN"
    assert realm.max_players == 10
    assert len(realm.players) == 1
    assert realm.players[0].xuid == "111"
    assert realm.players[0].online is True


def test_realm_from_api_handles_null_players():
    data = {
        "id": 1,
        "name": "Test",
        "owner": None,
        "ownerUUID": "x",
        "state": "CLOSED",
        "maxPlayers": 10,
        "activeSlot": 1,
        "member": False,
        "players": None,
    }
    realm = Realm.from_api(data)
    assert realm.players == []


def test_realm_activity_filters_to_online_players_only():
    data = {
        "id": 1112223,
        "full": False,
        "players": [
            {"uuid": "111", "online": True},
            {"uuid": "222", "online": False},
        ],
    }
    activity = RealmActivity.from_api(data)
    assert activity.realm_id == 1112223
    assert activity.online_xuids == ["111"]
