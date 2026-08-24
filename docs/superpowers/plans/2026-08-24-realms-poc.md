# Phase 3 Proof-of-Concept Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and prove out the Microsoft/Xbox/Realms authentication + API client as reusable
Python modules under `custom_components/minecraft_bedrock_realms/`, wired together by a standalone
CLI (`poc/realm_cli.py`) that authenticates against a real account and prints Realm status +
live online players — validating the mechanism confirmed in `docs/research.md` before any
Home Assistant integration code is written.

**Architecture:** Pure async Python (`aiohttp`), no Home Assistant imports anywhere in this phase
(these modules must be importable and testable standalone). Every external HTTP call is mocked in
automated tests (`aioresponses`); the one thing that cannot be automated is the final live run
against the developer's real Microsoft account, which is a manual verification step at the end of
this plan, per the project rule "do not continue to the full HA integration until the PoC
successfully retrieves real Realm data."

**Tech Stack:** Python 3.13+ (target runtime for the eventual HA integration is 3.14, matching
Home Assistant 2026.x), `aiohttp`, `pytest` + `pytest-asyncio` + `aioresponses` for tests, `ruff`
for lint/format, `mypy` for type checking.

## Global Constraints

- Never store or request a Microsoft password. Device-code flow only.
- Tokens are never logged, never printed except the one-time `access_token`/`refresh_token` pair
  written to the local PoC-only cache file (which is `.gitignore`d and never committed).
- All I/O is async (`aiohttp`); no blocking calls.
- No destructive Realm actions (open/close/reset/delete/ban/op) are implemented anywhere in this
  plan — this PoC is read-only monitoring, matching the project's monitoring-first scope.
- Every automated test mocks external HTTP; no test requires real Microsoft credentials or
  network access.
- MIT license for this repository.
- Git commits in this repo use author `LucaFSmart <197988000+LucaFSmart@users.noreply.github.com>`
  — never the developer's real name. Pass this per-command via `git -c user.name=... -c
  user.email=... commit ...`; never edit git config directly.
- Realms API base URL: `https://pocket.realms.minecraft.net`. Realms XSTS relying party:
  `https://pocket.realms.minecraft.net/`. General Xbox Live XSTS relying party:
  `http://xboxlive.com`. XBL user-token relying party: `http://auth.xboxlive.com`. (All confirmed
  in `docs/research.md` §1.)

---

## Task 1: Project scaffolding & dev tooling

**Files:**
- Create: `.gitignore`
- Create: `pyproject.toml`
- Create: `requirements-dev.txt`
- Create: `custom_components/__init__.py`
- Create: `custom_components/minecraft_bedrock_realms/__init__.py`
- Create: `poc/__init__.py`
- Create: `LICENSE`
- Create: `README.md`

**Interfaces:**
- Produces: an importable `custom_components.minecraft_bedrock_realms` package and an importable
  `poc` package, a working `pytest` command, `ruff` and `mypy` configured.

- [ ] **Step 1: Create `.gitignore`**

```gitignore
# Python
__pycache__/
*.py[cod]
*.egg-info/
.eggs/
.venv/
venv/
.mypy_cache/
.ruff_cache/
.pytest_cache/
.coverage
htmlcov/

# Editors / OS
.vscode/
.idea/
.DS_Store
Thumbs.db

# Secrets / local state - never commit tokens
token.json
*.token.json
.env
```

- [ ] **Step 2: Create `pyproject.toml`**

```toml
[tool.pytest.ini_options]
asyncio_mode = "auto"
pythonpath = ["."]
testpaths = ["tests"]

[tool.ruff]
line-length = 100

[tool.ruff.lint]
select = ["E", "F", "I", "UP", "B", "ASYNC"]
ignore = ["E501"]

[tool.mypy]
python_version = "3.13"
ignore_missing_imports = true
warn_unused_ignores = true
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```text
aiohttp>=3.10
pytest>=8.3
pytest-asyncio>=0.24
aioresponses>=0.7.6
ruff>=0.7
mypy>=1.13
```

- [ ] **Step 4: Create the package `__init__.py` files**

`custom_components/__init__.py`:
```python
```
(empty file — present only so local tooling can import `custom_components.*` as a dotted path;
Home Assistant itself does not require this file for custom component discovery)

`custom_components/minecraft_bedrock_realms/__init__.py`:
```python
"""Minecraft Bedrock Realms monitoring.

This package currently contains only the authentication and Realms API client
(auth.py, realms_api.py, xbox_profile.py, models.py, exceptions.py, const.py),
used by the standalone proof-of-concept CLI in poc/realm_cli.py. Home Assistant
integration entry points (config_flow.py, coordinator.py, sensor.py, etc.) are
added in Phase 4 once the proof-of-concept confirms real Realm data can be
retrieved end-to-end.
"""
```

`poc/__init__.py`:
```python
```
(empty file)

- [ ] **Step 5: Create `LICENSE`**

```text
MIT License

