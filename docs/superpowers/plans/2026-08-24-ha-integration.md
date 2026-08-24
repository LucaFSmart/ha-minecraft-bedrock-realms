# Phase 4: Home Assistant Integration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn the Phase 3 auth/API client (`custom_components/minecraft_bedrock_realms/{auth,realms_api,xbox_profile,models,exceptions,const}.py`, already built and tested) into a complete, installable Home Assistant custom integration: config flow (device-code login + Realm selection + options + reauth), a `DataUpdateCoordinator`, sensors, binary sensors, and diagnostics — matching the design in `docs/architecture.md`.

**Architecture:** One `DataUpdateCoordinator` per config entry polls `RealmsAPI.list_realms()` + `RealmsAPI.get_live_activities()` together every update cycle (both cover every selected Realm in one HTTP call each, per `docs/research.md` §3), diffs online-player sets to fire join/leave events, and persists refreshed Microsoft tokens back into the config entry. One HA device per Realm; entities read from coordinator data, never call the API directly.

**Tech Stack:** Home Assistant 2026.x custom integration conventions (`DataUpdateCoordinator`, `ConfigFlow` with progress steps for the device-code wait, `CoordinatorEntity`), `pytest-homeassistant-custom-component` pinned to the same `2026.8.3` version as the target Home Assistant release for tests.

## Global Constraints

- Tokens are never logged, never appear in entity state/attributes, never appear in diagnostics output (diagnostics.py must explicitly redact them).
- All I/O is async; only `aiohttp` via Home Assistant's shared session (`homeassistant.helpers.aiohttp_client.async_get_clientsession(hass)`) — never a second HTTP client.
- No destructive Realm actions (open/close/reset/delete/ban) anywhere in this integration.
- The first successful coordinator refresh after (re)start establishes baseline online-player state without firing `minecraft_realm_player_joined`/`minecraft_realm_player_left` events. A failed refresh never overwrites the last-known-good online-player state.
- Default polling interval is 60 seconds; user-configurable to 15/30/60/120/300 seconds via the options flow.
- Realm status sensor attributes must only include fields the Realms API actually returns (confirmed in `docs/research.md`): realm id, owner, owner XUID, active slot, member. Do **not** add a "Minecraft version" attribute — the `/worlds` and `/worlds/{id}` responses this project uses do not return one, and inventing one would violate "do not claim functionality works unless verified."
- Git commits use author `LucaFSmart <197988000+LucaFSmart@users.noreply.github.com>` via `git -c user.name=... -c user.email=... commit ...` — never edit git config.
- `custom_components/minecraft_bedrock_realms/{auth,realms_api,xbox_profile,models,exceptions,const}.py` already exist from Phase 3 and are already unit-tested; this plan extends them (adds new fields/methods where noted) but must not change their existing tested public signatures.

### Windows test environment (already set up - read before running any test in this plan)

The dev machine this plan is executed on is Windows, where Home Assistant's own test harness does
not work out of the box. This was discovered and fixed once, before Task 3, so every task from
here on can just run tests normally - but the fix depends on machine state that isn't committed to
git (it lives in `.venv/`, which is git-ignored) and must exist for tests to pass:

1. **A dedicated venv at `.venv/`, created with `python3` (resolves to Python 3.14.6 on this
   machine) — not the plain `python`/`pip` commands, which resolve to an unrelated, older Python
   3.11 environment.** Every command in every task (`pytest`, `pip`, `ruff`, `mypy`) must be run as
   `.venv/Scripts/python -m <tool>`. If `.venv/` doesn't exist: `python3 -m venv .venv`, then
   `.venv/Scripts/python -m pip install -r requirements-dev.txt`.
2. **`requirements-dev.txt` pins `aiohttp==3.14.3` exactly** (forced by `homeassistant==2026.8.3`,
   which hard-pins it) **and installs `aioresponses` from an unmerged upstream git branch**
   (`agners/aioresponses@fix-aiohttp-3.14-stream-writer`) because the latest PyPI release
   (0.7.9) doesn't support aiohttp 3.14's new required `stream_writer` kwarg on `ClientResponse`.
   Both are already correctly pinned in the committed `requirements-dev.txt` — don't "fix" them
   back to a plain PyPI `aioresponses` version or a `<3.14` aiohttp bound.
3. **Three small stub files must exist in `.venv/Lib/site-packages/`** (created once, not part of
   any git commit, must be recreated if `.venv/` is ever deleted and rebuilt):
   - `fcntl.py` — `homeassistant/runner.py` does `import fcntl` at module level (a POSIX-only
     stdlib module, absent on Windows) purely to take an advisory single-instance lock that no
     unit test in this project ever exercises. Stub: module-level `LOCK_EX = 2`, `LOCK_SH = 1`,
     `LOCK_UN = 8`, `LOCK_NB = 4` constants, plus no-op `flock(fd, operation)` and
     `lockf(fd, operation, length=0, start=0, whence=0)` functions.
   - `resource.py` — same situation, `homeassistant/util/resource.py` does `import resource`
     (also POSIX-only) to read/set the process's open-file-descriptor limit, again never called
     during unit tests. Stub: `RLIMIT_NOFILE = 7` constant, `getrlimit(resource_id)` returning
     `(1024, 4096)`, no-op `setrlimit(resource_id, limits)`.
   - `sitecustomize.py` — the real fix, auto-loaded by Python's `site` module at interpreter
     startup (before pytest or any plugin runs). Root cause: Windows has no real
     `socket.socketpair()`, so CPython falls back to building a loopback TCP pair via
     `socket.socket(...)` - which is exactly what asyncio's event loop uses internally for its
     self-wakeup pipe, on every async test. `pytest-homeassistant-custom-component` (via
     `pytest_socket`) replaces `socket.socket` with a guard that only allows AF_UNIX-family
     sockets through (correct on Linux/macOS, where the real self-pipe *is* AF_UNIX); on Windows
     the fallback is AF_INET, so the guard blocks it and every async test fails at event-loop
     creation with `HASocketBlockedError`, before any test code or mocked HTTP call runs. Fix:
     capture the pristine, unpatched `socket.socket` class at interpreter startup (before any test
     plugin can monkeypatch it) and replace `socket.socketpair`/`socket._fallback_socketpair` with
     a version that builds the loopback pair entirely from that pristine class - including for the
     `accept()`-returned peer socket, built via the class's private `_accept()` plus
     `_real_socket_class(family, type, proto, fileno=fd)` rather than calling `.accept()` itself
     (which would internally reconstruct the peer socket via the *patched* module-level `socket`
     name and hit the guard anyway). This has no effect on real test behavior - every actual HTTP
     call in every test is still mocked via `aioresponses`, and `pytest_socket` still blocks any
     other real `socket.socket(...)` normally.

   Verify all three are working with:
   `.venv/Scripts/python -m pytest -q` — Phase 3's existing 32 tests must all still pass, with no
   `ModuleNotFoundError` or `HASocketBlockedError`.

---

## Task 1: `manifest.json` and `hacs.json`

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/manifest.json`
- Create: `hacs.json`

**Interfaces:**
- Produces: the two manifest files HACS and Home Assistant both require to discover and load the integration. No code interfaces — later tasks don't import from these files.

- [ ] **Step 1: Create `custom_components/minecraft_bedrock_realms/manifest.json`**

```json
{
  "domain": "minecraft_bedrock_realms",
  "name": "Minecraft Bedrock Realms",
  "version": "0.1.0",
  "codeowners": ["@LucaFSmart"],
  "config_flow": true,
  "documentation": "https://github.com/LucaFSmart/ha-minecraft-bedrock-realms",
  "issue_tracker": "https://github.com/LucaFSmart/ha-minecraft-bedrock-realms/issues",
  "integration_type": "hub",
  "iot_class": "cloud_polling",
  "requirements": [],
  "dependencies": []
}
```

Note: `requirements` is empty because this integration only depends on `aiohttp`, which Home Assistant Core already ships and every integration may use without declaring it.

- [ ] **Step 2: Create `hacs.json`**

```json
{
  "name": "Minecraft Bedrock Realms",
  "content_in_root": false,
  "render_readme": true,
  "homeassistant": "2026.3.0"
}
```

- [ ] **Step 3: Verify both are valid JSON**

Run: `.venv/Scripts/python -c "import json; json.load(open('custom_components/minecraft_bedrock_realms/manifest.json')); json.load(open('hacs.json')); print('valid')"`
Expected: `valid`

- [ ] **Step 4: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/manifest.json hacs.json
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add manifest.json and hacs.json for HACS/HA discovery"
```

---

## Task 2: HA-specific constants

**Files:**
- Modify: `custom_components/minecraft_bedrock_realms/const.py`

**Interfaces:**
- Consumes: nothing new.
- Produces (appended to the existing file, all existing constants unchanged): `PLATFORMS`, `CONF_CLIENT_ID`, `CONF_OAUTH_TOKEN`, `CONF_REALM_IDS`, `CONF_UPDATE_INTERVAL`, `CONF_TRACKED_GAMERTAGS`, `CONF_ENABLE_EVENTS`, `DEFAULT_UPDATE_INTERVAL`, `UPDATE_INTERVAL_OPTIONS`, `EVENT_PLAYER_JOINED`, `EVENT_PLAYER_LEFT`. Consumed by every task from here on.

No test file — pure constant data, exercised indirectly by every later task's tests, same as Phase 3's `const.py`.

