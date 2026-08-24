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
    except (json.JSONDecodeError, KeyError, ValueError, TypeError):
        return None


def save_token(token: OAuthToken, path: Path = DEFAULT_CACHE_PATH) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(token.to_dict()), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass  # best-effort; not all platforms (e.g. Windows) support POSIX chmod bits
