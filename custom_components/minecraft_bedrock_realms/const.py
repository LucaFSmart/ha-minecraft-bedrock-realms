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