- [ ] **Step 1: Append to `custom_components/minecraft_bedrock_realms/const.py`**

Add this block at the end of the existing file (do not modify anything above it):

```python

# --- Home Assistant integration constants ---
from homeassistant.const import Platform  # noqa: E402

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.BINARY_SENSOR]

CONF_CLIENT_ID = "client_id"
CONF_OAUTH_TOKEN = "oauth_token"
CONF_REALM_IDS = "realm_ids"
CONF_UPDATE_INTERVAL = "update_interval"
CONF_TRACKED_GAMERTAGS = "tracked_gamertags"
CONF_ENABLE_EVENTS = "enable_events"

DEFAULT_UPDATE_INTERVAL = 60
UPDATE_INTERVAL_OPTIONS = [15, 30, 60, 120, 300]

# Event names are spelled out in full (not DOMAIN-prefixed) to match the
# project's specified event contract exactly.
EVENT_PLAYER_JOINED = "minecraft_realm_player_joined"
EVENT_PLAYER_LEFT = "minecraft_realm_player_left"
```

- [ ] **Step 2: Verify it imports cleanly**

Run: `.venv/Scripts/python -c "from custom_components.minecraft_bedrock_realms.const import PLATFORMS, EVENT_PLAYER_JOINED; print(PLATFORMS, EVENT_PLAYER_JOINED)"`
Expected: prints the platform list and `minecraft_realm_player_joined` with no import error. This
requires `homeassistant` to be importable in the project's `.venv/` (created and populated in
Task 3) — if `.venv/` doesn't exist yet when you reach this step, skip straight to Task 3, which
creates it and installs the full test toolchain, then come back and verify.

- [ ] **Step 3: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/const.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add Home Assistant-specific constants (platforms, config keys, events)"
```

---

## Task 3: Test toolchain, coordinator/tracked-player models, and gamertag-to-XUID lookup

**Files:**
- Verify only (already modified as infrastructure setup, see Step 1): `requirements-dev.txt`
- Modify: `custom_components/minecraft_bedrock_realms/xbox_profile.py`
- Modify: `custom_components/minecraft_bedrock_realms/models.py`
- Test: `tests/test_xbox_profile.py` (extend)
- Test: `tests/test_models.py` (extend)
- Create: `tests/conftest.py`

**Interfaces:**
- Consumes: `custom_components.minecraft_bedrock_realms.exceptions.RealmsAPIError` (existing).
- Produces: `XboxProfileClient.get_xuid(gamertag: str) -> str | None` (new method, mirrors the existing `get_gamertag`), `models.RealmSnapshot` and `models.TrackedPlayerStatus` dataclasses (consumed by `coordinator.py` in Task 4 and `sensor.py`/`binary_sensor.py` in Tasks 8-9), and the `tests/conftest.py` fixtures every later HA-aware test file needs (`enable_custom_integrations`).

- [ ] **Step 1: Verify the HA test dependencies and environment are ready**

`requirements-dev.txt` already has `homeassistant==2026.8.3` and
`pytest-homeassistant-custom-component==0.13.357` added (plus the `aiohttp`/`aioresponses`
version corrections these forced — see this plan's "Windows test environment" note in Global
Constraints for the full story). This was done as one-time infrastructure setup alongside the
three `.venv/Lib/site-packages/` stub files (`fcntl.py`, `resource.py`, `sitecustomize.py`) that
Windows needs for Home Assistant's test harness to import and run at all. Read that Global
Constraints note now if you haven't already — it explains what these are and why, and confirms
they must already exist for this step to succeed.

Run: `.venv/Scripts/python -m pip install -r requirements-dev.txt` (should report everything
already satisfied — this just confirms the environment matches the file) then
`.venv/Scripts/python -m pytest -q` and confirm all 32 existing Phase 3 tests still pass, with no
`ModuleNotFoundError` or `HASocketBlockedError`. If either the install pulls something unexpected
or any test fails with one of those two errors, STOP and report BLOCKED — do not attempt to
work around it yourself (e.g. by re-pinning `aiohttp<3.14` or switching `aioresponses` back to a
plain PyPI install) since that would silently reintroduce the exact incompatibility this setup
fixes. Report exactly what you observed instead.

- [ ] **Step 2: Create `tests/conftest.py`**

```python
"""Shared pytest fixtures for Home Assistant-aware tests."""
import pytest

pytest_plugins = "pytest_homeassistant_custom_component"


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    """Enable loading custom_components/ in every test automatically."""
    yield
```

- [ ] **Step 3: Write the failing tests for the new xbox_profile.py method**

Append to `tests/test_xbox_profile.py` (keep the existing two tests unchanged):

```python


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
```

- [ ] **Step 4: Run to verify the new tests fail**

Run: `.venv/Scripts/python -m pytest tests/test_xbox_profile.py -v`
Expected: the two new tests FAIL with `AttributeError: 'XboxProfileClient' object has no attribute 'get_xuid'`; the two pre-existing tests still PASS.

- [ ] **Step 5: Implement `get_xuid` in `custom_components/minecraft_bedrock_realms/xbox_profile.py`**

Add this method to the `XboxProfileClient` class (alongside the existing `get_gamertag`; keep everything else in the file unchanged):

```python
    async def get_xuid(self, gamertag: str) -> str | None:
        url = f"https://profile.xboxlive.com/users/gt({gamertag})/profile/settings?settings=Gamertag"
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
            return str(data["profileUsers"][0]["id"])
        except (KeyError, IndexError):
            _LOGGER.debug("Profile response for gamertag %s had no id", gamertag)
            return None
```

- [ ] **Step 6: Run to verify the xbox_profile tests pass**

Run: `.venv/Scripts/python -m pytest tests/test_xbox_profile.py -v`
Expected: 4 passed

- [ ] **Step 7: Write the failing tests for the new models**

Append to `tests/test_models.py`:

```python


def test_realm_snapshot_defaults():
    from custom_components.minecraft_bedrock_realms.models import Realm, RealmSnapshot

    realm = Realm(
        id=1, name="Test", owner="X", owner_xuid="1", state="OPEN",
        max_players=10, active_slot=1, member=True,
    )
    snapshot = RealmSnapshot(realm=realm)

    assert snapshot.online_gamertags == {}
    assert snapshot.available is True
    assert snapshot.error_category is None
    assert snapshot.last_update is None


def test_tracked_player_status_fields():
    from datetime import datetime, timezone

    from custom_components.minecraft_bedrock_realms.models import TrackedPlayerStatus

    now = datetime.now(timezone.utc)
    status = TrackedPlayerStatus(
        gamertag="SteveGT", xuid="123", online=True, last_seen=now, joined_at=now,
    )

    assert status.gamertag == "SteveGT"
    assert status.online is True
```

- [ ] **Step 8: Run to verify the new model tests fail**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: the two new tests FAIL with `ImportError: cannot import name 'RealmSnapshot'`; all 7 pre-existing tests still PASS.

- [ ] **Step 9: Implement the new models**

Append to `custom_components/minecraft_bedrock_realms/models.py` (keep everything above unchanged):

```python


@dataclass(slots=True)
class RealmSnapshot:
    """One coordinator refresh's result for a single tracked Realm."""

    realm: Realm | None
    online_gamertags: dict[str, str] = field(default_factory=dict)  # xuid -> gamertag
    last_update: datetime | None = None
    available: bool = True
    error_category: str | None = None  # "auth" | "rate_limit" | "network" | "not_found" | None


@dataclass(slots=True)
class TrackedPlayerStatus:
    """Online status of one user-configured tracked gamertag."""

    gamertag: str
    xuid: str | None
    online: bool
    last_seen: datetime | None = None
    joined_at: datetime | None = None
```

- [ ] **Step 10: Run to verify the model tests pass**

Run: `.venv/Scripts/python -m pytest tests/test_models.py -v`
Expected: 9 passed

- [ ] **Step 11: Run the full suite to confirm nothing else broke**

Run: `.venv/Scripts/python -m pytest -v`
Expected: all tests pass (Phase 3's 32 plus this task's 4 new ones = 36), pristine output.

- [ ] **Step 12: Commit**

```bash
git add requirements-dev.txt tests/conftest.py \
  custom_components/minecraft_bedrock_realms/xbox_profile.py tests/test_xbox_profile.py \
  custom_components/minecraft_bedrock_realms/models.py tests/test_models.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add HA test toolchain, gamertag-to-XUID lookup, and coordinator data models"
```

---

## Task 4: `coordinator.py`

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/coordinator.py`
- Test: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `auth.MicrosoftAuth`, `realms_api.RealmsAPI`, `xbox_profile.XboxProfileClient`,
  `models.{OAuthToken,Realm,RealmActivity,RealmSnapshot,TrackedPlayerStatus}`,
  `exceptions.{RealmsClientError,RealmsAPIError}`,
  `const.{DOMAIN,EVENT_PLAYER_JOINED,EVENT_PLAYER_LEFT}` (all existing/Task-3-added).
- Produces: `RealmsDataUpdateCoordinator(hass, config_entry, auth, realms_api, profile_client,
  oauth_token, realm_ids, tracked_gamertags, enable_events, update_interval)`, a
  `DataUpdateCoordinator[dict[int, RealmSnapshot]]` subclass, with public attribute
  `tracked_player_status: dict[str, TrackedPlayerStatus]` (keyed by gamertag). Consumed by
  `__init__.py` (Task 5), `sensor.py` (Task 8), `binary_sensor.py` (Task 9).

