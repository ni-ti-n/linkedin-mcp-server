"""Post tools — Tier 1 (self-serve: w_member_social).

Covers the full organic Posts API content matrix: text, article/link, single &
multi-image, video, document, and poll — plus edit, delete, and reshare.

The same tools accept an organization author URN; posting *as an organization*
additionally requires ``w_organization_social`` + a Page role (Tier 2), which the
client surfaces as a clear ScopeError if the token lacks it.
"""

from __future__ import annotations

from typing import Literal

from .._compat import MCPServer

from ..client import LinkedInClient
from ..errors import APIError

_POLL_DURATIONS = {"ONE_DAY", "THREE_DAYS", "SEVEN_DAYS", "FOURTEEN_DAYS"}


def _base_post(author_urn: str, commentary: str, visibility: str) -> dict:
    # LinkedIn 422s on empty commentary; a single space is the documented workaround.
    return {
        "author": author_urn,
        "commentary": commentary if commentary.strip() else " ",
        "visibility": visibility,
        "distribution": {
            "feedDistribution": "MAIN_FEED",
            "targetEntities": [],
            "thirdPartyDistributionChannels": [],
        },
        "lifecycleState": "PUBLISHED",
        "isReshareDisabledByAuthor": False,
    }


def register(mcp: MCPServer, client: LinkedInClient) -> None:
    @mcp.tool()
    async def linkedin_create_post(
        author_urn: str,
        commentary: str,
        visibility: Literal["PUBLIC", "CONNECTIONS", "LOGGED_IN"] = "PUBLIC",
        image_urns: list[str] | None = None,
        image_alt_texts: list[str] | None = None,
        video_urn: str | None = None,
        video_title: str | None = None,
        document_urn: str | None = None,
        document_title: str | None = None,
        article_url: str | None = None,
        article_title: str | None = None,
        article_description: str | None = None,
    ) -> dict:
        """Create a LinkedIn post. Supports text, image, multi-image, video,
        document, and article/link posts — pick ONE media type per call.

        - Text only: pass just ``commentary``.
        - Image: upload with ``linkedin_upload_image`` first, pass its URN in
          ``image_urns`` (1 = single image, 2–20 = multi-image carousel).
        - Video: pass ``video_urn`` from ``linkedin_upload_video``.
        - Document: pass ``document_urn`` from ``linkedin_upload_document``.
        - Article/link: pass ``article_url`` (+ optional title/description); no
          upload needed.

        Args:
            author_urn: ``urn:li:person:...`` (self) or ``urn:li:organization:...`` (page).
            commentary: The post text (an empty string is coerced to a single space).
            visibility: PUBLIC, CONNECTIONS, or LOGGED_IN.
            image_urns: Image URNs for an image/multi-image post.
            image_alt_texts: Optional alt text per image (same order as image_urns).
            video_urn: A video URN for a video post.
            document_urn: A document URN for a document post.
            article_url: A URL for an article/link post.
        """
        media_choices = [
            bool(image_urns),
            bool(video_urn),
            bool(document_urn),
            bool(article_url),
        ]
        if sum(media_choices) > 1:
            raise APIError(
                400,
                "Pick only one media type per post (images OR video OR document OR article).",
            )

        body = _base_post(author_urn, commentary, visibility)

        if image_urns:
            if len(image_urns) == 1:
                img: dict = {"id": image_urns[0]}
                if image_alt_texts:
                    img["altText"] = image_alt_texts[0]
                body["content"] = {"media": img}
            else:
                images = []
                for i, urn in enumerate(image_urns):
                    entry: dict = {"id": urn}
                    if image_alt_texts and i < len(image_alt_texts):
                        entry["altText"] = image_alt_texts[i]
                    images.append(entry)
                body["content"] = {"multiImage": {"images": images}}
        elif video_urn:
            video: dict = {"id": video_urn}
            if video_title:
                video["title"] = video_title
            body["content"] = {"media": video}
        elif document_urn:
            doc: dict = {"id": document_urn}
            if document_title:
                doc["title"] = document_title
            body["content"] = {"media": doc}
        elif article_url:
            article: dict = {"source": article_url}
            if article_title:
                article["title"] = article_title
            if article_description:
                article["description"] = article_description
            body["content"] = {"article": article}

        resp = await client.post("/posts", json=body)
        post_urn = resp.headers.get("x-restli-id")
        return {"post_urn": post_urn, "status": "published"}

    @mcp.tool()
    async def linkedin_create_poll(
        author_urn: str,
        question: str,
        options: list[str],
        duration: Literal["ONE_DAY", "THREE_DAYS", "SEVEN_DAYS", "FOURTEEN_DAYS"] = "SEVEN_DAYS",
        visibility: Literal["PUBLIC", "CONNECTIONS", "LOGGED_IN"] = "PUBLIC",
    ) -> dict:
        """Create a poll post with 2–4 options.

        Poll content cannot be edited after creation. Do not ask for political
        opinions, health status, or other sensitive data (LinkedIn policy).

        Args:
            author_urn: The author URN.
            question: The poll question (used as the post commentary).
            options: 2 to 4 answer options.
            duration: ONE_DAY, THREE_DAYS, SEVEN_DAYS, or FOURTEEN_DAYS.
        """
        if not 2 <= len(options) <= 4:
            raise APIError(400, "A poll needs between 2 and 4 options.")
        if duration not in _POLL_DURATIONS:
            raise APIError(400, f"duration must be one of {sorted(_POLL_DURATIONS)}.")

        body = _base_post(author_urn, question, visibility)
        body["content"] = {
            "poll": {
                "question": question,
                "options": [{"text": o} for o in options],
                "settings": {"duration": duration, "voteSelectionType": "SINGLE_VOTE"},
            }
        }
        resp = await client.post("/posts", json=body)
        return {"post_urn": resp.headers.get("x-restli-id"), "status": "published"}

    @mcp.tool()
    async def linkedin_reshare_post(
        author_urn: str,
        reshared_post_urn: str,
        commentary: str = " ",
        visibility: Literal["PUBLIC", "CONNECTIONS", "LOGGED_IN"] = "PUBLIC",
    ) -> dict:
        """Reshare an existing post, optionally with your own commentary.

        Args:
            author_urn: The resharing author's URN.
            reshared_post_urn: URN of the post to reshare (``urn:li:share:...`` or ``urn:li:ugcPost:...``).
            commentary: Optional text to add above the reshare.
        """
        body = _base_post(author_urn, commentary, visibility)
        body["reshareContext"] = {"parent": reshared_post_urn}
        resp = await client.post("/posts", json=body)
        return {"post_urn": resp.headers.get("x-restli-id"), "status": "published"}

    @mcp.tool()
    async def linkedin_update_post(
        post_urn: str,
        commentary: str | None = None,
    ) -> dict:
        """Edit an existing post's commentary (text).

        LinkedIn's partial-update only supports editing the commentary of an
        existing post; author, media, and poll content cannot be changed.

        Args:
            post_urn: The post URN (``urn:li:share:...`` or ``urn:li:ugcPost:...``).
            commentary: New post text.
        """
        if commentary is None:
            raise APIError(400, "Provide `commentary` to update.")
        encoded = client.encode_urn(post_urn)
        patch = {"patch": {"$set": {"commentary": commentary}}}
        await client.post(
            f"/posts/{encoded}",
            json=patch,
            extra_headers={"X-RestLi-Method": "PARTIAL_UPDATE"},
        )
        return {"post_urn": post_urn, "status": "updated"}

    @mcp.tool()
    async def linkedin_delete_post(post_urn: str) -> dict:
        """Delete a post.

        Args:
            post_urn: The post URN to delete.
        """
        encoded = client.encode_urn(post_urn)
        await client.delete(f"/posts/{encoded}")
        return {"post_urn": post_urn, "status": "deleted"}
