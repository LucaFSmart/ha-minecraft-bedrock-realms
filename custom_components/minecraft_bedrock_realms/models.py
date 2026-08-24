"""Typed data models for Microsoft/Xbox auth tokens and Realms API responses."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _parse_iso(value: str) -> datetime:
    """Parse Microsoft's timestamp format, e.g. '2026-08-24T12:00:00.0000000Z'."""
    value = value.rstrip("Z")
    if "." in value:
        head, frac = value.split(".")
        value = f"{head}.{frac[:6]}"  # datetime supports up to microsecond precision
    dt = datetime.fromisoformat(value)
    return dt.replace(tzinfo=timezone.utc)


@dataclass(slots=True)
class DeviceCodeInfo:
    device_code: str
    user_code: str
    verification_uri: str
    expires_in: int
    interval: int
    message: str
    requested_at: datetime = field(default_factory=_utcnow)

    @property
    def expires_at(self) -> datetime:
        return self.requested_at + timedelta(seconds=self.expires_in)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "DeviceCodeInfo":
        verification_uri = data.get("verification_uri") or data.get("verification_url", "")
        message = data.get(
            "message",
            f"Go to {verification_uri} and enter code {data['user_code']}",
        )
        return cls(
            device_code=data["device_code"],
            user_code=data["user_code"],
            verification_uri=verification_uri,
            expires_in=int(data["expires_in"]),
            interval=int(data.get("interval", 5)),
            message=message,
        )


@dataclass(slots=True)
class OAuthToken:
    access_token: str
    refresh_token: str
    expires_in: int
    obtained_at: datetime = field(default_factory=_utcnow)

    @property
    def expires_at(self) -> datetime:
        return self.obtained_at + timedelta(seconds=self.expires_in)

    def is_valid(self, margin_seconds: int = 60) -> bool:
        return _utcnow() < (self.expires_at - timedelta(seconds=margin_seconds))

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "OAuthToken":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "expires_in": self.expires_in,
            "obtained_at": self.obtained_at.isoformat(),
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "OAuthToken":
        return cls(
            access_token=data["access_token"],
            refresh_token=data["refresh_token"],
            expires_in=int(data["expires_in"]),
            obtained_at=datetime.fromisoformat(data["obtained_at"]),
        )


@dataclass(slots=True)
class XboxToken:
    token: str
    userhash: str
    xuid: str
    gamertag: str
    not_after: datetime

    def is_valid(self, margin_seconds: int = 60) -> bool:
        return _utcnow() < (self.not_after - timedelta(seconds=margin_seconds))

    @property
    def authorization_header(self) -> str:
        return f"XBL3.0 x={self.userhash};{self.token}"

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "XboxToken":
        claims = data["DisplayClaims"]["xui"][0]
        return cls(
            token=data["Token"],
            userhash=claims["uhs"],
            xuid=claims.get("xid", ""),
            gamertag=claims.get("gtg", ""),
            not_after=_parse_iso(data["NotAfter"]),
        )


@dataclass(slots=True)
class RealmPlayer:
    xuid: str
    online: bool
    operator: bool = False
    accepted: bool = False
    permission: str = "MEMBER"


@dataclass(slots=True)
class Realm:
    id: int
    name: str
    owner: str | None
    owner_xuid: str
    state: str  # "OPEN" | "CLOSED"
    max_players: int
    active_slot: int
    member: bool
    days_left: int = 0
    expired: bool = False
    motd: str | None = None
    players: list[RealmPlayer] = field(default_factory=list)

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "Realm":
        players = [
            RealmPlayer(
                xuid=p["uuid"],
                online=bool(p.get("online", False)),
                operator=bool(p.get("operator", False)),
                accepted=bool(p.get("accepted", False)),
                permission=p.get("permission", "MEMBER"),
            )
            for p in (data.get("players") or [])
        ]
        return cls(
            id=int(data["id"]),
            name=data.get("name") or "",
            owner=data.get("owner"),
            owner_xuid=data.get("ownerUUID", ""),
            state=data.get("state", "UNKNOWN"),
            max_players=int(data.get("maxPlayers") or 0),
            active_slot=int(data.get("activeSlot") or 1),
            member=bool(data.get("member", False)),
            days_left=int(data.get("daysLeft") or 0),
            expired=bool(data.get("expired", False)),
            motd=data.get("motd"),
            players=players,
        )


@dataclass(slots=True)
class RealmActivity:
    realm_id: int
    online_xuids: list[str]

    @classmethod
    def from_api(cls, data: dict[str, Any]) -> "RealmActivity":
        online = [p["uuid"] for p in (data.get("players") or []) if p.get("online")]
        return cls(realm_id=int(data["id"]), online_xuids=online)