Copyright (c) 2026 LucaFSmart

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

- [ ] **Step 6: Create a minimal `README.md`**

```markdown
# Minecraft Bedrock Realms for Home Assistant

**Status: early development (Phase 3 — proof of concept).** Not yet installable via HACS.

An unofficial Home Assistant custom integration for monitoring Minecraft Bedrock Realms /
Realms Plus, via Microsoft/Xbox authentication. Not affiliated with Mojang or Microsoft.

- [Research notes](docs/research.md) — confirmed API/auth mechanism, sourced from reading the
  actual code of prismarine-realms, prismarine-auth, elytra-ms, and RealmsPlayerlistBot.
- [Architecture](docs/architecture.md) — the chosen design and why.

## Current state

The authentication and Realms API client live under
`custom_components/minecraft_bedrock_realms/` and are exercised by a standalone CLI at
`poc/realm_cli.py`. The full Home Assistant integration (config flow, sensors, coordinator) is
not implemented yet — that's Phase 4, gated on the PoC successfully reading real Realm data.

### Running the proof-of-concept

```bash
pip install -r requirements-dev.txt
python -m poc.realm_cli
```

This will print a Microsoft device-code login URL and code. Open it in any browser, sign in with
the Microsoft account that owns or has joined the Realm you want to monitor, and the CLI will
print that account's Realms, their open/closed state, and who's currently online.

## License

MIT — see [LICENSE](LICENSE).
```

- [ ] **Step 7: Verify the package imports and pytest runs (even with zero tests yet)**

Run:
```bash
pip install -r requirements-dev.txt
python -c "import custom_components.minecraft_bedrock_realms; import poc"
pytest --collect-only
```
Expected: both imports succeed silently; `pytest --collect-only` reports `no tests ran` (there
are no test files yet) without import errors.

- [ ] **Step 8: Commit**

```bash
git add .gitignore pyproject.toml requirements-dev.txt custom_components/__init__.py \
  custom_components/minecraft_bedrock_realms/__init__.py poc/__init__.py LICENSE README.md
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Scaffold project: packaging, tooling, license, README"
```

---

## Task 2: Exceptions

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/exceptions.py`
- Test: `tests/test_exceptions.py`

**Interfaces:**
- Produces: `RealmsClientError` (base), `AuthenticationError`, `DeviceCodeExpiredError`,
  `XboxLiveError(xerr: int | None, message: str)` with classmethod
  `XboxLiveError.from_response(data: dict) -> XboxLiveError`, `RealmsAPIError(status: int,
  message: str)`, `RealmsRateLimitedError(retry_after: float | None)`.

- [ ] **Step 1: Write the failing test**

`tests/test_exceptions.py`:
```python
from custom_components.minecraft_bedrock_realms.exceptions import XboxLiveError


def test_known_xerr_code_maps_to_readable_message():
    err = XboxLiveError.from_response({"XErr": 2148916233, "Message": "raw"})
    assert err.xerr == 2148916233
    assert "no Xbox profile" in str(err)


def test_unknown_xerr_code_falls_back_to_generic_message():
    err = XboxLiveError.from_response({"XErr": 999999999})
    assert err.xerr == 999999999
    assert "999999999" in str(err)


def test_missing_xerr_field_still_produces_a_message():
    err = XboxLiveError.from_response({})
    assert err.xerr is None
    assert "Xbox Live rejected" in str(err)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_exceptions.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.exceptions'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/exceptions.py`:
