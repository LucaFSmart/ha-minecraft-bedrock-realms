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
    DEFAULT_CLIENT_ID,
    REALMS_XSTS_RELYING_PARTY,
    XBOX_LIVE_XSTS_RELYING_PARTY,
)
from custom_components.minecraft_bedrock_realms.exceptions import RealmsClientError
from custom_components.minecraft_bedrock_realms.realms_api import RealmsAPI
from custom_components.minecraft_bedrock_realms.xbox_profile import XboxProfileClient
from poc.token_cache import load_token, save_token


async def _authenticate(session: aiohttp.ClientSession, client_id: str | None) -> tuple[str, str]:
    """Runs (or resumes) the auth chain. Returns (realms_auth_header, xbox_live_auth_header)."""
    effective_client_id = client_id or DEFAULT_CLIENT_ID
    auth = MicrosoftAuth(session, client_id=effective_client_id)

    oauth_token = load_token()
    if oauth_token is not None and not oauth_token.is_valid():
        print("Cached token expired, refreshing...")
        try:
            oauth_token = await auth.refresh_oauth_token(oauth_token)
        except RealmsClientError:
            oauth_token = None

    if oauth_token is None:
        if not client_id:
            print(
                "Warning: using the default first-party client ID, which is unverified against "
                "this project's OAuth endpoints. If sign-in fails, register a free Azure AD app "
                "and pass --client-id (see docs/research.md).",
                file=sys.stderr,
            )
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


async def _run(realm_name_filter: str | None, *, client_id: str | None = None) -> int:
    async with aiohttp.ClientSession() as session:
        try:
            realms_auth_header, xbox_auth_header = await _authenticate(session, client_id)
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
                try:
                    gamertag = await profile_client.get_gamertag(xuid)
                except RealmsClientError:
                    gamertag = None
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
    parser.add_argument(
        "--client-id",
        dest="client_id",
        default=None,
        help=(
            "Azure AD public-client app ID to use for sign-in. If omitted, falls back to a "
            "first-party Minecraft client ID that is unverified against this project's OAuth "
            "endpoints (see docs/research.md)."
        ),
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.debug else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )

    exit_code = asyncio.run(_run(args.realm_name_filter, client_id=args.client_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
