"""Profile tools — Tier 1 (self-serve: openid profile email)."""

from __future__ import annotations

from .._compat import MCPServer

from ..client import LinkedInClient


def register(mcp: MCPServer, client: LinkedInClient) -> None:
    @mcp.tool()
    async def linkedin_get_profile() -> dict:
        """Get the authenticated member's LinkedIn profile.

        Returns name, email, profile picture, locale and — most importantly — the
        member's person URN (e.g. ``urn:li:person:abc123``), which is the
        ``author_urn`` required by all post-creation tools. Call this first and
        reuse the URN.
        """
        info = await client.userinfo()
        sub = info.get("sub")
        return {
            "name": info.get("name"),
            "given_name": info.get("given_name"),
            "family_name": info.get("family_name"),
            "email": info.get("email"),
            "email_verified": info.get("email_verified"),
            "picture": info.get("picture"),
            "locale": info.get("locale"),
            "person_urn": f"urn:li:person:{sub}" if sub else None,
            "sub": sub,
        }