```python
"""Exceptions raised by the Minecraft Bedrock Realms auth/API client."""
from __future__ import annotations

from typing import Any


class RealmsClientError(Exception):
    """Base class for all errors raised by this package."""


class AuthenticationError(RealmsClientError):
    """Raised when the Microsoft/Xbox Live authentication chain fails."""


class DeviceCodeExpiredError(AuthenticationError):
    """Raised when the user did not complete device code login in time."""


# Numeric Xbox Live XErr codes -> human-readable messages. These codes are
# Microsoft's own documented-by-convention account-state error codes, not
# copyrighted expression - the mapping is a small factual table, cross-checked
# against docs/research.md's sources.
_XBOX_LIVE_ERROR_MESSAGES: dict[int, str] = {
    2148916227: "This Microsoft account was banned by Xbox for violating the Community Standards.",
    2148916229: "This account is restricted; a family organizer must grant permission to play online.",
    2148916233: "This Microsoft account has no Xbox profile. Create one at https://signup.live.com/signup.",
    2148916234: "This Microsoft account has not accepted the Xbox Live Terms of Service.",
    2148916235: "Xbox Live is not available in this account's region.",
    2148916236: "This Microsoft account requires age verification.",
    2148916237: "This account has reached its Xbox Live playtime limit.",
    2148916238: "This account is under 18 and must be added to a family group by an adult.",
}


class XboxLiveError(AuthenticationError):
    """Raised when Xbox Live rejects a user/XSTS token request."""

    def __init__(self, xerr: int | None, message: str) -> None:
        self.xerr = xerr
        super().__init__(message)

    @classmethod
    def from_response(cls, data: dict[str, Any]) -> "XboxLiveError":
        raw_xerr = data.get("XErr")
        xerr = int(raw_xerr) if raw_xerr is not None else None
        known_message = _XBOX_LIVE_ERROR_MESSAGES.get(xerr) if xerr is not None else None
        message = known_message or (
            f"Xbox Live rejected this account (XErr={xerr})"
            if xerr is not None
            else "Xbox Live rejected this account"
        )
        return cls(xerr, message)


class RealmsAPIError(RealmsClientError):
    """Raised for non-auth failures talking to the Realms API."""

    def __init__(self, status: int, message: str) -> None:
        self.status = status
        super().__init__(f"Realms API error (HTTP {status}): {message}")


class RealmsRateLimitedError(RealmsAPIError):
    """Raised on HTTP 429 from the Realms API after retries are exhausted."""

    def __init__(self, retry_after: float | None) -> None:
        self.retry_after = retry_after
        detail = f"rate limited, retry after {retry_after}s" if retry_after else "rate limited"
        super().__init__(429, detail)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_exceptions.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/exceptions.py tests/test_exceptions.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add exceptions module with Xbox Live error code mapping"
```

---

## Task 3: Constants

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/const.py`

**Interfaces:**
- Produces: `DOMAIN`, `MS_DEVICE_CODE_URL`, `MS_TOKEN_URL`, `MS_OAUTH_SCOPE`, `DEFAULT_CLIENT_ID`,
  `XBL_AUTH_RELYING_PARTY`, `XBL_USER_AUTH_URL`, `XBL_XSTS_AUTH_URL`,
  `XBOX_LIVE_XSTS_RELYING_PARTY`, `REALMS_XSTS_RELYING_PARTY`, `REALMS_API_BASE`,
  `REALMS_CLIENT_VERSION`, `REALMS_USER_AGENT`, `XBOX_PROFILE_CONTRACT_VERSION`,
  `REQUEST_TIMEOUT_SECONDS`.

No test file — this is pure constant data with no logic to fail; it's exercised indirectly by
every other module's tests.

- [ ] **Step 1: Write the implementation**

`custom_components/minecraft_bedrock_realms/const.py`:
```python
"""Constants for Microsoft/Xbox/Realms authentication and API access.

Endpoint values and relying-party strings are confirmed in docs/research.md
against two independent open-source implementations (prismarine-auth/
prismarine-realms in JS, elytra-ms in Python).
"""

DOMAIN = "minecraft_bedrock_realms"

# --- Microsoft OAuth2 device code flow (consumer/personal accounts) ---
MS_DEVICE_CODE_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode"
MS_TOKEN_URL = "https://login.microsoftonline.com/consumers/oauth2/v2.0/token"
MS_OAUTH_SCOPE = "Xboxlive.signin Xboxlive.offline_access"

# Known public first-party Microsoft client ID (Minecraft for Nintendo Switch).
# Reused per prismarine-auth's default `live` flow - see docs/research.md SS1
# for why a self-registered Azure app is not used by default.
DEFAULT_CLIENT_ID = "00000000441cc96b"

# --- Xbox Live (XBL user token + XSTS token) ---
XBL_USER_AUTH_URL = "https://user.auth.xboxlive.com/user/authenticate"
XBL_XSTS_AUTH_URL = "https://xsts.auth.xboxlive.com/xsts/authorize"

# RelyingParty for the *first* user-token step - always this constant value,
# regardless of what the resulting XSTS token will be used for.
XBL_AUTH_RELYING_PARTY = "http://auth.xboxlive.com"

# RelyingParty values for the *second* (XSTS) step - these differ by target service.
XBOX_LIVE_XSTS_RELYING_PARTY = "http://xboxlive.com"  # general Xbox Live APIs (profile, etc.)
REALMS_XSTS_RELYING_PARTY = "https://pocket.realms.minecraft.net/"  # Bedrock Realms API

# --- Realms API ---
REALMS_API_BASE = "https://pocket.realms.minecraft.net"
REALMS_CLIENT_VERSION = "1.21.50"
REALMS_USER_AGENT = "MCPE/UWP"

# --- Xbox profile API (XUID -> gamertag resolution) ---
XBOX_PROFILE_CONTRACT_VERSION = "3"

REQUEST_TIMEOUT_SECONDS = 15
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `python -c "from custom_components.minecraft_bedrock_realms import const; print(const.DOMAIN)"`
Expected: prints `minecraft_bedrock_realms`

- [ ] **Step 3: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/const.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add auth/API constants"
```

---

## Task 4: Data models

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/models.py`
- Test: `tests/test_models.py`