- [ ] **Step 1: Write the failing tests**

`tests/test_coordinator.py`:
```python
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
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_coordinator.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.coordinator'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/coordinator.py`:
```python
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
                error_category=activity_error,
            )

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
        self._realms_api.update_authorization(self._oauth_token.access_token)
        self._profile_client.update_authorization(self._oauth_token.access_token)

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
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_coordinator.py -v`
Expected: 9 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 45 passed (36 from before + 9 new), pristine output.

- [ ] **Step 6: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/coordinator.py tests/test_coordinator.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add RealmsDataUpdateCoordinator with join/leave events and token refresh"
```

---

## Task 5: `__init__.py` (setup/unload)

> **Execution order note (discovered during implementation):** `manifest.json` (Task 1) declares
> `"config_flow": true`, which makes Home Assistant's `config_entries` machinery require
> `config_flow.py` to exist and be importable before it will run `async_setup_entry` for *any*
> config entry — including in this task's own tests, which drive setup via
> `hass.config_entries.async_setup(entry.entry_id)`. Since `config_flow.py` doesn't exist until
> Tasks 6-7, **this task must actually be executed after Tasks 6 and 7**, even though it's
> numbered earlier in this document (task numbering reflects logical grouping, not literal
> execution order here). `config_flow.py` has no dependency on `__init__.py` or `coordinator.py`,
> so doing Tasks 6-7 first is safe and requires no changes to their content. Do not try to make
> this task's tests pass before Tasks 6-7 land — that's the correct, expected behavior, not a bug
> to route around with a placeholder `config_flow.py`.

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/__init__.py` (this replaces the Phase 3 placeholder — read it first, its docstring is being superseded)
- Test: `tests/test_init.py`

**Interfaces:**
- Consumes: `auth.MicrosoftAuth`, `realms_api.RealmsAPI`, `xbox_profile.XboxProfileClient`,
  `coordinator.RealmsDataUpdateCoordinator`, `models.OAuthToken`,
  `const.{DOMAIN,PLATFORMS,CONF_CLIENT_ID,CONF_OAUTH_TOKEN,CONF_REALM_IDS,CONF_UPDATE_INTERVAL,
  CONF_TRACKED_GAMERTAGS,CONF_ENABLE_EVENTS,DEFAULT_UPDATE_INTERVAL,DEFAULT_CLIENT_ID}`.
- Produces: `async_setup_entry(hass, entry) -> bool`, `async_unload_entry(hass, entry) -> bool`.
  Stores the coordinator on `entry.runtime_data` (the current HA convention — no `hass.data[DOMAIN]`
  dict needed). Consumed by `sensor.py`/`binary_sensor.py` (Tasks 8-9) via
  `entry.runtime_data`.

- [ ] **Step 1: Write the failing test**

`tests/test_init.py`:
```python
"""Tests for async_setup_entry / async_unload_entry."""
from unittest.mock import AsyncMock, patch

from homeassistant.core import HomeAssistant
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.minecraft_bedrock_realms.const import (
    CONF_OAUTH_TOKEN,
    CONF_REALM_IDS,
    DOMAIN,
)
from custom_components.minecraft_bedrock_realms.models import OAuthToken


async def test_setup_entry_creates_coordinator_and_does_first_refresh(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_OAUTH_TOKEN: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600).to_dict(),
            CONF_REALM_IDS: [1],
        },
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.minecraft_bedrock_realms.coordinator.RealmsDataUpdateCoordinator"
        ".async_config_entry_first_refresh",
        new=AsyncMock(),
    ):
        result = await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    assert result is True
    assert entry.state.value == "loaded"
    assert entry.runtime_data is not None


async def test_unload_entry_succeeds(hass: HomeAssistant):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_OAUTH_TOKEN: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600).to_dict(),
            CONF_REALM_IDS: [1],
        },
        options={},
    )
    entry.add_to_hass(hass)

    with patch(
        "custom_components.minecraft_bedrock_realms.coordinator.RealmsDataUpdateCoordinator"
        ".async_config_entry_first_refresh",
        new=AsyncMock(),
    ):
        await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

        unload_result = await hass.config_entries.async_unload(entry.entry_id)
        await hass.async_block_till_done()

    assert unload_result is True
    assert entry.state.value == "not_loaded"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_init.py -v`
Expected: FAIL — `async_setup_entry`/`async_unload_entry` don't exist yet (the current `__init__.py` is just a docstring), so `hass.config_entries.async_setup` returns `False`/raises, and the assertions fail.

- [ ] **Step 3: Write the implementation**

Replace the full contents of `custom_components/minecraft_bedrock_realms/__init__.py`:
```python
"""The Minecraft Bedrock Realms integration."""
from __future__ import annotations

from dataclasses import dataclass

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import MicrosoftAuth
from .const import (
    CONF_CLIENT_ID,
    CONF_ENABLE_EVENTS,
    CONF_OAUTH_TOKEN,
    CONF_REALM_IDS,
    CONF_TRACKED_GAMERTAGS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_CLIENT_ID,
    DEFAULT_UPDATE_INTERVAL,
    PLATFORMS,
    REALMS_XSTS_RELYING_PARTY,
    XBOX_LIVE_XSTS_RELYING_PARTY,
)
from .coordinator import RealmsDataUpdateCoordinator
from .models import OAuthToken
from .realms_api import RealmsAPI
from .xbox_profile import XboxProfileClient

type MinecraftRealmsConfigEntry = ConfigEntry[RealmsDataUpdateCoordinator]


async def async_setup_entry(hass: HomeAssistant, entry: MinecraftRealmsConfigEntry) -> bool:
    """Set up Minecraft Bedrock Realms from a config entry."""
    session = async_get_clientsession(hass)
    client_id = entry.data.get(CONF_CLIENT_ID) or DEFAULT_CLIENT_ID
    auth = MicrosoftAuth(session, client_id=client_id)

    oauth_token = OAuthToken.from_dict(entry.data[CONF_OAUTH_TOKEN])
    xbl_user_token = await auth.get_xbox_user_token(oauth_token)
    realms_xsts = await auth.get_xsts_token(xbl_user_token, REALMS_XSTS_RELYING_PARTY)
    xbox_live_xsts = await auth.get_xsts_token(xbl_user_token, XBOX_LIVE_XSTS_RELYING_PARTY)

    realms_api = RealmsAPI(session, realms_xsts.authorization_header)
    profile_client = XboxProfileClient(session, xbox_live_xsts.authorization_header)

    coordinator = RealmsDataUpdateCoordinator(
        hass,
        entry,
        auth,
        realms_api,
        profile_client,
        oauth_token,
        realm_ids=set(entry.data[CONF_REALM_IDS]),
        tracked_gamertags=entry.options.get(CONF_TRACKED_GAMERTAGS, []),
        enable_events=entry.options.get(CONF_ENABLE_EVENTS, True),
        update_interval=entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
    )

    await coordinator.async_config_entry_first_refresh()

    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))

    return True


async def async_unload_entry(hass: HomeAssistant, entry: MinecraftRealmsConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)


async def _async_update_listener(hass: HomeAssistant, entry: MinecraftRealmsConfigEntry) -> None:
    """Reload the entry when its options change (poll interval, tracked players, events)."""
    await hass.config_entries.async_reload(entry.entry_id)
```

Note: `entry.runtime_data` requires Home Assistant's typed-config-entry pattern (`ConfigEntry[T]`),
current in 2026.x releases. `REALMS_XSTS_RELYING_PARTY` and `XBOX_LIVE_XSTS_RELYING_PARTY` are
existing Phase 3 constants from `const.py` — no new constant needed for them.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_init.py -v`
Expected: 2 passed

Note: setup will attempt real `auth.get_xbox_user_token`/`get_xsts_token` HTTP calls against the
mocked `OAuthToken` in the test, which will fail against the real network in CI/offline
environments — if either test fails with a network/connection error rather than the expected
assertions, that means the auth calls need mocking too. In that case, extend the `patch(...)`
block in each test to also mock `custom_components.minecraft_bedrock_realms.auth.MicrosoftAuth
.get_xbox_user_token` and `.get_xsts_token` (both `AsyncMock`, returning a fake `XboxToken`
instance) alongside the existing `async_config_entry_first_refresh` patch, then re-run.

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/__init__.py tests/test_init.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add async_setup_entry/async_unload_entry wiring auth, API clients, and coordinator"
```

---

## Task 6: `config_flow.py` part 1 — device-code login and Realm selection

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/config_flow.py`
- Test: `tests/test_config_flow.py`

**Interfaces:**
- Consumes: `auth.MicrosoftAuth`, `realms_api.RealmsAPI`, `models.{DeviceCodeInfo,OAuthToken,Realm}`,
  `exceptions.{AuthenticationError,DeviceCodeExpiredError,RealmsClientError}`,
  `const.{DOMAIN,CONF_CLIENT_ID,CONF_OAUTH_TOKEN,CONF_REALM_IDS,DEFAULT_CLIENT_ID,
  REALMS_XSTS_RELYING_PARTY}`.
- Produces: `ConfigFlow` subclass registered for `DOMAIN`, steps `async_step_user` ->
  `async_step_device_code` -> `async_step_select_realms` -> entry creation. Task 7 adds
  `async_step_reauth`/`async_step_reauth_confirm` and the options flow to this same file/class.

- [ ] **Step 1: Write the failing tests**

`tests/test_config_flow.py`:
```python
"""Tests for the config flow: device code login and Realm selection."""
from datetime import datetime, timezone
from unittest.mock import AsyncMock, patch

