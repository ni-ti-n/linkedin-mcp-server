"""Shared fixtures. All LinkedIn HTTP is mocked with respx — no network, no token."""

from __future__ import annotations

from pathlib import Path

import pytest

from linkedin_mcp.auth import TokenProvider
from linkedin_mcp.client import LinkedInClient
from linkedin_mcp.config import Config


@pytest.fixture
def config(tmp_path: Path) -> Config:
    return Config(
        access_token="test-token",
        client_id=None,
        client_secret=None,
        oauth_port=8765,
        scopes="openid profile email w_member_social",
        api_version="202606",
        transport="stdio",
        http_host="127.0.0.1",
        http_port=8080,
        token_cache=tmp_path / "token.json",
        # Tests exercise the full tool surface, so enable the partner-gated tools.
        enable_social_feed=True,
        enable_org=True,
    )


@pytest.fixture
def client(config: Config) -> LinkedInClient:
    return LinkedInClient(config, TokenProvider(config))