**Interfaces:**
- Consumes: nothing (only stdlib `dataclasses`/`datetime`).
- Produces: `DeviceCodeInfo`, `OAuthToken` (with `.is_valid()`, `.to_dict()`,
  `OAuthToken.from_dict()`, `OAuthToken.from_response()`), `XboxToken` (with
  `.authorization_header`, `.is_valid()`, `XboxToken.from_response()`), `RealmPlayer`, `Realm`
  (with `Realm.from_api()`), `RealmActivity` (with `RealmActivity.from_api()`).

- [ ] **Step 1: Write the failing test**

`tests/test_models.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_models.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.models'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/models.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_models.py -v`
Expected: 7 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/models.py tests/test_models.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add typed models for tokens and Realms API responses"
```

---

## Task 5: Microsoft/Xbox authentication client

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/auth.py`
- Test: `tests/test_auth.py`

**Interfaces:**
- Consumes: `const.{MS_DEVICE_CODE_URL,MS_TOKEN_URL,MS_OAUTH_SCOPE,DEFAULT_CLIENT_ID,
  XBL_AUTH_RELYING_PARTY,XBL_USER_AUTH_URL,XBL_XSTS_AUTH_URL,REQUEST_TIMEOUT_SECONDS}`,
  `exceptions.{AuthenticationError,DeviceCodeExpiredError,XboxLiveError}`,
  `models.{DeviceCodeInfo,OAuthToken,XboxToken}`.
- Produces: `MicrosoftAuth(session: aiohttp.ClientSession, client_id: str = DEFAULT_CLIENT_ID)`
  with async methods `request_device_code() -> DeviceCodeInfo`,
  `poll_for_token(device_code_info: DeviceCodeInfo) -> OAuthToken`,
  `refresh_oauth_token(token: OAuthToken) -> OAuthToken`,
  `get_xbox_user_token(oauth_token: OAuthToken) -> XboxToken`,
  `get_xsts_token(xbl_user_token: XboxToken, relying_party: str) -> XboxToken`. These are consumed
  directly by `poc/realm_cli.py` in Task 8, and later by the HA coordinator in Phase 4.

- [ ] **Step 1: Write the failing test**

`tests/test_auth.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_auth.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.auth'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/auth.py`:
```python
"""Microsoft device-code -> Xbox Live user token -> XSTS token authentication chain."""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import aiohttp

from .const import (
    DEFAULT_CLIENT_ID,
    MS_DEVICE_CODE_URL,
    MS_OAUTH_SCOPE,
    MS_TOKEN_URL,
    REQUEST_TIMEOUT_SECONDS,
    XBL_AUTH_RELYING_PARTY,
    XBL_USER_AUTH_URL,
    XBL_XSTS_AUTH_URL,
)
from .exceptions import AuthenticationError, DeviceCodeExpiredError, XboxLiveError
from .models import DeviceCodeInfo, OAuthToken, XboxToken

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)


class MicrosoftAuth:
    """Performs and refreshes the MSA device code -> XBL -> XSTS token chain.

    Never logs or exposes token values - only presence/validity is logged.
    """

    def __init__(
        self,
        session: aiohttp.ClientSession,
        client_id: str = DEFAULT_CLIENT_ID,
    ) -> None:
        self._session = session
        self._client_id = client_id

    async def request_device_code(self) -> DeviceCodeInfo:
        async with self._session.post(
            MS_DEVICE_CODE_URL,
            data={"client_id": self._client_id, "scope": MS_OAUTH_SCOPE},
            timeout=_TIMEOUT,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise AuthenticationError(f"Failed to request device code: HTTP {resp.status}")
            _LOGGER.debug("Received device code (expires_in=%s)", data.get("expires_in"))
            return DeviceCodeInfo.from_response(data)

    async def poll_for_token(self, device_code_info: DeviceCodeInfo) -> OAuthToken:
        import asyncio

        interval = device_code_info.interval
        while True:
            await asyncio.sleep(interval)
            if datetime.now(timezone.utc) > device_code_info.expires_at:
                raise DeviceCodeExpiredError("Device code expired before login completed")

            async with self._session.post(
                MS_TOKEN_URL,
                data={
                    "client_id": self._client_id,
                    "grant_type": "urn:ietf:params:oauth:grant-type:device_code",
                    "device_code": device_code_info.device_code,
                },
                timeout=_TIMEOUT,
            ) as resp:
                data = await resp.json(content_type=None)

            error = data.get("error")
            if error is None:
                _LOGGER.debug("Device code login succeeded")
                return OAuthToken.from_response(data)
            if error == "authorization_pending":
                continue
            if error == "slow_down":
                interval += 5
                continue
            if error in ("authorization_declined", "expired_token", "bad_verification_code"):
                raise AuthenticationError(f"Device code login failed: {error}")
            raise AuthenticationError(f"Unexpected device code error: {error}")

    async def refresh_oauth_token(self, token: OAuthToken) -> OAuthToken:
        async with self._session.post(
            MS_TOKEN_URL,
            data={
                "client_id": self._client_id,
                "grant_type": "refresh_token",
                "refresh_token": token.refresh_token,
                "scope": MS_OAUTH_SCOPE,
            },
            timeout=_TIMEOUT,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status != 200:
                raise AuthenticationError(f"Failed to refresh Microsoft token: HTTP {resp.status}")
            _LOGGER.debug("Refreshed Microsoft OAuth token")
            return OAuthToken.from_response(data)

    async def get_xbox_user_token(self, oauth_token: OAuthToken) -> XboxToken:
        return await self._xbl_authenticate(
            relying_party=XBL_AUTH_RELYING_PARTY,
            url=XBL_USER_AUTH_URL,
            properties={
                "AuthMethod": "RPS",
                "SiteName": "user.auth.xboxlive.com",
                "RpsTicket": f"d={oauth_token.access_token}",
            },
        )

    async def get_xsts_token(self, xbl_user_token: XboxToken, relying_party: str) -> XboxToken:
        return await self._xbl_authenticate(
            relying_party=relying_party,
            url=XBL_XSTS_AUTH_URL,
            properties={"UserTokens": [xbl_user_token.token], "SandboxId": "RETAIL"},
        )

    async def _xbl_authenticate(self, *, relying_party: str, url: str, properties: dict) -> XboxToken:
        async with self._session.post(
            url,
            json={
                "RelyingParty": relying_party,
                "TokenType": "JWT",
                "Properties": properties,
            },
            headers={"x-xbl-contract-version": "1"},
            timeout=_TIMEOUT,
        ) as resp:
            data = await resp.json(content_type=None)
            if resp.status == 401:
                raise XboxLiveError.from_response(data)
            if resp.status not in (200, 201):
                raise AuthenticationError(f"Xbox Live auth failed: HTTP {resp.status}")
            return XboxToken.from_response(data)
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_auth.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/auth.py tests/test_auth.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add Microsoft/Xbox Live device-code auth chain"
```