from homeassistant import config_entries
from homeassistant.core import HomeAssistant

from custom_components.minecraft_bedrock_realms.const import CONF_REALM_IDS, DOMAIN
from custom_components.minecraft_bedrock_realms.exceptions import AuthenticationError
from custom_components.minecraft_bedrock_realms.models import DeviceCodeInfo, OAuthToken, Realm, XboxToken


def _fake_xbox_token(gamertag: str = "Steve") -> XboxToken:
    return XboxToken(
        token="t", userhash="h", xuid="1", gamertag=gamertag,
        not_after=datetime.now(timezone.utc).replace(year=2099),
    )


async def test_full_happy_path_creates_entry(hass: HomeAssistant):
    device_code = DeviceCodeInfo(
        device_code="dc", user_code="ABCD", verification_uri="https://microsoft.com/link",
        expires_in=900, interval=0, message="go to https://microsoft.com/link",
    )
    oauth_token = OAuthToken(access_token="at", refresh_token="rt", expires_in=3600)
    realms = [Realm(id=1, name="Ron's Realm", owner="Ron", owner_xuid="1", state="OPEN", max_players=10, active_slot=1, member=True)]

    with (
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.request_device_code",
            new=AsyncMock(return_value=device_code),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.poll_for_token",
            new=AsyncMock(return_value=oauth_token),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.get_xbox_user_token",
            new=AsyncMock(return_value=_fake_xbox_token()),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.get_xsts_token",
            new=AsyncMock(return_value=_fake_xbox_token()),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.RealmsAPI.list_realms",
            new=AsyncMock(return_value=realms),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        assert result["type"] == "form"
        assert result["step_id"] == "user"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        assert result["type"] == "progress"
        assert result["step_id"] == "device_code"

        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])
        assert result["type"] == "form"
        assert result["step_id"] == "select_realms"

        result = await hass.config_entries.flow.async_configure(
            result["flow_id"], {CONF_REALM_IDS: ["1"]}
        )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_REALM_IDS] == [1]


async def test_zero_realms_shows_error(hass: HomeAssistant):
    device_code = DeviceCodeInfo(
        device_code="dc", user_code="ABCD", verification_uri="https://microsoft.com/link",
        expires_in=900, interval=0, message="go to https://microsoft.com/link",
    )
    oauth_token = OAuthToken(access_token="at", refresh_token="rt", expires_in=3600)

    with (
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.request_device_code",
            new=AsyncMock(return_value=device_code),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.poll_for_token",
            new=AsyncMock(return_value=oauth_token),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.get_xbox_user_token",
            new=AsyncMock(return_value=_fake_xbox_token()),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.get_xsts_token",
            new=AsyncMock(return_value=_fake_xbox_token()),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.RealmsAPI.list_realms",
            new=AsyncMock(return_value=[]),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "abort"
    assert result["reason"] == "no_realms_found"


async def test_device_code_login_failure_aborts_with_reason(hass: HomeAssistant):
    device_code = DeviceCodeInfo(
        device_code="dc", user_code="ABCD", verification_uri="https://microsoft.com/link",
        expires_in=900, interval=0, message="go to https://microsoft.com/link",
    )

    with (
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.request_device_code",
            new=AsyncMock(return_value=device_code),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.poll_for_token",
            new=AsyncMock(side_effect=AuthenticationError("denied")),
        ),
    ):
        result = await hass.config_entries.flow.async_init(
            DOMAIN, context={"source": config_entries.SOURCE_USER}
        )
        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "abort"
    assert result["reason"] == "auth_failed"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_config_flow.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.config_flow'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/config_flow.py`:
```python
"""Config flow for Minecraft Bedrock Realms."""
from __future__ import annotations

import asyncio
import logging
from typing import Any

import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from .auth import MicrosoftAuth
from .const import (
    CONF_CLIENT_ID,
    CONF_OAUTH_TOKEN,
    CONF_REALM_IDS,
    DEFAULT_CLIENT_ID,
    DOMAIN,
    REALMS_XSTS_RELYING_PARTY,
)
from .exceptions import AuthenticationError, DeviceCodeExpiredError, RealmsClientError
from .models import DeviceCodeInfo, OAuthToken, Realm
from .realms_api import RealmsAPI

_LOGGER = logging.getLogger(__name__)


class MinecraftBedrockRealmsConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for Minecraft Bedrock Realms."""

    VERSION = 1

    def __init__(self) -> None:
        self._client_id: str = DEFAULT_CLIENT_ID
        self._auth: MicrosoftAuth | None = None
        self._device_code_info: DeviceCodeInfo | None = None
        self._device_code_task: asyncio.Task | None = None
        self._oauth_token: OAuthToken | None = None
        self._realms: list[Realm] = []

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            self._client_id = user_input.get(CONF_CLIENT_ID) or DEFAULT_CLIENT_ID
            session = async_get_clientsession(self.hass)
            self._auth = MicrosoftAuth(session, client_id=self._client_id)
            try:
                self._device_code_info = await self._auth.request_device_code()
            except AuthenticationError:
                return self.async_abort(reason="device_code_request_failed")
            return await self.async_step_device_code()

        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema({vol.Optional(CONF_CLIENT_ID): str}),
        )

    async def async_step_device_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._auth is not None
        assert self._device_code_info is not None

        if self._device_code_task is None:
            # eager_start=False is required: HomeAssistant.async_create_task defaults to
            # eager_start=True, which runs the coroutine synchronously up to its first real
            # suspension point at creation time. A mocked poll_for_token (or, in production, a
            # call that happens to return before the caller re-checks .done()) would then already
            # be finished by the time we check it below, and this step would never actually
            # return async_show_progress - it would fall straight through to the final result
            # inside this single call, which is not how the "show progress in the UI, then
            # advance" flow is supposed to work.
            self._device_code_task = self.hass.async_create_task(
                self._auth.poll_for_token(self._device_code_info), eager_start=False
            )

        if not self._device_code_task.done():
            return self.async_show_progress(
                step_id="device_code",
                progress_action="wait_for_login",
                description_placeholders={
                    "url": self._device_code_info.verification_uri,
                    "code": self._device_code_info.user_code,
                },
                progress_task=self._device_code_task,
            )

        try:
            self._oauth_token = self._device_code_task.result()
        except (AuthenticationError, DeviceCodeExpiredError):
            return self.async_show_progress_done(next_step_id="auth_failed")

        return self.async_show_progress_done(next_step_id="discover_realms")

    async def async_step_auth_failed(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        return self.async_abort(reason="auth_failed")

    async def async_step_discover_realms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._auth is not None
        assert self._oauth_token is not None

        try:
            xbl_user_token = await self._auth.get_xbox_user_token(self._oauth_token)
            xsts_token = await self._auth.get_xsts_token(xbl_user_token, REALMS_XSTS_RELYING_PARTY)
        except RealmsClientError:
            return self.async_abort(reason="auth_failed")

        await self.async_set_unique_id(xsts_token.xuid)
        self._abort_if_unique_id_configured()

        session = async_get_clientsession(self.hass)
        realms_api = RealmsAPI(session, xsts_token.authorization_header)
        try:
            self._realms = await realms_api.list_realms()
        except RealmsClientError:
            return self.async_abort(reason="realm_discovery_failed")

        if not self._realms:
            return self.async_abort(reason="no_realms_found")

        return await self.async_step_select_realms()

    async def async_step_select_realms(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            selected_ids = [int(realm_id) for realm_id in user_input[CONF_REALM_IDS]]
            return self.async_create_entry(
                title="Minecraft Bedrock Realms",
                data={
                    CONF_CLIENT_ID: self._client_id,
                    CONF_OAUTH_TOKEN: self._oauth_token.to_dict(),
                    CONF_REALM_IDS: selected_ids,
                },
            )

        realm_options = {str(realm.id): realm.name for realm in self._realms}
        return self.async_show_form(
            step_id="select_realms",
            data_schema=vol.Schema(
                {vol.Required(CONF_REALM_IDS): vol.All(vol.Coerce(list), [vol.In(realm_options)])}
            ),
            description_placeholders={"count": str(len(self._realms))},
        )
```

Note on test/HA-version specifics (found and verified during implementation, not guessed):
- `FlowResultType.SHOW_PROGRESS`/`SHOW_PROGRESS_DONE` serialize to the strings `"progress"`/
  `"progress_done"` in this Home Assistant version, not `"show_progress"`/`"show_progress_done"`
  — the test's literal assertions must use the actual values.
- `FlowManager.async_configure`'s public method internally loops and never returns a
  `SHOW_PROGRESS_DONE` result to the caller — it auto-chases straight through to whatever the
  `next_step_id` step returns. So there is no separate "observe progress_done" call: the single
  `async_configure(flow_id)` call made after `await hass.async_block_till_done()` (which lets the
  `eager_start=False` task actually run and lets HA's own progress-task-done callback re-enter the
  step) lands directly on the flow's real next result (the `select_realms` form, the `abort`, etc).
  Do not add an intermediate call/assertion expecting to observe `"progress_done"` as a stopping
  point — it isn't one.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config_flow.py -v`
Expected: 3 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 50 passed, pristine.

