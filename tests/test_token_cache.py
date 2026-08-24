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
