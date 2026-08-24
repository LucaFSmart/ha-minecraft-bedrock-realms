# Architecture: Minecraft Bedrock Realms integration for Home Assistant

Status: **approved design** (see [research.md](research.md) for the evidence this is based on).

## 1. Decision

**Native Python Home Assistant custom integration.** No external bridge process, no Docker, no
MQTT. Installed and updated purely through HACS, like any other custom integration.

### Why not the Node.js bridge alternative

The brief asked us to evaluate a `prismarine-realms` + `prismarine-auth` + local bridge +
MQTT/REST architecture as an alternative. Rejected because:

- **The Node ecosystem doesn't even cover the endpoint we need most.** `prismarine-realms` has no
  Bedrock live-player-activity method at all (§3 of research.md) — Java Edition only. We'd have
  to patch upstream or fork it, which defeats the point of "using the mature library."
- **Python-native auth is proven, not fragile.** `elytra-ms` demonstrates the full MSA→XBL→XSTS→
  Realms chain in pure async Python, running in production. The premise for needing a bridge
  ("Xbox auth is too fragile to reimplement in Python") does not hold up.
- **User preference.** A bridge means an always-on second process, a Docker host requirement (not
  available on this machine), token state split across two systems, and a second thing to update
  and keep alive. The user explicitly wants "just an integration I can add via HACS." A
  self-contained integration is also simpler to audit for security (no local unauthenticated HTTP
  API surface to expose).

The trade-off we accept: our own small auth/API client instead of reusing a battle-tested
library. This is mitigated by keeping that client intentionally minimal (a few hundred lines,
five HTTP calls, no undocumented cleverness) and by structuring it so the request/response shapes
mirror `elytra-ms`'s models 1:1, making it easy to cross-check against the reference
implementation during development and easy for future contributors to verify against upstream if
Microsoft changes something.

## 2. Component diagram

```
┌─────────────────────────────────────────────────────────────────────┐
│ Home Assistant Core                                                  │
│                                                                        │
│  ┌──────────────┐   ┌────────────────┐   ┌────────────────────────┐ │
│  │ config_flow   │──▶│ ConfigEntry     │──▶│ __init__.async_setup_ │ │
│  │ (device code, │   │ .data (tokens)  │   │ entry                  │ │
│  │  realm picker,│   │ .options (poll  │   │  - creates auth client │ │
│  │  options)     │   │  interval, etc) │   │  - creates coordinator │ │
│  └──────────────┘   └────────────────┘   └───────────┬────────────┘ │
│                                                          │             │
│                                             ┌────────────▼──────────┐ │
│                                             │ RealmsDataUpdateCoord- │ │
│                                             │ inator (per entry)     │ │
│                                             │  - polls every N sec   │ │
│                                             │  - diffs player sets   │ │
│                                             │  - fires HA events     │ │
│                                             └────────────┬──────────┘ │
│                                                          │             │
│              ┌───────────────────────────────────────────┤             │
│              ▼                       ▼                   ▼             │
│      ┌──────────────┐      ┌──────────────┐    ┌──────────────────┐  │
│      │ sensor.py     │      │ binary_       │    │ diagnostics.py    │  │
│      │ (status,      │      │ sensor.py     │    │ (redacted export) │  │
│      │  players,     │      │ (available,   │    └──────────────────┘  │
│      │  world, ...)  │      │  tracked      │                          │
│      └──────────────┘      │  players)     │                          │
│                              └──────────────┘                          │
└──────────────────────┬──────────────────────────────────────────────┘
                        │ aiohttp (HA's shared ClientSession)
                        ▼
        ┌───────────────────────────────────────┐
        │ auth.py (MSA device code / XBL / XSTS)  │
        │ realms_api.py (Realms REST client)      │
        └───────────────────┬─────────────────────┘
                             ▼
      login.microsoftonline.com, xboxlive.com domains,
      pocket.realms.minecraft.net   (all external, Microsoft-owned)
```

Everything runs inside the HA event loop as a normal custom integration. No new network-exposed
surface is introduced — the integration only makes outbound HTTPS calls.

## 3. Authentication flow

```
User                HA config_flow          auth.py                Microsoft
 │                        │                     │                       │
 │  Add integration       │                     │                       │
 │───────────────────────▶│                     │                       │
 │                        │  start_device_code()│                       │
 │                        │────────────────────▶│  POST devicecode      │
 │                        │                     │──────────────────────▶│
 │                        │◀────────────────────│  device_code,         │
 │  "Go to microsoft.com/ │                     │  user_code, interval  │
 │   link, enter ABCD1234"│                     │                       │
 │◀───────────────────────│                     │                       │
 │  (user logs in on any  │                     │                       │
 │   device's browser)    │                     │                       │
 │                        │  poll_for_token()   │  POST token (loop)    │
 │                        │────────────────────▶│──────────────────────▶│
 │                        │                     │◀──────────────────────│
 │                        │◀────────────────────│  access+refresh token │
 │                        │  xbl = get_xbl()    │  POST user/authenticate│
 │                        │────────────────────▶│──────────────────────▶│
 │                        │  xsts = get_xsts()  │  POST xsts/authorize  │
 │                        │────────────────────▶│──────────────────────▶│
 │                        │  realms = list()    │  GET /worlds          │
 │                        │────────────────────▶│──────────────────────▶│
 │  "Select your Realm(s)"│                     │                       │
 │◀───────────────────────│                     │                       │
 │  picks Realm(s)        │                     │                       │
 │───────────────────────▶│  create ConfigEntry │                       │
 │                        │  (tokens in .data)  │                       │
```