- [ ] **Step 6: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/config_flow.py tests/test_config_flow.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add config flow: device-code login and Realm selection"
```

---

## Task 7: `config_flow.py` part 2 — options flow and reauthentication

**Files:**
- Modify: `custom_components/minecraft_bedrock_realms/config_flow.py`
- Test: `tests/test_config_flow.py` (extend)

**Interfaces:**
- Consumes: everything from Task 6, plus `const.{CONF_UPDATE_INTERVAL,CONF_TRACKED_GAMERTAGS,
  CONF_ENABLE_EVENTS,DEFAULT_UPDATE_INTERVAL,UPDATE_INTERVAL_OPTIONS}`.
- Produces: `MinecraftBedrockRealmsOptionsFlow` (registered via `async_get_options_flow`),
  `async_step_reauth`/`async_step_reauth_confirm`/`async_step_reauth_device_code` on the main
  flow class.

- [ ] **Step 1: Write the failing tests**

Append to `tests/test_config_flow.py`:
```python


async def test_options_flow_updates_poll_interval_and_tracked_gamertags(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.minecraft_bedrock_realms.const import (
        CONF_ENABLE_EVENTS,
        CONF_OAUTH_TOKEN,
        CONF_TRACKED_GAMERTAGS,
        CONF_UPDATE_INTERVAL,
    )
    from custom_components.minecraft_bedrock_realms.models import OAuthToken

    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_OAUTH_TOKEN: OAuthToken(access_token="at", refresh_token="rt", expires_in=3600).to_dict(),
            CONF_REALM_IDS: [1],
        },
        options={},
    )
    entry.add_to_hass(hass)

    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] == "form"

    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            CONF_UPDATE_INTERVAL: 120,
            CONF_TRACKED_GAMERTAGS: "PlayerOne, PlayerTwo",
            CONF_ENABLE_EVENTS: False,
        },
    )

    assert result["type"] == "create_entry"
    assert result["data"][CONF_UPDATE_INTERVAL] == 120
    assert result["data"][CONF_TRACKED_GAMERTAGS] == ["PlayerOne", "PlayerTwo"]
    assert result["data"][CONF_ENABLE_EVENTS] is False


async def test_reauth_flow_updates_stored_token(hass: HomeAssistant):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    from custom_components.minecraft_bedrock_realms.const import CONF_OAUTH_TOKEN
    from custom_components.minecraft_bedrock_realms.models import OAuthToken

    old_token = OAuthToken(access_token="old", refresh_token="rt", expires_in=3600)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={CONF_OAUTH_TOKEN: old_token.to_dict(), CONF_REALM_IDS: [1]},
        options={},
    )
    entry.add_to_hass(hass)

    device_code = DeviceCodeInfo(
        device_code="dc", user_code="ABCD", verification_uri="https://microsoft.com/link",
        expires_in=900, interval=0, message="go to https://microsoft.com/link",
    )
    new_token = OAuthToken(access_token="new", refresh_token="rt2", expires_in=3600)

    with (
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.request_device_code",
            new=AsyncMock(return_value=device_code),
        ),
        patch(
            "custom_components.minecraft_bedrock_realms.config_flow.MicrosoftAuth.poll_for_token",
            new=AsyncMock(return_value=new_token),
        ),
    ):
        result = await entry.start_reauth_flow(hass)
        assert result["step_id"] == "reauth_confirm"

        result = await hass.config_entries.flow.async_configure(result["flow_id"], {})
        await hass.async_block_till_done()
        result = await hass.config_entries.flow.async_configure(result["flow_id"])

    assert result["type"] == "abort"
    assert result["reason"] == "reauth_successful"
    assert entry.data[CONF_OAUTH_TOKEN]["access_token"] == "new"
```

- [ ] **Step 2: Run to verify the new tests fail**

Run: `.venv/Scripts/python -m pytest tests/test_config_flow.py -v -k "options_flow or reauth"`
Expected: FAIL — `hass.config_entries.options.async_init` errors because no options flow is
registered yet, and `entry.start_reauth_flow` errors because `async_step_reauth` doesn't exist.

- [ ] **Step 3: Extend the implementation**

Add these imports to the top of `custom_components/minecraft_bedrock_realms/config_flow.py`
(merge with the existing import block from Task 6):
```python
from homeassistant.config_entries import ConfigEntry, OptionsFlow
from homeassistant.core import callback

from .const import (
    CONF_ENABLE_EVENTS,
    CONF_TRACKED_GAMERTAGS,
    CONF_UPDATE_INTERVAL,
    DEFAULT_UPDATE_INTERVAL,
    UPDATE_INTERVAL_OPTIONS,
)
```

Add this method to `MinecraftBedrockRealmsConfigFlow` (alongside the Task 6 methods):
```python
    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> "MinecraftBedrockRealmsOptionsFlow":
        return MinecraftBedrockRealmsOptionsFlow()

    async def async_step_reauth(self, entry_data: dict[str, Any]) -> ConfigFlowResult:
        self._client_id = entry_data.get(CONF_CLIENT_ID) or DEFAULT_CLIENT_ID
        return await self.async_step_reauth_confirm()

    async def async_step_reauth_confirm(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is None:
            return self.async_show_form(step_id="reauth_confirm", data_schema=vol.Schema({}))

        session = async_get_clientsession(self.hass)
        self._auth = MicrosoftAuth(session, client_id=self._client_id)
        try:
            self._device_code_info = await self._auth.request_device_code()
        except AuthenticationError:
            return self.async_abort(reason="device_code_request_failed")
        return await self.async_step_reauth_device_code()

    async def async_step_reauth_device_code(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        assert self._auth is not None
        assert self._device_code_info is not None

        if self._device_code_task is None:
            # eager_start=False - see the identical comment in async_step_device_code above;
            # same reason applies here.
            self._device_code_task = self.hass.async_create_task(
                self._auth.poll_for_token(self._device_code_info), eager_start=False
            )

        if not self._device_code_task.done():
            return self.async_show_progress(
                step_id="reauth_device_code",
                progress_action="wait_for_login",
                description_placeholders={
                    "url": self._device_code_info.verification_uri,
                    "code": self._device_code_info.user_code,
                },
                progress_task=self._device_code_task,
            )

        try:
            new_token = self._device_code_task.result()
        except (AuthenticationError, DeviceCodeExpiredError):
            return self.async_show_progress_done(next_step_id="auth_failed")

        reauth_entry = self._get_reauth_entry()
        return self.async_update_reload_and_abort(
            reauth_entry,
            data={**reauth_entry.data, CONF_OAUTH_TOKEN: new_token.to_dict()},
            reason="reauth_successful",
        )


class MinecraftBedrockRealmsOptionsFlow(OptionsFlow):
    """Handle options: poll interval, tracked gamertags, join/leave events."""

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        if user_input is not None:
            raw_gamertags = user_input.get(CONF_TRACKED_GAMERTAGS, "")
            tracked = [gt.strip() for gt in raw_gamertags.split(",") if gt.strip()]
            return self.async_create_entry(
                data={
                    CONF_UPDATE_INTERVAL: user_input[CONF_UPDATE_INTERVAL],
                    CONF_TRACKED_GAMERTAGS: tracked,
                    CONF_ENABLE_EVENTS: user_input[CONF_ENABLE_EVENTS],
                },
            )

        current_gamertags = self.config_entry.options.get(CONF_TRACKED_GAMERTAGS, [])
        return self.async_show_form(
            step_id="init",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_UPDATE_INTERVAL,
                        default=self.config_entry.options.get(CONF_UPDATE_INTERVAL, DEFAULT_UPDATE_INTERVAL),
                    ): vol.In(UPDATE_INTERVAL_OPTIONS),
                    vol.Optional(
                        CONF_TRACKED_GAMERTAGS, default=", ".join(current_gamertags)
                    ): str,
                    vol.Required(
                        CONF_ENABLE_EVENTS,
                        default=self.config_entry.options.get(CONF_ENABLE_EVENTS, True),
                    ): bool,
                }
            ),
        )
```

Note: the test passes `CONF_TRACKED_GAMERTAGS: "PlayerOne, PlayerTwo"` (a comma-separated string,
matching a plain HA form text field) and asserts the stored result is the parsed list
`["PlayerOne", "PlayerTwo"]` — the options flow does that string-to-list parsing itself.

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_config_flow.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 52 passed, pristine.

- [ ] **Step 6: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/config_flow.py tests/test_config_flow.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add options flow and reauthentication to config flow"
```

---

## Task 8: `sensor.py`

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/sensor.py`
- Test: `tests/test_sensor.py`

**Interfaces:**
- Consumes: `coordinator.RealmsDataUpdateCoordinator`, `models.RealmSnapshot`,
  `const.DOMAIN`, `__init__.MinecraftRealmsConfigEntry`.
- Produces: `async_setup_entry(hass, entry, async_add_entities)` registering 5 sensor entities
  per configured Realm: status, players_online, max_players, world, last_update.

- [ ] **Step 1: Write the failing tests**

`tests/test_sensor.py`:
```python
"""Tests for Realm sensor entities."""
from datetime import datetime, timezone

from homeassistant.core import HomeAssistant

from custom_components.minecraft_bedrock_realms.coordinator import RealmsDataUpdateCoordinator
from custom_components.minecraft_bedrock_realms.models import Realm, RealmSnapshot
from custom_components.minecraft_bedrock_realms.sensor import (
    RealmLastUpdateSensor,
    RealmMaxPlayersSensor,
    RealmPlayersOnlineSensor,
    RealmStatusSensor,
    RealmWorldSensor,
)


