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
