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
#
# WARNING - unverified pairing (see docs/research.md SS1): this ID is a
# first-party Minecraft "title" ID. It is documented to work with
# prismarine-auth's *legacy* `login.live.com` device-code flow, which uses a
# different scope format and a different (older) device-code protocol. This
# project instead calls the modern Azure AD v2 endpoints above
# (login.microsoftonline.com/consumers/oauth2/v2.0/*), matching elytra-ms.
# Pairing a first-party title ID with the AAD v2 endpoints has not been
# validated against a real account and is likely to fail with
# AADSTS700016 (unauthorized_client), since AAD v2 generally expects a
# client ID that is registered as an app in Azure AD, not a first-party
# title ID.
#
# Recommended: register a free Azure AD "public client" app (no client
# secret required for the device-code flow) and pass its client ID via
# --client-id instead of relying on this default. This constant is kept
# as a documented, clearly-labeled fallback for the one live verification
# attempt in Phase 3 - not because the pairing is expected to work.
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