class _FakeCoordinator:
    """Minimal stand-in for RealmsDataUpdateCoordinator in entity unit tests."""

    def __init__(self, data):
        self.data = data
        self.last_update_success = True

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


def _snapshot(**overrides) -> RealmSnapshot:
    realm = Realm(
        id=1, name="Ron's Realm", owner="Ron", owner_xuid="owner-xuid",
        state="OPEN", max_players=10, active_slot=2, member=True,
    )
    defaults = dict(
        realm=realm,
        online_gamertags={"p1": "PlayerOne"},
        last_update=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
        available=True,
        error_category=None,
    )
    defaults.update(overrides)
    return RealmSnapshot(**defaults)


def test_status_sensor_reports_realm_state_and_attributes():
    coordinator = _FakeCoordinator({1: _snapshot()})
    sensor = RealmStatusSensor(coordinator, realm_id=1)

    assert sensor.native_value == "open"
    assert sensor.extra_state_attributes["realm_id"] == 1
    assert sensor.extra_state_attributes["owner"] == "Ron"
    assert sensor.extra_state_attributes["owner_xuid"] == "owner-xuid"
    assert sensor.extra_state_attributes["active_slot"] == 2


def test_status_sensor_reports_closed():
    coordinator = _FakeCoordinator({1: _snapshot(realm=Realm(
        id=1, name="R", owner="X", owner_xuid="x", state="CLOSED",
        max_players=10, active_slot=1, member=True,
    ))})
    sensor = RealmStatusSensor(coordinator, realm_id=1)
    assert sensor.native_value == "closed"


def test_status_sensor_reports_unavailable_when_snapshot_unavailable():
    coordinator = _FakeCoordinator({1: _snapshot(available=False, error_category="rate_limited")})
    sensor = RealmStatusSensor(coordinator, realm_id=1)
    assert sensor.native_value == "unavailable"


def test_players_online_sensor_state_and_attribute():
    coordinator = _FakeCoordinator({1: _snapshot()})
    sensor = RealmPlayersOnlineSensor(coordinator, realm_id=1)

    assert sensor.native_value == 1
    assert sensor.extra_state_attributes["players"] == ["PlayerOne"]


def test_max_players_sensor_reads_from_realm_not_hardcoded():
    coordinator = _FakeCoordinator({1: _snapshot()})
    sensor = RealmMaxPlayersSensor(coordinator, realm_id=1)
    assert sensor.native_value == 10


def test_world_sensor_reports_active_slot():
    coordinator = _FakeCoordinator({1: _snapshot()})
    sensor = RealmWorldSensor(coordinator, realm_id=1)
    assert sensor.native_value == "Slot 2"


def test_last_update_sensor_reports_timestamp():
    coordinator = _FakeCoordinator({1: _snapshot()})
    sensor = RealmLastUpdateSensor(coordinator, realm_id=1)
    assert sensor.native_value == datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)


def test_unique_ids_are_stable_and_realm_scoped():
    coordinator = _FakeCoordinator({1: _snapshot()})
    status = RealmStatusSensor(coordinator, realm_id=1)
    players = RealmPlayersOnlineSensor(coordinator, realm_id=1)

    assert status.unique_id == "1_status"
    assert players.unique_id == "1_players_online"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_sensor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.sensor'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/sensor.py`:
```python
"""Sensor entities for Minecraft Bedrock Realms."""
from __future__ import annotations

from datetime import datetime
from typing import Any

from homeassistant.components.sensor import SensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RealmsDataUpdateCoordinator


class _RealmSensorBase(CoordinatorEntity[RealmsDataUpdateCoordinator], SensorEntity):
    """Shared base for all per-Realm sensors."""

    _attr_has_entity_name = True

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int, key: str) -> None:
        super().__init__(coordinator)
        self._realm_id = realm_id
        self._attr_unique_id = f"{realm_id}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(realm_id))},
            name=self._realm_name,
            manufacturer="Mojang / Microsoft (unofficial)",
        )

    @property
    def _realm_name(self) -> str:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot and snapshot.realm:
            return snapshot.realm.name
        return f"Realm {self._realm_id}"

    @property
    def available(self) -> bool:
        return super().available and self._realm_id in self.coordinator.data


class RealmStatusSensor(_RealmSensorBase):
    """Realm open/closed/unavailable status."""

    _attr_translation_key = "status"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator, realm_id, "status")

    @property
    def native_value(self) -> str:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot is None or not snapshot.available or snapshot.realm is None:
            return "unavailable"
        return snapshot.realm.state.lower() if snapshot.realm.state in ("OPEN", "CLOSED") else "unknown"

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot is None or snapshot.realm is None:
            return {}
        realm = snapshot.realm
        return {
            "realm_id": realm.id,
            "owner": realm.owner,
            "owner_xuid": realm.owner_xuid,
            "active_slot": realm.active_slot,
        }


class RealmPlayersOnlineSensor(_RealmSensorBase):
    """Number of players currently online, with gamertags as an attribute."""

    _attr_translation_key = "players_online"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator, realm_id, "players_online")

    @property
    def native_value(self) -> int:
        snapshot = self.coordinator.data.get(self._realm_id)
        return len(snapshot.online_gamertags) if snapshot else 0

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot is None:
            return {"players": []}
        return {"players": sorted(snapshot.online_gamertags.values())}


class RealmMaxPlayersSensor(_RealmSensorBase):
    """Maximum player slots, read from the API - never hardcoded."""

    _attr_translation_key = "max_players"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator, realm_id, "max_players")

    @property
    def native_value(self) -> int | None:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot is None or snapshot.realm is None:
            return None
        return snapshot.realm.max_players


class RealmWorldSensor(_RealmSensorBase):
    """Active world slot. Only exposes fields confirmed present in the API response."""

    _attr_translation_key = "world"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator, realm_id, "world")

    @property
    def native_value(self) -> str | None:
        snapshot = self.coordinator.data.get(self._realm_id)
        if snapshot is None or snapshot.realm is None:
            return None
        return f"Slot {snapshot.realm.active_slot}"


class RealmLastUpdateSensor(_RealmSensorBase):
    """Timestamp of the last successful poll."""

    _attr_translation_key = "last_update"
    _attr_device_class = "timestamp"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator, realm_id, "last_update")

    @property
    def native_value(self) -> datetime | None:
        snapshot = self.coordinator.data.get(self._realm_id)
        return snapshot.last_update if snapshot else None


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up sensor entities for each configured Realm."""
    coordinator: RealmsDataUpdateCoordinator = entry.runtime_data
    entities: list[_RealmSensorBase] = []
    for realm_id in coordinator.data:
        entities.extend(
            [
                RealmStatusSensor(coordinator, realm_id),
                RealmPlayersOnlineSensor(coordinator, realm_id),
                RealmMaxPlayersSensor(coordinator, realm_id),
                RealmWorldSensor(coordinator, realm_id),
                RealmLastUpdateSensor(coordinator, realm_id),
            ]
        )
    async_add_entities(entities)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_sensor.py -v`
Expected: 8 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 60 passed, pristine.

- [ ] **Step 6: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/sensor.py tests/test_sensor.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add sensor entities: status, players online, max players, world, last update"
```

---

## Task 9: `binary_sensor.py`

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/binary_sensor.py`
- Test: `tests/test_binary_sensor.py`

**Interfaces:**
- Consumes: `coordinator.RealmsDataUpdateCoordinator`, `models.{RealmSnapshot,TrackedPlayerStatus}`,
  `const.DOMAIN`.