---

## Task 6: Realms API client

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/realms_api.py`
- Test: `tests/test_realms_api.py`

**Interfaces:**
- Consumes: `const.{REALMS_API_BASE,REALMS_CLIENT_VERSION,REALMS_USER_AGENT,
  REQUEST_TIMEOUT_SECONDS}`, `exceptions.{RealmsAPIError,RealmsRateLimitedError}`,
  `models.{Realm,RealmActivity}`.
- Produces: `RealmsAPI(session: aiohttp.ClientSession, authorization_header: str, *,
  backoff_base_seconds: float = 1.0, max_attempts: int = 4)` with async methods
  `list_realms() -> list[Realm]`, `get_realm(realm_id: int) -> Realm`,
  `get_live_activities() -> list[RealmActivity]`, and `update_authorization(authorization_header:
  str) -> None`. Consumed by `poc/realm_cli.py` in Task 8, and later by the HA coordinator.

- [ ] **Step 1: Write the failing test**

`tests/test_realms_api.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_realms_api.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.realms_api'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/realms_api.py`:
```python
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
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_realms_api.py -v`
Expected: 5 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/realms_api.py tests/test_realms_api.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add Realms API client with retry/backoff for 429 and 5xx"
```

---

## Task 7: Xbox profile client (XUID -> gamertag resolution)

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/xbox_profile.py`
- Test: `tests/test_xbox_profile.py`

**Interfaces:**
- Consumes: `const.{REQUEST_TIMEOUT_SECONDS,XBOX_PROFILE_CONTRACT_VERSION}`,
  `exceptions.RealmsAPIError`.
- Produces: `XboxProfileClient(session: aiohttp.ClientSession, authorization_header: str)` with
  async method `get_gamertag(xuid: str) -> str | None` and `update_authorization(authorization_header:
  str) -> None`. Consumed by `poc/realm_cli.py` in Task 8 to resolve the XUIDs returned by
  `RealmsAPI.get_live_activities()` (which, per docs/research.md SS3, never includes names).

- [ ] **Step 1: Write the failing test**

