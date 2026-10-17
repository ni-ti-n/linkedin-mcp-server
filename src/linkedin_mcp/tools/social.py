"""Social tools — comments, reactions, social metadata.

Scope reality (confirmed against LinkedIn's Community Management docs):

* ``linkedin_comment``       — writes a comment; works with ``w_member_social``.
* ``linkedin_react`` /
  ``linkedin_unreact``       — the versioned Reactions collection needs
                               ``w_member_social_feed`` (a Community Management
                               permission distinct from ``w_member_social``).
* ``linkedin_get_social_metadata`` — the socialMetadata read needs
                               ``r_member_social_feed``, which LinkedIn marks
                               **Restricted — granted to select developers only**.

The two feed-scoped tools will return a structured ScopeError (not an opaque
failure) until the app is approved for those permissions.
"""

from __future__ import annotations

from typing import Literal

from .._compat import MCPServer

from ..client import LinkedInClient
from ..errors import tool_safe

_REACTIONS = {
    "LIKE",
    "PRAISE",
    "EMPATHY",
    "INTEREST",
    "APPRECIATION",
    "ENTERTAINMENT",
}


def register(mcp: MCPServer, client: LinkedInClient, enable_social_feed: bool = False) -> None:
    @mcp.tool()
    @tool_safe
    async def linkedin_comment(
        actor_urn: str,
        object_urn: str,
        text: str,
        parent_comment_urn: str | None = None,
    ) -> dict:
        """Comment on a post, or reply to a comment.

        Scope: ``w_member_social``.

        Args:
            actor_urn: Who is commenting (``urn:li:person:...`` or org URN).
            object_urn: The post URN being commented on.
            text: The comment body.
            parent_comment_urn: If replying to a comment, that comment's URN.
        """
        encoded = client.encode_urn(object_urn)
        body: dict = {"actor": actor_urn, "message": {"text": text}}
        if parent_comment_urn:
            body["parentComment"] = parent_comment_urn
        resp = await client.post(f"/socialActions/{encoded}/comments", json=body)
        return {
            "comment_urn": resp.headers.get("x-restli-id"),
            "object_urn": object_urn,
            "status": "created",
        }

    # ---- Community Management tools (need *_social_feed) --------------------
    # Only registered when LINKEDIN_ENABLE_SOCIAL_FEED is set, so the default
    # server advertises only tools that work on self-serve w_member_social.
    if not enable_social_feed:
        return

    @mcp.tool()
    @tool_safe
    async def linkedin_react(
        actor_urn: str,
        object_urn: str,
        reaction: Literal[
            "LIKE", "PRAISE", "EMPATHY", "INTEREST", "APPRECIATION", "ENTERTAINMENT"
        ] = "LIKE",
    ) -> dict:
        """Add a reaction to a post or comment.

        Scope: ``w_member_social_feed`` (Community Management — NOT plain
        ``w_member_social``). Without it LinkedIn returns 403 and this tool
        surfaces a ScopeError explaining the required permission.

        Args:
            actor_urn: Who is reacting (``urn:li:person:...``).
            object_urn: The post or comment URN to react to.
            reaction: LIKE, PRAISE (celebrate), EMPATHY (support), INTEREST,
                APPRECIATION (insightful), or ENTERTAINMENT (funny).
        """
        # The Reactions collection takes the actor as a query param and
        # {root, reactionType} in the body, with the RestLi CREATE method header.
        body = {"root": object_urn, "reactionType": reaction}
        resp = await client.post(
            f"/reactions?actor={client.encode_urn(actor_urn)}",
            json=body,
            extra_headers={"X-RestLi-Method": "CREATE"},
        )
        return {
            "object_urn": object_urn,
            "reaction": reaction,
            "status": "created",
            "id": resp.headers.get("x-restli-id"),
        }

    @mcp.tool()
    @tool_safe
    async def linkedin_unreact(actor_urn: str, object_urn: str) -> dict:
        """Remove your reaction from a post or comment.

        Scope: ``w_member_social_feed`` (same as ``linkedin_react``).

        Args:
            actor_urn: Who is removing the reaction.
            object_urn: The post or comment URN.
        """
        enc_actor = client.encode_urn(actor_urn)
        enc_obj = client.encode_urn(object_urn)
        await client.delete(f"/reactions/(actor:{enc_actor},entity:{enc_obj})")
        return {"object_urn": object_urn, "status": "removed"}

    @mcp.tool()
    @tool_safe
    async def linkedin_get_social_metadata(object_urn: str) -> dict:
        """Read like/comment counts and the reaction summary for a post.

        Scope: ``r_member_social_feed`` — LinkedIn marks this **Restricted
        (granted to select developers only)**, so this will return a ScopeError
        until your app is granted that permission. Not reachable with plain
        ``w_member_social``.

        Args:
            object_urn: The post URN.
        """
        encoded = client.encode_urn(object_urn)
        resp = await client.get(f"/socialMetadata/{encoded}")
        return resp.json()