- Produces: `async_setup_entry(...)` registering one `realm_available` binary sensor per
  configured Realm, plus one binary sensor per user-configured tracked gamertag (account-wide,
  not per-Realm, matching the spec's "explicitly tracked players" design).

- [ ] **Step 1: Write the failing tests**

`tests/test_binary_sensor.py`:
```python
"""Tests for availability and tracked-player binary sensor entities."""
from datetime import datetime, timezone

from custom_components.minecraft_bedrock_realms.binary_sensor import (
    RealmAvailableBinarySensor,
    TrackedPlayerBinarySensor,
)
from custom_components.minecraft_bedrock_realms.models import Realm, RealmSnapshot, TrackedPlayerStatus


class _FakeCoordinator:
    def __init__(self, data, tracked_player_status=None):
        self.data = data
        self.tracked_player_status = tracked_player_status or {}
        self.last_update_success = True

    def async_add_listener(self, *args, **kwargs):
        return lambda: None


def test_realm_available_is_on_when_snapshot_available():
    realm = Realm(id=1, name="R", owner="X", owner_xuid="x", state="OPEN", max_players=10, active_slot=1, member=True)
    snapshot = RealmSnapshot(realm=realm, available=True)
    coordinator = _FakeCoordinator({1: snapshot})

    sensor = RealmAvailableBinarySensor(coordinator, realm_id=1)
    assert sensor.is_on is True
    assert sensor.extra_state_attributes["last_error_category"] is None


def test_realm_available_is_off_and_reports_error_category():
    realm = Realm(id=1, name="R", owner="X", owner_xuid="x", state="OPEN", max_players=10, active_slot=1, member=True)
    snapshot = RealmSnapshot(realm=realm, available=False, error_category="rate_limited")
    coordinator = _FakeCoordinator({1: snapshot})

    sensor = RealmAvailableBinarySensor(coordinator, realm_id=1)
    assert sensor.is_on is False
    assert sensor.extra_state_attributes["last_error_category"] == "rate_limited"


def test_tracked_player_binary_sensor_reports_online_status_and_attributes():
    now = datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc)
    status = TrackedPlayerStatus(gamertag="PlayerOne", xuid="p1", online=True, last_seen=now, joined_at=now)
    coordinator = _FakeCoordinator({}, tracked_player_status={"PlayerOne": status})

    sensor = TrackedPlayerBinarySensor(coordinator, gamertag="PlayerOne")

    assert sensor.is_on is True
    assert sensor.extra_state_attributes["gamertag"] == "PlayerOne"
    assert sensor.extra_state_attributes["xuid"] == "p1"
    assert sensor.extra_state_attributes["last_seen"] == now.isoformat()
    assert sensor.extra_state_attributes["joined_at"] == now.isoformat()


def test_tracked_player_binary_sensor_off_when_offline():
    status = TrackedPlayerStatus(gamertag="PlayerOne", xuid="p1", online=False)
    coordinator = _FakeCoordinator({}, tracked_player_status={"PlayerOne": status})

    sensor = TrackedPlayerBinarySensor(coordinator, gamertag="PlayerOne")
    assert sensor.is_on is False


def test_tracked_player_binary_sensor_unique_id_is_gamertag_scoped():
    status = TrackedPlayerStatus(gamertag="PlayerOne", xuid="p1", online=False)
    coordinator = _FakeCoordinator({}, tracked_player_status={"PlayerOne": status})

    sensor = TrackedPlayerBinarySensor(coordinator, gamertag="PlayerOne")
    assert sensor.unique_id == "tracked_player_playerone"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_binary_sensor.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.binary_sensor'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/binary_sensor.py`:
```python
"""Binary sensor entities for Minecraft Bedrock Realms."""
from __future__ import annotations

from typing import Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import DeviceInfo
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RealmsDataUpdateCoordinator


class RealmAvailableBinarySensor(CoordinatorEntity[RealmsDataUpdateCoordinator], BinarySensorEntity):
    """Whether the Realm's data was successfully polled."""

    _attr_has_entity_name = True
    _attr_translation_key = "available"

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, realm_id: int) -> None:
        super().__init__(coordinator)
        self._realm_id = realm_id
        self._attr_unique_id = f"{realm_id}_available"
        snapshot = coordinator.data.get(realm_id)
        realm_name = snapshot.realm.name if snapshot and snapshot.realm else f"Realm {realm_id}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, str(realm_id))}, name=realm_name,
            manufacturer="Mojang / Microsoft (unofficial)",
        )

    @property
    def is_on(self) -> bool:
        snapshot = self.coordinator.data.get(self._realm_id)
        return bool(snapshot and snapshot.available)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        snapshot = self.coordinator.data.get(self._realm_id)
        return {"last_error_category": snapshot.error_category if snapshot else "not_found"}


class TrackedPlayerBinarySensor(CoordinatorEntity[RealmsDataUpdateCoordinator], BinarySensorEntity):
    """Online status of one explicitly user-configured gamertag.

    Account-wide (not scoped to a single Realm device) since a tracked player
    could in principle be found via any of the account's monitored Realms.
    """

    _attr_has_entity_name = True

    def __init__(self, coordinator: RealmsDataUpdateCoordinator, gamertag: str) -> None:
        super().__init__(coordinator)
        self._gamertag = gamertag
        self._attr_unique_id = f"tracked_player_{gamertag.lower()}"
        self._attr_name = gamertag

    @property
    def is_on(self) -> bool:
        status = self.coordinator.tracked_player_status.get(self._gamertag)
        return bool(status and status.online)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        status = self.coordinator.tracked_player_status.get(self._gamertag)
        if status is None:
            return {"gamertag": self._gamertag}
        return {
            "gamertag": status.gamertag,
            "xuid": status.xuid,
            "last_seen": status.last_seen.isoformat() if status.last_seen else None,
            "joined_at": status.joined_at.isoformat() if status.joined_at else None,
        }


async def async_setup_entry(hass: HomeAssistant, entry, async_add_entities: AddEntitiesCallback) -> None:
    """Set up availability and tracked-player binary sensors."""
    coordinator: RealmsDataUpdateCoordinator = entry.runtime_data
    entities: list[BinarySensorEntity] = [
        RealmAvailableBinarySensor(coordinator, realm_id) for realm_id in coordinator.data
    ]
    entities.extend(
        TrackedPlayerBinarySensor(coordinator, gamertag)
        for gamertag in coordinator.tracked_player_status
    )
    async_add_entities(entities)
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_binary_sensor.py -v`
Expected: 5 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 65 passed, pristine.

- [ ] **Step 6: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/binary_sensor.py tests/test_binary_sensor.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add binary sensors: Realm availability and tracked-player online status"
```

---

## Task 10: `strings.json` and translations

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/strings.json`
- Create: `custom_components/minecraft_bedrock_realms/translations/en.json`
- Create: `custom_components/minecraft_bedrock_realms/translations/de.json`

**Interfaces:**
- Consumes: nothing (referenced by `step_id`/`translation_key`/abort `reason` strings already
  used in `config_flow.py` and `sensor.py`/`binary_sensor.py` from Tasks 6-9).
- Produces: the UI text HA's frontend renders for every config/options flow step, abort reason,
  and entity `translation_key` defined in this plan.

- [ ] **Step 1: Create `custom_components/minecraft_bedrock_realms/strings.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Connect your Microsoft account",
        "description": "Optionally provide your own Azure AD public-client app ID. If left blank, a default (currently unverified for this OAuth flow - see the project README) is used.",
        "data": {
          "client_id": "Azure AD Client ID (optional)"
        }
      },
      "device_code": {
        "title": "Sign in with Microsoft",
        "description": "Go to {url} and enter the code: {code}\n\nWaiting for you to complete sign-in..."
      },
      "reauth_confirm": {
        "title": "Re-authenticate Minecraft Bedrock Realms",
        "description": "Your Microsoft sign-in has expired or was revoked. Click Submit to sign in again."
      },
      "reauth_device_code": {
        "title": "Sign in with Microsoft",
        "description": "Go to {url} and enter the code: {code}\n\nWaiting for you to complete sign-in..."
      },
      "select_realms": {
        "title": "Select Realms to monitor",
        "description": "Found {count} Realm(s) on this account. Choose which to add to Home Assistant.",
        "data": {
          "realm_ids": "Realms"
        }
      }
    },
    "abort": {
      "device_code_request_failed": "Could not request a Microsoft device code. Check your internet connection and try again.",
      "auth_failed": "Microsoft sign-in failed or was cancelled.",
      "realm_discovery_failed": "Could not retrieve your Realms from the Minecraft Realms API. Try again later.",
      "no_realms_found": "This Microsoft account does not own or belong to any Bedrock Realm.",
      "already_configured": "This Microsoft account is already configured.",
      "reauth_successful": "Re-authentication was successful."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Minecraft Bedrock Realms options",
        "data": {
          "update_interval": "Polling interval (seconds)",
          "tracked_gamertags": "Tracked gamertags (comma-separated)",
          "enable_events": "Fire join/leave events"
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "status": { "name": "Status" },
      "players_online": { "name": "Players online" },
      "max_players": { "name": "Max players" },
      "world": { "name": "World" },
      "last_update": { "name": "Last update" }
    },
    "binary_sensor": {
      "available": { "name": "Available" }
    }
  }
}
```

- [ ] **Step 2: Create `custom_components/minecraft_bedrock_realms/translations/en.json`**

Copy the exact same content as `strings.json` (this is the standard Home Assistant convention —
`strings.json` is both the source-of-truth schema and the English translation).

- [ ] **Step 3: Create `custom_components/minecraft_bedrock_realms/translations/de.json`**

```json
{
  "config": {
    "step": {
      "user": {
        "title": "Microsoft-Konto verbinden",
        "description": "Optional kannst du eine eigene Azure-AD-Client-ID angeben. Wenn leer gelassen, wird ein Standardwert verwendet (aktuell unverifiziert für diesen OAuth-Ablauf - siehe README des Projekts).",
        "data": {
          "client_id": "Azure-AD-Client-ID (optional)"
        }
      },
      "device_code": {
        "title": "Bei Microsoft anmelden",
        "description": "Gehe zu {url} und gib den Code ein: {code}\n\nWarte auf deine Anmeldung..."
      },
      "reauth_confirm": {
        "title": "Minecraft Bedrock Realms erneut authentifizieren",
        "description": "Deine Microsoft-Anmeldung ist abgelaufen oder wurde widerrufen. Klicke auf Absenden, um dich erneut anzumelden."
      },
      "reauth_device_code": {
        "title": "Bei Microsoft anmelden",
        "description": "Gehe zu {url} und gib den Code ein: {code}\n\nWarte auf deine Anmeldung..."
      },
      "select_realms": {
        "title": "Realms zur Überwachung auswählen",
        "description": "{count} Realm(s) auf diesem Konto gefunden. Wähle aus, welche zu Home Assistant hinzugefügt werden sollen.",
        "data": {
          "realm_ids": "Realms"
        }
      }
    },
    "abort": {
      "device_code_request_failed": "Der Microsoft-Geraetecode konnte nicht angefordert werden. Prüfe deine Internetverbindung und versuche es erneut.",
      "auth_failed": "Die Microsoft-Anmeldung ist fehlgeschlagen oder wurde abgebrochen.",
      "realm_discovery_failed": "Die Realms konnten nicht von der Minecraft-Realms-API abgerufen werden. Versuche es später erneut.",
      "no_realms_found": "Dieses Microsoft-Konto besitzt keine oder ist Mitglied keiner Bedrock-Realm.",
      "already_configured": "Dieses Microsoft-Konto ist bereits konfiguriert.",
      "reauth_successful": "Die erneute Authentifizierung war erfolgreich."
    }
  },
  "options": {
    "step": {
      "init": {
        "title": "Minecraft-Bedrock-Realms-Optionen",
        "data": {
          "update_interval": "Abfrageintervall (Sekunden)",
          "tracked_gamertags": "Überwachte Gamertags (kommagetrennt)",
          "enable_events": "Beitritt/Verlassen-Ereignisse auslösen"
        }
      }
    }
  },
  "entity": {
    "sensor": {
      "status": { "name": "Status" },
      "players_online": { "name": "Spieler online" },
      "max_players": { "name": "Maximale Spieleranzahl" },
      "world": { "name": "Welt" },
      "last_update": { "name": "Letzte Aktualisierung" }
    },
    "binary_sensor": {
      "available": { "name": "Verfügbar" }
    }
  }
}
```

- [ ] **Step 4: Verify all three files are valid JSON**

Run:
```bash
python -c "
import json
for f in ['custom_components/minecraft_bedrock_realms/strings.json',
          'custom_components/minecraft_bedrock_realms/translations/en.json',
          'custom_components/minecraft_bedrock_realms/translations/de.json']:
    json.load(open(f, encoding='utf-8'))
print('all valid')
"
```
Expected: `all valid`

- [ ] **Step 5: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/strings.json \
  custom_components/minecraft_bedrock_realms/translations/en.json \
  custom_components/minecraft_bedrock_realms/translations/de.json
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add strings.json and en/de translations"
```

---

## Task 11: `diagnostics.py`

**Files:**
- Create: `custom_components/minecraft_bedrock_realms/diagnostics.py`
- Test: `tests/test_diagnostics.py`

**Interfaces:**
- Consumes: `coordinator.RealmsDataUpdateCoordinator`, `const.{CONF_OAUTH_TOKEN,CONF_CLIENT_ID}`.
- Produces: `async_get_config_entry_diagnostics(hass, entry) -> dict`. Final task of this plan.

- [ ] **Step 1: Write the failing test**

`tests/test_diagnostics.py`:
```python
"""Tests for diagnostics redaction."""
from datetime import datetime, timezone

from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.minecraft_bedrock_realms.const import (
    CONF_CLIENT_ID,
    CONF_OAUTH_TOKEN,
    CONF_REALM_IDS,
    CONF_UPDATE_INTERVAL,
    DOMAIN,
)
from custom_components.minecraft_bedrock_realms.diagnostics import async_get_config_entry_diagnostics
from custom_components.minecraft_bedrock_realms.models import OAuthToken, Realm, RealmSnapshot


class _FakeCoordinator:
    def __init__(self, data):
        self.data = data
        self.update_interval_seconds = 60
        self.last_update_success = True


async def test_diagnostics_redacts_tokens_and_client_id(hass):
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={
            CONF_OAUTH_TOKEN: OAuthToken(access_token="SECRET-AT", refresh_token="SECRET-RT", expires_in=3600).to_dict(),
            CONF_CLIENT_ID: "my-azure-app-id",
            CONF_REALM_IDS: [1],
        },
        options={CONF_UPDATE_INTERVAL: 60},
    )
    entry.add_to_hass(hass)

    realm = Realm(id=1, name="Ron's Realm", owner="Ron", owner_xuid="owner-xuid", state="OPEN", max_players=10, active_slot=1, member=True)
    snapshot = RealmSnapshot(
        realm=realm, available=True,
        last_update=datetime(2026, 8, 24, 12, 0, tzinfo=timezone.utc),
    )
    entry.runtime_data = _FakeCoordinator({1: snapshot})

    diagnostics = await async_get_config_entry_diagnostics(hass, entry)

    serialized = str(diagnostics)
    assert "SECRET-AT" not in serialized
    assert "SECRET-RT" not in serialized
    assert "my-azure-app-id" not in serialized
    assert diagnostics["polling_interval_seconds"] == 60
    assert diagnostics["realms"][0]["realm_id"] == 1
    assert diagnostics["realms"][0]["realm_name"] == "Ron's Realm"
    assert diagnostics["realms"][0]["last_update"] == "2026-08-24T12:00:00+00:00"
