"""Media upload tools — Tier 1 (self-serve: w_member_social).

Each uploads a local file via LinkedIn's 3-step flow and returns an asset URN to
reference when creating a post.
"""

from __future__ import annotations

from .._compat import MCPServer

from ..client import LinkedInClient


def register(mcp: MCPServer, client: LinkedInClient) -> None:
    @mcp.tool()
    async def linkedin_upload_image(author_urn: str, file_path: str) -> dict:
        """Upload a local image file and return its image URN.

        Pass the returned ``urn:li:image:...`` to ``linkedin_create_post`` as one
        of ``image_urns`` (one image = single-image post, 2–20 = multi-image).

        Args:
            author_urn: The owner URN (``urn:li:person:...`` or ``urn:li:organization:...``).
            file_path: Absolute path to a local image (PNG/JPG/GIF).
        """
        urn = await client.upload_media(author_urn, file_path, "images")
        return {"image_urn": urn}

    @mcp.tool()
    async def linkedin_upload_video(author_urn: str, file_path: str) -> dict:
        """Upload a local video file and return its video URN.

        LinkedIn processes video asynchronously; a freshly uploaded video may take
        a short while before a post referencing it goes fully live.

        Args:
            author_urn: The owner URN.
            file_path: Absolute path to a local video (MP4).
        """
        urn = await client.upload_media(author_urn, file_path, "videos")
        return {"video_urn": urn}

    @mcp.tool()
    async def linkedin_upload_document(author_urn: str, file_path: str) -> dict:
        """Upload a local document (e.g. PDF) and return its document URN.

        Reference the returned ``urn:li:document:...`` via ``document_urn`` on
        ``linkedin_create_post`` to publish a document/carousel-style post.

        Args:
            author_urn: The owner URN.
            file_path: Absolute path to a local document (PDF).
        """
        urn = await client.upload_media(author_urn, file_path, "documents")
        return {"document_urn": urn}
