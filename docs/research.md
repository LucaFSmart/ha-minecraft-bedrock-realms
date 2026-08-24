# Research: Minecraft Bedrock Realms API & Authentication

Status: **Phase 1 complete**. This document separates **CONFIRMED** facts (verified by reading
actual source code of maintained projects, cross-checked between two independent
implementations) from **INFERRED** facts (plausible but not directly verified) and **UNCERTAIN**
items that must be validated against a real account in Phase 3 (PoC).

## Sources inspected

| Project | Language | License | Commit inspected | Role in this research |
|---|---|---|---|---|
| [PrismarineJS/prismarine-realms](https://github.com/PrismarineJS/prismarine-realms) | JS | MIT | `39787cc` (v1.6.0, 2026-04-14) | Realms API surface, endpoint paths |
| [PrismarineJS/prismarine-auth](https://github.com/PrismarineJS/prismarine-auth) | JS | MIT | `b795199` (v3.1.1, 2026-03-31) | MSA/XBL/XSTS auth chain, device code flow |
| [AstreaTSS/RealmsPlayerlistBot](https://github.com/AstreaTSS/RealmsPlayerlistBot) | Python | AGPL-3.0 | `4529ee0` (2026-07-02) | How a production bot detects online players; polling architecture; join/leave/baseline handling |
| [Astrea-Stellarium-Labs/elytra-ms](https://github.com/Astrea-Stellarium-Labs/elytra-ms) | Python | MIT | `ec666db` (2024-10-02), PyPI `elytra-ms==0.7.3` used by the bot | **Proves a pure-Python implementation of the full MSA→XBL→XSTS→Realms chain exists and is production-tested.** This is the library RealmsPlayerlistBot actually depends on. |

No code is copied from RealmsPlayerlistBot (AGPL-3.0, and it's a Discord bot, not reusable as a
library). Its *mechanism* is documented here — mechanisms/facts are not copyrightable, only its
specific expression, which we do not use. `elytra-ms` and both Prismarine packages are MIT and
compatible with reuse as reference/inspiration; we still choose not to add `elytra-ms` as a
runtime dependency (see [Architecture decision](#architecture-decision)).

## 1. Authentication mechanism (CONFIRMED, cross-verified in two independent implementations)

Both `prismarine-auth` (JS) and `elytra-ms` (Python) implement the identical, well-understood
four-step Microsoft identity chain. Reading both independently and finding matching endpoints,
headers, and payloads is strong confirmation this is accurate and stable:

1. **Device code request** — `POST https://login.microsoftonline.com/consumers/oauth2/v2.0/devicecode`
   (or the legacy `https://login.live.com/oauth20_connect.srf` used by `prismarine-auth`'s
   default `live` flow) with `client_id` and `scope=Xboxlive.signin` (+`offline_access` for a
   refresh token). Returns `device_code`, `user_code`, `verification_uri`, `interval`, `expires_in`.
2. **Token polling** — `POST .../oauth2/v2.0/token` with
   `grant_type=urn:ietf:params:oauth:grant-type:device_code`, polled every `interval` seconds
   until the user completes login in their own browser. Yields an MSA `access_token` +
   `refresh_token`.
3. **Xbox Live user token (XBL)** — `POST https://user.auth.xboxlive.com/user/authenticate` with
   `RelyingParty: http://auth.xboxlive.com`, `Properties.RpsTicket: "d=" + access_token`. Returns
   an XAU token.
4. **XSTS token** — `POST https://xsts.auth.xboxlive.com/xsts/authorize` with
   `RelyingParty: https://pocket.realms.minecraft.net/` (Bedrock Realms-specific — confirmed
   identical in both `prismarine-realms/src/constants.js` and `elytra-ms`'s
   `BedrockRealmsAPI.RELYING_PATH`) and `Properties.UserTokens: [xbl_user_token]`. Returns an XSTS
   token containing the XUID, gamertag, and userhash.
5. **Realms API calls** authenticate with header
   `Authorization: XBL3.0 x={userhash};{xsts_token}` against
   `https://pocket.realms.minecraft.net/`, plus `Client-Version` (a real Bedrock client version
   string) and `User-Agent: MCPE/UWP`.

**No Microsoft password ever needs to be stored or seen by the integration** — device code auth
is a public-client flow; the user authenticates in their own browser on any device.

### Client ID / "title" registration (RESOLVED during Phase 3 — see below)

Xbox Live gates some auth flows to a recognized "title" (an approved Minecraft/Xbox client). Two
approaches are used in the wild:

- **Reuse a known public Microsoft first-party client ID.** `prismarine-auth`'s default `live`
  flow ships several of these in `Titles.js` (e.g. `MinecraftNintendoSwitch:
  '00000000441cc96b'`) and its README states plainly: *"If flow is live, the default, then you
  can only specify existing Microsoft client IDs."* Critically, this only works against the
  **legacy `login.live.com` endpoints** that `prismarine-auth`'s `live` flow actually calls — not
  against the modern Azure AD v2 endpoints (`login.microsoftonline.com/consumers/oauth2/v2.0/*`)
  this project uses.
- **Register your own Azure AD "public client" app** (free, no client secret needed for device
  code) and use the modern AAD v2 endpoints — this is what `elytra-ms`/RealmsPlayerlistBot
  actually do (`XBOX_CLIENT_ID` env var, a self-registered app, per elytra-ms's own README setup
  instructions, fetched directly from source during Phase 3: *"Register a new application in
  Azure AD... Select 'Personal Microsoft accounts only' under supported account types."*).

**CONFIRMED during Phase 3 (live test against the developer's real account):** pairing the AAD v2
endpoints with the first-party `MinecraftNintendoSwitch` title ID fails immediately with
`AADSTS700016: Application with identifier '00000000441cc96b' was not found in the directory` —
the two approaches above are mutually exclusive protocol families, not interchangeable options,
and this project's `const.py` had accidentally mixed them (AAD v2 URLs + a first-party title ID).
This was found by the project's own code-review process before the live test even confirmed it,
and fixed by making the mismatch explicit rather than silently guessing:
`custom_components/minecraft_bedrock_realms/const.py`'s `DEFAULT_CLIENT_ID` comment now documents
the incompatibility, and `poc/realm_cli.py` gained a `--client-id` flag so a self-registered app ID
can be supplied instead of the (non-working, for this endpoint family) default.

**Registration recipe, cross-checked against elytra-ms's own README and official Microsoft Learn
troubleshooting docs (fetched directly, not from memory) — this is the exact, minimal, working
recipe for the Bedrock Realms use case specifically:**

1. https://portal.azure.com/#blade/Microsoft_AAD_RegisteredApps/ApplicationsListBlade → *New
   registration*.
2. Any name. **Supported account types: "Personal Microsoft accounts only."**
3. No redirect URI is needed — this project's device-code flow never redirects. (elytra-ms's own
   README asks for one, but only because its bundled `elytra-authenticate` quickstart script uses
   a different, redirect-based flow for convenience; this project's `auth.py` implements pure
   device-code and doesn't need it.)
4. **Authentication → Advanced settings → "Allow public client flows" → Yes.** This step is not
   optional: Microsoft's own troubleshooting documentation for error `AADSTS7000218` states
   device-code flow "is not using a redirect URI" so Entra ID "uses the app registration's
   ['Enable the following mobile and desktop flows'] to determine whether the client is
   confidential or public" — device code requests fail with `AADSTS7000218` until this is set.
5. No client secret is needed (this project's code never sends one). Copy the **Application
   (client) ID** from the Overview page and pass it via `poc/realm_cli.py --client-id`.

**Also confirmed — no Xbox Developer Program / Partner Center approval is needed for this use
case**, resolving an apparent contradiction found during research: one Microsoft Q&A community
answer claims `XboxLive.signin` requires formal Xbox Developer Program enrollment, but that
answer was about the **Java Edition** `api.minecraftservices.com` API specifically, which
separately requires app approval via `https://aka.ms/mce-reviewappid` (confirmed via
minecraft.wiki's Microsoft-authentication article: *"api.minecraftservices.com will return a 403"*
without it). **The Bedrock Realms API (`pocket.realms.minecraft.net`) has no equivalent gate** —
confirmed by elytra-ms's README describing plain self-service Azure AD registration with no
approval step, and by RealmsPlayerlistBot (built on exactly that recipe) having authenticated to
`pocket.realms.minecraft.net` in continuous production use since 2020 without any such approval.
This project is Bedrock-only and therefore unaffected by the Java-specific approval gate.

### Token persistence (CONFIRMED pattern)

Both libraries persist tokens to a local file/cache keyed by account, and transparently refresh
on expiry (`prismarine-auth`'s `FileCache` + per-stage `verifyTokens()`; `elytra-ms`'s
`AuthenticationManager.refresh_tokens()`, which force-refreshes the whole chain on a 401). Home
Assistant's own `ConfigEntry.data`/`hass.config_entries.async_update_entry` (backed by the HA
Storage helper, which HA encrypts/protects at rest under `.storage/`) is the equivalent
mechanism for the integration and is what we will use — no separate token file.

## 2. Realms API surface (CONFIRMED from `prismarine-realms/src/bedrock/api.js` + `index.js`, cross-checked against `elytra-ms/elytra/bedrock_realms/__init__.py`)

Both libraries expose the same underlying endpoints (paths below are relative to
`https://pocket.realms.minecraft.net/`):

| Purpose | Endpoint | Notes |
|---|---|---|
| List Realms the account owns or joined | `GET /worlds` | Returns `servers[]`. Each item includes id, name, owner, `state` (`OPEN`/`CLOSED`), `daysLeft`, `expired`, `maxPlayers`, `activeSlot`, `slots`, `member`, and a `players` field (see caveat below). |
| Get one Realm | `GET /worlds/{realmId}` | Same shape as one entry from `/worlds`, only for owned/joined Realms. |
| Realm connection address | `GET /worlds/{realmId}/join` | Returns `host:port` for direct MCPE connection — not needed for monitoring, only if a future feature wants to display join address. |
| **Live player activity (all Realms in one call)** | `GET /activities/live/players` | **This is the mechanism this project needs.** See §3. |
| Subscription info | `GET /subscriptions/{realmId}` or `/subscriptions/{realmId}/details` | Days left, renewal period, subscription type/store. |
| Backups | `GET /worlds/{realmId}/backups` | Metadata incl. game difficulty, game mode, version, size. |
| Invite management | `GET/POST /links/v1`, `GET /invites/pending`, `PUT /invites/accept/{id}` | Not needed for monitoring. |
| Open/close Realm | `PUT /worlds/{realmId}/open` \| `/close` | **Destructive/administrative** — out of scope for v1 monitoring per project requirements. |
| Reset/delete Realm, ban/op players | `PUT /worlds/{realmId}/reset`, `DELETE /worlds/{realmId}`, blocklist endpoints | **Destructive** — explicitly excluded from this project entirely (not even behind a disabled-by-default service in v1; see [architecture.md](architecture.md)). |

### Realm player list schema (CONFIRMED shape, reliability CAVEAT)

`/worlds` and `/worlds/{realmId}` include a `players` array on each Realm:

```ts
interface RealmPlayer {
  uuid: string       // XUID
  name: string | null
  operator: boolean
  accepted: boolean
  online: boolean
  permission: "VISITOR" | "MEMBER" | "OPERATOR"
}
```

This looks at first glance like it could answer "who is online" directly. **We do not rely on
it for that purpose.** Evidence:

- In the test fixtures for both libraries, `players` is frequently `null`/absent, and appears
  tied to Realm *membership* (people who have an invite/accepted relationship with the Realm),
  not necessarily "currently connected."
- RealmsPlayerlistBot — the one production system whose entire purpose is accurate live
  playerlists — **does not use this field at all**. Its polling loop
  (`exts/playerlist.py::parse_realms`) exclusively iterates `realm.players` off the result of
  `fetch_activities()`, i.e. the dedicated activities endpoint from §3, never off
  `fetch_realms()`. That is a strong signal from the most relevant real-world implementation that
  `/worlds[].players[].online` is not the reliable live-presence source.
- **Marked INFERRED, not confirmed**: we don't have positive proof this field is stale/wrong,
  only that the most Realms-experienced open-source project avoids it. We will still read it (as
  a fallback / for member-roster display) but will use §3's endpoint as the source of truth for
  online/offline state, matching RealmsPlayerlistBot's proven approach.

## 3. Live player detection — the key question (CONFIRMED)

This directly answers the project's central research question.

**`GET https://pocket.realms.minecraft.net/activities/live/players`** returns, in one call, the
live player activity for *every* Realm the authenticated account can see:

```
ActivityListResponse
  servers: [
    {
      id: number          // realm id
      full: boolean
      players: [
        { uuid: string, name: null, operator: bool, accepted: bool, online: bool, permission: str }
      ]
    }
  ]
```

Confirmed directly in `elytra-ms/elytra/bedrock_realms/__init__.py`:
```python
async def fetch_activities(self) -> ActivityListResponse:
    return await ActivityListResponse.from_response(await self.get("activities/live/players"))
```
and this is exactly what RealmsPlayerlistBot polls once a minute in production
(`exts/playerlist.py::get_people_runner` → `parse_realms` → `self.bot.realms.fetch_activities()`).

Important nuances, all confirmed by reading the code:

- **`name` is always `null`** on this endpoint. It gives you XUIDs and online flags only — not
  gamertags. Resolving XUID → gamertag requires a *separate* call, either to Xbox's Profile API
  (`https://profile.xboxlive.com/...`) or the batch People Hub API
  (`https://peoplehub.xboxlive.com/...`), both of which `elytra-ms` also implements natively in
  Python (`elytra/xbox/profile`, `elytra/xbox/peoplehub`). RealmsPlayerlistBot caches
  XUID→gamertag mappings (its Redis-backed `gamertag_from_xuid`/`fill_in_gamertags_for_sessions`)
  precisely because this second lookup is the expensive/rate-limited part, not the activities
  poll itself.
- **This is a polling mechanism, not a persistent connection.** RealmsPlayerlistBot does **not**
  run a Bedrock protocol client that joins the world, and does **not** rely on Xbox
  presence/"currently playing" status (that data exists via `peoplehub` but is used by the bot
  only as a *secondary* signal for device-type info, gated behind a premium feature — not for
  join/leave detection). Join/leave is entirely computed by diffing successive polls of this one
  endpoint. This directly satisfies the project requirement "work without a Minecraft client
  permanently connected to the Realm."
- **One HTTP call covers every Realm on the account**, regardless of how many Realms are tracked.
  This matters for rate-limit budgeting: monitoring N Realms does not cost N requests per poll
  cycle for the player-presence piece (only the `/worlds/{id}` calls, if used for the other
  sensors, scale with realm count — and those can be batched/staggered too).

**Prismarine-realms currently does NOT implement this Bedrock endpoint.** Its `src/java/api.js`
has `getLivePlayerLists()` hitting `/activities/liveplayerlist` (note: different path, no `/live/`
segment) for **Java Edition Realms only**; `src/bedrock/api.js` has no equivalent method at all
(verified by grep across the whole repository — zero matches for `LivePlayerList`, `activities`,
or `live/players` in the bedrock module). This is a real feature gap in prismarine-realms for our
use case, not a sign the endpoint doesn't exist — `elytra-ms`/RealmsPlayerlistBot prove the
Bedrock endpoint is real, documented-by-use, and actively relied upon in production. It simply
means we cannot use prismarine-realms as-is even if we wanted a Node-based approach; we'd have to
patch it. This is one more point in favor of a native implementation (see below) over a
Node-bridge architecture, since the Node ecosystem's purpose-built library doesn't even cover the
one endpoint we need most.

## 4. Rate limits & polling interval (INFERRED from production behavior; no official docs exist)

Microsoft does not publish rate limits for the Realms or Xbox Live consumer APIs. Evidence
gathered from the two implementations:

- `elytra-ms`'s HTTP transport (`retry_transport.py`) treats `429, 502, 503, 504` as retryable,
  honors a `Retry-After` header when present, and otherwise backs off exponentially
  (`backoff_factor * 2^attempt` with jitter, capped at 30s, max 3 attempts by default).
  `prismarine-realms`'s `Rest.js` retries `5xx` only (not 429 explicitly) up to 4 times with
  `2^n * 1000ms` backoff.
- RealmsPlayerlistBot polls `fetch_activities()` **once every 60 seconds**, aligned to the top of
  the minute (`next_time()` rounds up to the next `:00`), across potentially many thousands of
  Discord-linked Realms in a single account/process. This is the strongest real-world evidence we
  have that a **60-second interval is safe for sustained, long-running production polling** of
  this specific endpoint. We did not find evidence of what happens below 30s (untested by either
  reference project).

**Recommendation**: default polling interval of **60 seconds** (not 30s) given this is the only
empirically-tested cadence found in a large-scale production system; allow the user to configure
15/30/60/120/300s per the spec, but document that <30s is unverified and may be more likely to
hit rate limits, and implement 429/5xx-aware exponential backoff regardless of configured
interval (see [architecture.md](architecture.md) for the coordinator design).

## 5. Realms Plus / "10 players" semantics (UNCERTAIN — validate in PoC)

`maxPlayers` is returned directly by `/worlds` and `/worlds/{id}` as an integer — we do not need
to hardcode 10. Whether the owner counts against this limit is not visible in any of the source
code inspected (it's a business-logic detail of the Realms service, not exposed as a distinct
field). **Do not hardcode owner-inclusion assumptions**; surface `maxPlayers` and the live player
count as returned, and note in the README that exact slot semantics for Realms Plus should be
confirmed against the user's own account during the PoC.

## 6. Python-native feasibility — direct answer to the architecture question

**Confirmed possible and proven in production**: `elytra-ms` is a real, MIT-licensed,
async-native (httpx-based) Python library implementing the complete MSA→XBL→XSTS→Realms chain,
including the Bedrock live-activity endpoint, and it is the actual dependency powering
RealmsPlayerlistBot — a bot serving a large number of real Discord communities continuously
since 2020. This directly answers the project's open question: **implementing Microsoft/Xbox/Realm
authentication in Python is not fragile or unrealistic — it is already done, maintained, and
running at scale.** There is no technical reason requiring a Node.js bridge.

We will not add `elytra-ms` itself as a runtime dependency of the Home Assistant integration
(see [architecture.md](architecture.md) for why — dependency footprint and HA's `aiohttp`
convention), but we treat it as validated proof of feasibility and as the primary reference for
the request/response shapes our own minimal client implements.

## 7. Architecture decision

See [architecture.md](architecture.md) for the full write-up. Summary: **native Python Home
Assistant custom integration, no external bridge process** — matching both the technical findings
above and the user's explicit preference for a integration installable purely through HACS.

## Open items to validate in Phase 3 (PoC)

1. Whether a self-registered Azure AD public-client app ID works end-to-end for XBL/XSTS/Realms,
   or whether a known first-party title ID is required (see §1).
2. Real-world shape of `/worlds[].players` vs `/activities/live/players` side-by-side on the
   user's actual Realm, to confirm the reliability gap described in §2.
3. Exact behavior of `maxPlayers` / owner-slot counting for a Realms Plus subscription (§5).
4. Whether `Client-Version` needs to closely track the real current Bedrock version or is lenient
   (both libraries note their hardcoded version "can be a few versions behind").