Tokens (`access_token`, `refresh_token`, and the derived XBL/XSTS tokens' expiry) are stored in
`ConfigEntry.data`, which HA persists to `.storage/core.config_entries` (JSON on disk, included in
HA backups, not world-readable by other integrations). This satisfies "survive HA restarts"
without a custom cache file. Refresh happens transparently inside the coordinator's update method
before every poll if the cached token is within its expiry margin; a 401 anywhere in the chain
triggers one forced full-chain refresh, and if that also fails the coordinator raises
`ConfigEntryAuthFailed`, which HA turns into a "Reauthenticate" repair — re-running the
device-code step without deleting the Realm selection or options.

## 4. Data flow (steady state)

Every poll cycle (default 60s, configurable 15–300s):

1. Coordinator calls `GET /worlds` once (covers all Realms on the account in one call) →
   Realm metadata: state (open/closed), name, owner, `maxPlayers`, `activeSlot`.
2. Coordinator calls `GET /activities/live/players` once (also covers every Realm in one call,
   confirmed in research.md §3) → per-Realm XUID + online flag.
3. For newly-seen XUIDs only (not cached from a previous poll), resolve gamertag via the Xbox
   Profile API, with an in-memory TTL cache (avoids a lookup storm and avoids a second class of
   rate limit — mirrors RealmsPlayerlistBot's approach of caching gamertag resolution
   separately from the presence poll).
4. Diff the new online-XUID set per Realm against the coordinator's in-memory previous-online set:
   - **First successful poll after (re)start**: populate the baseline set, fire *no* join/leave
     events. This is the "avoid false joins after restart" requirement — implemented as a simple
     `if self._baseline_established:` guard per config entry, not a heuristic.
   - **Subsequent polls**: XUIDs present now but not before → `minecraft_realm_player_joined`;
     present before but not now → `minecraft_realm_player_left`. A failed poll (exception,
     timeout, `UpdateFailed`) never updates the previous-online set — it is left untouched so the
     next successful poll diffs against the last known-good state, not a blank one. This avoids
     spurious leave/join pairs around a transient API outage.
5. Coordinator data is a single typed dataclass tree; entities read from it, no entity ever calls
   the API directly (standard HA coordinator entity pattern).

## 5. Home Assistant entity model

One HA **device** per configured Realm (`identifiers={(DOMAIN, realm_id)}`).

| Entity | Domain | State | Key attributes |
|---|---|---|---|
| Realm status | `sensor` | `open` / `closed` / `unavailable` / `unknown` | realm_id, owner, owner_xuid, active_slot, minecraft_version |
| Players online | `sensor` | integer count | — |
| Max players | `sensor` | integer (from `maxPlayers`, never hardcoded) | — |
| Online players | `sensor` | integer count (same as players-online value, kept separate per spec so attributes stay focused) | `players: [gamertag, ...]` list |
| World | `sensor` | active slot name/number | game_mode, difficulty, minecraft_version (whatever the API actually returns — see research.md §5 open item) |
| Last update | `sensor` | ISO timestamp of last *successful* poll | — |
| Realm available | `binary_sensor` | on/off | last_error_category (auth/rate_limit/network/unknown) |
| Tracked player `<gamertag>` (opt-in only, one per user-configured gamertag) | `binary_sensor` | on/off | gamertag, xuid, last_seen, joined_at |

No entity is created per arbitrary online player — matches the spec's explicit requirement to
keep the entity registry stable. `unique_id` for every entity is `{realm_id}_{key}`, stable
across restarts and reauth.

## 6. Error handling & resilience

| Condition | Coordinator behavior | User-visible effect |
|---|---|---|
| Realms API 5xx / network timeout | Exponential backoff (mirrors both reference implementations: base delay × 2^attempt + jitter, capped), retry within the same update; if still failing, raise `UpdateFailed` | Entities go `unavailable`, `binary_sensor.realm_available` → off, no state destroyed |
| Realms API 429 | Honor `Retry-After` if present, else same backoff as 5xx; never spins tighter than the configured interval | Same as above, plus a `last_api_error_category="rate_limited"` diagnostic field |
| 401 on any auth step | One forced full-chain token refresh; if that also 401s, raise `ConfigEntryAuthFailed` | HA surfaces a "Reauthenticate" repair flow; existing Realm selection/options untouched |
| Realm exists but is `CLOSED` | Normal successful poll; `sensor.realm_status = "closed"`, players sensor = 0 | Not an error — a closed Realm is valid state, not "unavailable" |
| Realm removed / account loses access | `/worlds` and `/worlds/{id}` stop returning it | Sensor → `unknown` after N consecutive misses (avoid flapping on one transient miss), device stays in registry (user can remove manually) |
| HA restart mid-session | Coordinator re-created fresh; tokens reloaded from `ConfigEntry.data`; first poll = baseline (§4 step 4) | No false join/leave events on restart |

Config entry setup itself never fails hard on a *transient* API error — `async_setup_entry`
schedules the first refresh through the coordinator's normal retry path rather than raising, so a
momentary Microsoft outage at HA startup doesn't remove/disable the integration.

## 7. Security model

- **No password ever collected.** Device-code flow only.
- Tokens live only in `ConfigEntry.data`/`.options`, never in entity state or attributes, never
  logged (even at debug level — log statements reference token *presence*/expiry, never values),
  never in diagnostics output (see redaction list below), never in exceptions' string
  representations (custom exception classes carry structured fields, not raw response bodies that
  might embed a token).
- `diagnostics.py` redacts: access token, refresh token, XBL/XSTS tokens, the Microsoft account
  email/username used for cache-key purposes, invite codes (Realm invite codes grant join access
  — treated as a secret), and any `Authorization` header value if ever captured in debug context.
- No inbound network surface. The integration makes outbound HTTPS calls only; there's no local
  API for anything else to attack (this is the main practical security win of not building a
  bridge).
- Destructive Realm administration (reset, delete, ban, open/close) is **not implemented at all**
  in v1 — not even behind a disabled-by-default service — per the project's explicit scope
  limits. If added later, it must be opt-in services with strong warnings, not exposed as a
  climate/switch-style always-on control.

## 8. Config flow

1. **Auth** — show device code + URL, poll in the background (HA's `async_step_*` pattern for
   long-running steps: show a progress step, poll via `async_step_device_code` re-entry), handle
   expiry/denial with a clear retryable error.
2. **Discover & select Realms** — `GET /worlds`, present a multi-select of Realm names; if the
   account owns/joined zero Realms, show an actionable error instead of an empty picker.
3. **Options** (can also be revisited later via the entry's Options flow) — polling interval
   (15/30/60/120/300s, default 60s), tracked gamertags (free-text list, validated against the
   Realm's known player set where possible), enable/disable join/leave events.
4. **Reauth** — triggered automatically by `ConfigEntryAuthFailed`; re-runs step 1 only, preserves
   the existing Realm selection and options.

All configuration is UI-driven; no YAML.

## 9. Repository layout

```
custom_components/minecraft_bedrock_realms/
  __init__.py          # async_setup_entry / async_unload_entry / async_migrate_entry
  manifest.json
  config_flow.py
  coordinator.py
  auth.py               # MSA device code + XBL + XSTS chain
  realms_api.py          # Realms REST client (worlds, activities, profile lookup)
  models.py               # typed dataclasses for API responses + coordinator data
  sensor.py
  binary_sensor.py
  diagnostics.py
  const.py
  strings.json
  translations/
    en.json
    de.json
tests/
  conftest.py
  test_auth.py
  test_realms_api.py
  test_config_flow.py
  test_coordinator.py
  test_sensor.py
  test_binary_sensor.py
  test_diagnostics.py
poc/
  realm_cli.py           # Phase 3 standalone proof-of-concept script
docs/
  research.md
  architecture.md
.github/workflows/
  ci.yml                 # lint, type-check, pytest, hassfest, HACS validation
README.md
LICENSE
hacs.json
.gitignore
```

## 10. Testing strategy

Mock every external HTTP call (no real Microsoft credentials in CI): `aioresponses` or
`respx`-style fixtures for the device-code/XBL/XSTS/Realms endpoints, using response shapes taken
directly from the schemas confirmed in research.md (and cross-checked against `elytra-ms`'s
`msgspec` model field names) so tests fail loudly if our parsing drifts from the real shape.
Coverage required per the project brief: Realm discovery, config flow (happy path + zero-realms +
denial/expiry), auth failure → reauth, token refresh, API unavailable (backoff → recovery),
Realm closed, player-list parsing, join detection, leave detection, startup-baseline
(no-events-on-first-poll), coordinator recovery after a failed cycle, diagnostics redaction.

## 11. Known limitations (carried into README)

- Relies on undocumented/reverse-engineered Microsoft endpoints (no official Realms API
  contract) — Microsoft can change these without notice.
- Live player detection has no gamertag in its native response; gamertag resolution is a second,
  separately-rate-limited call.
- No official rate-limit numbers exist; the chosen interval and backoff are evidence-based, not
  guaranteed safe forever.
- Client ID / title-authentication strategy has one open item pending Phase 3 validation
  (research.md §1).
- `/worlds[].players[].online` reliability is unconfirmed; we deliberately don't depend on it.
