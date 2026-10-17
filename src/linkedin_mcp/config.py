"""Runtime configuration, loaded from environment variables.

No secrets are logged. All values are read once at process start.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

# Base URLs
REST_BASE = "https://api.linkedin.com/rest"
# OIDC userinfo lives on the un-versioned v2 surface (the only v2 call we make).
USERINFO_URL = "https://api.linkedin.com/v2/userinfo"
AUTHORIZE_URL = "https://www.linkedin.com/oauth/v2/authorization"
TOKEN_URL = "https://www.linkedin.com/oauth/v2/accessToken"


def _default_cache() -> Path:
    return Path.home() / ".linkedin-mcp" / "token.json"


@dataclass(frozen=True)
class Config:
    access_token: str | None
    client_id: str | None
    client_secret: str | None
    oauth_port: int
    scopes: str
    api_version: str
    transport: str
    http_host: str
    http_port: int
    token_cache: Path
    enable_social_feed: bool
    enable_org: bool

    @property
    def redirect_uri(self) -> str:
        return f"http://localhost:{self.oauth_port}/callback"

    @classmethod
    def from_env(cls) -> "Config":
        cache = os.environ.get("LINKEDIN_TOKEN_CACHE")
        return cls(
            access_token=os.environ.get("LINKEDIN_ACCESS_TOKEN") or None,
            client_id=os.environ.get("LINKEDIN_CLIENT_ID") or None,
            client_secret=os.environ.get("LINKEDIN_CLIENT_SECRET") or None,
            oauth_port=int(os.environ.get("LINKEDIN_OAUTH_PORT", "8765")),
            scopes=os.environ.get(
                "LINKEDIN_SCOPES", "openid profile email w_member_social"
            ),
            api_version=os.environ.get("LINKEDIN_API_VERSION", "202606"),
            transport=os.environ.get("LINKEDIN_MCP_TRANSPORT", "stdio").lower(),
            http_host=os.environ.get("LINKEDIN_MCP_HTTP_HOST", "127.0.0.1"),
            http_port=int(os.environ.get("LINKEDIN_MCP_HTTP_PORT", "8080")),
            token_cache=Path(cache) if cache else _default_cache(),
            # Partner-scoped tools are OFF by default so the server advertises
            # only the 10 tools that work on self-serve w_member_social. Flip
            # these on once your app is approved for the respective programs.
            enable_social_feed=_env_bool("LINKEDIN_ENABLE_SOCIAL_FEED"),
            enable_org=_env_bool("LINKEDIN_ENABLE_ORG"),
        )


def _env_bool(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in {"1", "true", "yes", "on"}