```

- [ ] **Step 2: Run to verify it fails**

Run: `.venv/Scripts/python -m pytest tests/test_diagnostics.py -v`
Expected: FAIL with `ModuleNotFoundError: No module named 'custom_components.minecraft_bedrock_realms.diagnostics'`

- [ ] **Step 3: Write the implementation**

`custom_components/minecraft_bedrock_realms/diagnostics.py`:
```python
"""Diagnostics for Minecraft Bedrock Realms.

Redacts every secret this integration ever holds: OAuth access/refresh
tokens, the Azure AD client ID (treated as sensitive since it identifies
the specific registered app), and Realm invite codes (this integration
never fetches invite codes, but the redaction list documents the intent
explicitly per the project's security requirements).
"""
from __future__ import annotations

from typing import Any

from homeassistant.core import HomeAssistant

from .const import CONF_CLIENT_ID, CONF_OAUTH_TOKEN
from .coordinator import RealmsDataUpdateCoordinator

REDACTED = "**REDACTED**"


async def async_get_config_entry_diagnostics(hass: HomeAssistant, entry) -> dict[str, Any]:
    """Return a redacted diagnostics dict for one config entry."""
    coordinator: RealmsDataUpdateCoordinator = entry.runtime_data

    redacted_data = dict(entry.data)
    if CONF_OAUTH_TOKEN in redacted_data:
        redacted_data[CONF_OAUTH_TOKEN] = REDACTED
    if CONF_CLIENT_ID in redacted_data:
        redacted_data[CONF_CLIENT_ID] = REDACTED

    realms_diag = []
    for realm_id, snapshot in coordinator.data.items():
        realms_diag.append(
            {
                "realm_id": realm_id,
                "realm_name": snapshot.realm.name if snapshot.realm else None,
                "state": snapshot.realm.state if snapshot.realm else None,
                "available": snapshot.available,
                "error_category": snapshot.error_category,
                "last_update": snapshot.last_update.isoformat() if snapshot.last_update else None,
                "player_count": len(snapshot.online_gamertags),
            }
        )

    return {
        "entry_data": redacted_data,
        "entry_options": dict(entry.options),
        "polling_interval_seconds": entry.options.get("update_interval", 60),
        "coordinator_last_update_success": coordinator.last_update_success,
        "realms": realms_diag,
    }
```

- [ ] **Step 4: Run to verify it passes**

Run: `.venv/Scripts/python -m pytest tests/test_diagnostics.py -v`
Expected: 1 passed

- [ ] **Step 5: Run the full suite**

Run: `.venv/Scripts/python -m pytest -v`
Expected: 66 passed, pristine output.

- [ ] **Step 6: Run lint and type-check**

Run:
```bash
.venv/Scripts/python -m ruff check .
.venv/Scripts/python -m mypy custom_components poc
```
Fix anything ruff flags. mypy may report warnings in the new HA-integration files where Home
Assistant's own typing is loose (e.g. `ConfigEntry` generics) — note these in your report rather
than fighting them, since matching HA core's own typing conventions matters more than a
zero-warning mypy run for files that directly subclass HA base classes.

- [ ] **Step 7: Commit**

```bash
git add custom_components/minecraft_bedrock_realms/diagnostics.py tests/test_diagnostics.py
git -c user.name="LucaFSmart" -c user.email="197988000+LucaFSmart@users.noreply.github.com" \
  commit -m "Add diagnostics with token/client-ID redaction"
```

---

## Self-Review Notes

- **Spec coverage:** device-code config flow (Task 6), Realm selection (Task 6), options
  (poll interval/tracked gamertags/events toggle, Task 7), reauth (Task 7), all 5 sensors +
  2 binary sensor types from `docs/architecture.md`'s entity table (Tasks 8-9), join/leave events
  with baseline-on-first-poll and no-events-on-failed-poll (Task 4), token persistence via
  `ConfigEntry.data` (Tasks 4-5), diagnostics redaction (Task 11), en/de translations (Task 10).
  Realm administration (open/close/reset/delete) is deliberately absent per the Global Constraints
  — not a gap.
- **Placeholder scan:** none — every task has complete code. `sensor.py`'s `native_value`
  fallbacks (`None`/`"unavailable"`) are intentional defensive defaults, not placeholders.
- **Type consistency:** `RealmSnapshot`/`TrackedPlayerStatus` (Task 3) field names match their use
  in `coordinator.py` (Task 4), `sensor.py` (Task 8), `binary_sensor.py` (Task 9), and
  `diagnostics.py` (Task 11) identically. `RealmsDataUpdateCoordinator`'s constructor signature
  (Task 4) matches exactly how `__init__.py` (Task 5) and every test instantiate it.
- **Known follow-up, not blocking this plan:** `const.DEFAULT_CLIENT_ID`'s pairing with the AAD v2
  endpoints is still unverified pending the Phase 3 Task 10 live result (see `docs/research.md`
  §1). `config_flow.py`'s `async_step_user` already exposes a `client_id` override field so this
  doesn't block using the integration — once Task 10 confirms a working ID, updating
  `DEFAULT_CLIENT_ID` is a one-line follow-up, not a rework of anything in this plan.