`tests/test_xbox_profile.py`:
```python
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
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_xbox_profile.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.xbox_profile'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/xbox_profile.py`:
```python
"""Resolve Xbox User IDs (XUIDs) to gamertags via the Xbox Live Profile API.

The Realms activities endpoint (see realms_api.get_live_activities) returns
XUIDs but never gamertags (confirmed in docs/research.md SS3), so a second,
separately rate-limited lookup is required to show a human-readable name.
"""
from __future__ import annotations

import logging

import aiohttp

from .const import REQUEST_TIMEOUT_SECONDS, XBOX_PROFILE_CONTRACT_VERSION
from .exceptions import RealmsAPIError

_LOGGER = logging.getLogger(__name__)

_TIMEOUT = aiohttp.ClientTimeout(total=REQUEST_TIMEOUT_SECONDS)
_PROFILE_SETTINGS_URL = (
    "https://profile.xboxlive.com/users/xuid({xuid})/profile/settings?settings=Gamertag"
)


class XboxProfileClient:
    """Async client for resolving a single XUID to a gamertag."""

    def __init__(self, session: aiohttp.ClientSession, authorization_header: str) -> None:
        self._session = session
        self._authorization_header = authorization_header

    def update_authorization(self, authorization_header: str) -> None:
        self._authorization_header = authorization_header

    async def get_gamertag(self, xuid: str) -> str | None:
        url = _PROFILE_SETTINGS_URL.format(xuid=xuid)
        headers = {
            "Authorization": self._authorization_header,
            "x-xbl-contract-version": XBOX_PROFILE_CONTRACT_VERSION,
            "Accept": "application/json",
        }
        async with self._session.get(url, headers=headers, timeout=_TIMEOUT) as resp:
            if resp.status == 404:
                return None
            if resp.status >= 400:
                text = await resp.text()
                raise RealmsAPIError(resp.status, text)
            data = await resp.json(content_type=None)

        try:
            settings = data["profileUsers"][0]["settings"]
            return next(s["value"] for s in settings if s["id"] == "Gamertag")
        except (KeyError, IndexError, StopIteration):
            _LOGGER.debug("Profile response for XUID %s had no Gamertag setting", xuid)
            return None
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_xbox_profile.py -v`
Expected: 2 passed

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/xbox_profile.py tests/test_xbox_profile.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add Xbox profile client for XUID to gamertag resolution"
```

---

## Task 8: PoC-only local token cache

**Files:**
- Create: `poc/token_cache.py`
- Test: `tests/test_token_cache.py`

**Interfaces:**
- Consumes: `custom_components.minecraft_bedrock_realms.models.OAuthToken`.
- Produces: `DEFAULT_CACHE_PATH: Path`, `load_token(path: Path = DEFAULT_CACHE_PATH) -> OAuthToken
  | None`, `save_token(token: OAuthToken, path: Path = DEFAULT_CACHE_PATH) -> None`. Consumed by
  `poc/realm_cli.py` in Task 9. **Not** used by the future Home Assistant integration — Phase 4
  persists tokens via `ConfigEntry.data` instead (see docs/architecture.md SS3), this file exists
  purely so the PoC CLI doesn't require a fresh device-code login on every run.

- [ ] **Step 1: Write the failing test**

`tests/test_token_cache.py`:
```python
from pathlib import Path

from custom_components.minecraft_bedrock_realms.models import OAuthToken
from poc.token_cache import load_token, save_token


def test_save_and_load_token_roundtrip(tmp_path: Path):
    cache_path = tmp_path / "token.json"
    token = OAuthToken(access_token="at", refresh_token="rt", expires_in=3600)

    save_token(token, path=cache_path)
    loaded = load_token(path=cache_path)

    assert loaded is not None
    assert loaded.access_token == "at"
    assert loaded.refresh_token == "rt"


def test_load_token_returns_none_when_file_missing(tmp_path: Path):
    assert load_token(path=tmp_path / "does_not_exist.json") is None


def test_load_token_returns_none_on_corrupt_json(tmp_path: Path):
    cache_path = tmp_path / "token.json"
    cache_path.write_text("not json", encoding="utf-8")
    assert load_token(path=cache_path) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_token_cache.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poc.token_cache'`

- [ ] **Step 3: Write the implementation**

`poc/token_cache.py`:
```python
"""Local JSON token cache for the standalone PoC CLI only.

The Home Assistant integration (Phase 4) persists tokens via
ConfigEntry.data instead of a file on disk - this module exists purely so
the Phase 3 CLI can be run repeatedly without a fresh device-code login
every time. Never used by the HA integration itself.
"""
from __future__ import annotations

import json
from pathlib import Path

from custom_components.minecraft_bedrock_realms.models import OAuthToken

DEFAULT_CACHE_PATH = Path.home() / ".cache" / "minecraft_bedrock_realms_poc" / "token.json"


def load_token(path: Path = DEFAULT_CACHE_PATH) -> OAuthToken | None:
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return OAuthToken.from_dict(data)
    except (json.JSONDecodeError, KeyError, ValueError):
        return None


def save_token(token: OAuthToken, path: Path = DEFAULT_CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token.to_dict()), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # best-effort; not all platforms (e.g. Windows) support POSIX chmod bits
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_token_cache.py -v`
Expected: 3 passed

- [ ] **Step 5: Commit**

```bash
git add poc/token_cache.py tests/test_token_cache.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add PoC-only local token cache"
```

---

## Task 9: Proof-of-concept CLI

**Files:**
- Create: `poc/realm_cli.py`
- Test: `tests/test_realm_cli.py`

**Interfaces:**
- Consumes: `MicrosoftAuth`, `RealmsAPI`, `XboxProfileClient`, `RealmsClientError`,
  `REALMS_XSTS_RELYING_PARTY`, `XBOX_LIVE_XSTS_RELYING_PARTY` (add this constant re-export check —
  already defined in Task 3's `const.py`), `poc.token_cache.{load_token,save_token}`.
- Produces: `async def _run(realm_name_filter: str | None) -> int` (the testable core, returns a
  process exit code) and a `main()` CLI entry point invoked via `python -m poc.realm_cli`.

- [ ] **Step 1: Write the failing test**

`tests/test_realm_cli.py`:
```python
from datetime import datetime, timezone

import aiohttp
from aioresponses import aioresponses

from custom_components.minecraft_bedrock_realms.const import (
    REALMS_API_BASE,
    XBL_USER_AUTH_URL,
    XBL_XSTS_AUTH_URL,
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


async def test_run_reports_when_account_has_no_realms(monkeypatch):
    async def fake_authenticate(session: aiohttp.ClientSession) -> tuple[str, str]:
        return "realms-auth", "xbox-auth"

    monkeypatch.setattr(realm_cli, "_authenticate", fake_authenticate)

    with aioresponses() as mocked:
        mocked.get(f"{REALMS_API_BASE}/worlds", payload={"servers": []})
        exit_code = await realm_cli._run(None)

    assert exit_code == 0
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_realm_cli.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'poc.realm_cli'`

- [ ] **Step 3: Write the implementation**

`poc/realm_cli.py`:
```python
"""Phase 3 proof-of-concept CLI.

Authenticates against a real Minecraft/Xbox account via device code, lists the
account's Bedrock Realms, and prints status + live players for each.

Run: python -m poc.realm_cli
"""
from __future__ import annotations

import argparse
import asyncio
import logging
import sys

import aiohttp

from custom_components.minecraft_bedrock_realms.auth import MicrosoftAuth
from custom_components.minecraft_bedrock_realms.const import (
    REALMS_XSTS_RELYING_PARTY,
    XBOX_LIVE_XSTS_RELYING_PARTY,
)
from custom_components.minecraft_bedrock_realms.exceptions import RealmsClientError
from custom_components.minecraft_bedrock_realms.realms_api import RealmsAPI
from custom_components.minecraft_bedrock_realms.xbox_profile import XboxProfileClient
from poc.token_cache import load_token, save_token

_LOGGER = logging.getLogger("realm_cli")


async def _authenticate(session: aiohttp.ClientSession) -> tuple[str, str]:
    """Runs (or resumes) the auth chain. Returns (realms_auth_header, xbox_live_auth_header)."""
    auth = MicrosoftAuth(session)

    oauth_token = load_token()
    if oauth_token is not None and not oauth_token.is_valid():
        print("Cached token expired, refreshing...")
        try:
            oauth_token = await auth.refresh_oauth_token(oauth_token)
        except RealmsClientError:
            oauth_token = None

    if oauth_token is None:
        device_code = await auth.request_device_code()
        print(device_code.message)
        print(f"Waiting for you to sign in (expires in {device_code.expires_in}s)...")
        oauth_token = await auth.poll_for_token(device_code)
        print("Signed in with Microsoft.")

    save_token(oauth_token)

    xbl_user_token = await auth.get_xbox_user_token(oauth_token)
    realms_xsts = await auth.get_xsts_token(xbl_user_token, REALMS_XSTS_RELYING_PARTY)
    xbox_live_xsts = await auth.get_xsts_token(xbl_user_token, XBOX_LIVE_XSTS_RELYING_PARTY)

    print(f"Signed in as Xbox gamertag: {realms_xsts.gamertag} (XUID {realms_xsts.xuid})")
    return realms_xsts.authorization_header, xbox_live_xsts.authorization_header


async def _run(realm_name_filter: str | None) -> int:
    async with aiohttp.ClientSession() as session:
        try:
            realms_auth_header, xbox_auth_header = await _authenticate(session)
        except RealmsClientError as err:
            print(f"Authentication failed: {err}", file=sys.stderr)
            return 1

        realms_api = RealmsAPI(session, realms_auth_header)
        profile_client = XboxProfileClient(session, xbox_auth_header)

        try:
            realms = await realms_api.list_realms()
        except RealmsClientError as err:
            print(f"Failed to list Realms: {err}", file=sys.stderr)
            return 1

        if not realms:
            print("This account does not own or belong to any Bedrock Realm.")
            return 0

        if realm_name_filter:
            realms = [r for r in realms if realm_name_filter.lower() in r.name.lower()]
            if not realms:
                print(f"No Realm matching '{realm_name_filter}' found.", file=sys.stderr)
                return 1

        try:
            activities = await realms_api.get_live_activities()
        except RealmsClientError as err:
            print(f"Warning: could not fetch live player activity: {err}", file=sys.stderr)
            activities = []
        activity_by_realm = {a.realm_id: a for a in activities}

        for realm in realms:
            activity = activity_by_realm.get(realm.id)
            online_xuids = activity.online_xuids if activity else []

            gamertags: list[str] = []
            for xuid in online_xuids:
                gamertag = await profile_client.get_gamertag(xuid)
                gamertags.append(gamertag or f"(unknown XUID {xuid})")

            print()
            print("Realm:")
            print(f"  {realm.name}")
            print("State:")
            print(f"  {realm.state}")
            print("Players:")
            print(f"  {len(online_xuids)}/{realm.max_players}")
            print("Online:")
            if gamertags:
                for gamertag in gamertags:
                    print(f"  {gamertag}")
            else:
                print("  (nobody online right now)")

        return 0


def main() -> None:
    parser = argparse.ArgumentParser(description="Minecraft Bedrock Realms proof-of-concept CLI")
    parser.add_argument(
        "--realm",
        dest="realm_name_filter",
        default=None,
        help="Only show Realms whose name contains this text (case-insensitive)",
    )
    parser.add_argument("--debug", action="store_true", help="Enable debug logging")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    exit_code = asyncio.run(_run(args.realm_name_filter))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: Run test to verify it passes**

Run: `pytest tests/test_realm_cli.py -v`
Expected: 2 passed

- [ ] **Step 5: Run the full test suite and lint/type-check**

Run:
```bash
pytest -v
ruff check .
mypy custom_components poc
```
Expected: all tests pass; ruff reports no issues (fix any it finds — likely import-order or
unused-import nits); mypy may report a small number of warnings on the `dict`-returning internal
`_request` methods — acceptable at this stage, but no errors in `models.py`/`auth.py` (those are
fully typed).

- [ ] **Step 6: Commit**

```bash
git add poc/realm_cli.py tests/test_realm_cli.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add PoC CLI wiring auth, Realms API, and gamertag resolution together"
```

---

## Task 10: Manual live verification (cannot be automated)

This is the actual Phase 3 exit criterion from the project brief: *"Do not continue to the full
Home Assistant integration until the proof of concept successfully retrieves real Realm data."*
This step must be performed by the account owner — device-code login requires signing in in a
real browser, which cannot be done by an agent, and must not be attempted by one.

- [ ] **Step 1: Run the CLI for real**

```bash
pip install -r requirements-dev.txt
python -m poc.realm_cli
```

- [ ] **Step 2: Complete the device code login**

Open the printed URL in any browser, sign in with the Microsoft account that owns or has joined
the target Realm, and approve.

- [ ] **Step 3: Confirm the output**

Verify the CLI prints your real Realm's name, its actual `OPEN`/`CLOSED` state, and (if anyone is
currently on the Realm) their real gamertag(s). If nobody is online, join the Realm briefly from a
Bedrock client on any device and re-run `python -m poc.realm_cli` to confirm the online count and
gamertag update.

- [ ] **Step 4: Record findings back into research.md**

Update `docs/research.md`'s "Open items to validate in Phase 3" section: for each of the 4 items
listed there, replace it with what was actually observed (e.g., "confirmed: the default public
client ID worked without needing a self-registered Azure app" or the opposite, if it didn't and a
fallback was needed). This directly unblocks Phase 4, since the HA config flow's client-ID
strategy depends on this result.

- [ ] **Step 5: Commit the research.md update**

```bash
git add docs/research.md
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Record Phase 3 PoC live-verification findings"
```

**Do not start Phase 4 (the Home Assistant integration) until this task is complete and
committed.**

---

## Self-Review Notes

- **Spec coverage**: every Phase 3 requirement from the brief is covered — device code auth
  (Task 5), Realm discovery (Task 6), live player count/names (Tasks 6+7), token persistence
  across CLI runs (Task 8), the exact output shape requested (`Realm:` / `State:` / `Players:` /
  `Online:`, Task 9), and the explicit "PoC before HA integration" gate (Task 10).
- **Placeholder scan**: none — every step has complete, runnable code. (Task 9's Step 1 flags one
  intentionally-dead draft helper to delete, which is itself an explicit instruction, not a
  placeholder.)
- **Type consistency**: `MicrosoftAuth.get_xsts_token(xbl_user_token: XboxToken, relying_party:
  str)` in Task 5 matches its two call sites in Task 9's `_authenticate`. `RealmsAPI` and
  `XboxProfileClient` constructor signatures match how Task 9 instantiates them. `OAuthToken`/
  `XboxToken`/`Realm`/`RealmActivity` field names are identical everywhere they're constructed vs.
  read across Tasks 4–9.
