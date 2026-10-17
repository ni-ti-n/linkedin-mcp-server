"""Thin LinkedIn REST client.

Centralizes: versioned headers, URN URL-encoding, the 3-step media upload dance,
and mapping LinkedIn's HTTP errors to readable MCP messages (notably turning a
Tier-2 403/invalid-scope into an actionable ScopeError).
"""

from __future__ import annotations

import urllib.parse
from pathlib import Path
from typing import Any

import httpx

from .auth import TokenProvider
from .config import REST_BASE, USERINFO_URL, Config
from .errors import APIError, ScopeError

_RESTLI = "2.0.0"


class LinkedInClient:
    def __init__(self, config: Config, tokens: TokenProvider):
        self._cfg = config
        self._tokens = tokens

    # -- headers -------------------------------------------------------------
    def _headers(self, extra: dict[str, str] | None = None) -> dict[str, str]:
        headers = {
            "Authorization": f"Bearer {self._tokens.get_token()}",
            "LinkedIn-Version": self._cfg.api_version,
            "X-Restli-Protocol-Version": _RESTLI,
        }
        if extra:
            headers.update(extra)
        return headers

    @staticmethod
    def encode_urn(urn: str) -> str:
        """URL-encode a URN for use inside a REST path."""
        return urllib.parse.quote(urn, safe="")

    # -- error mapping -------------------------------------------------------
    @staticmethod
    def _raise_for_status(resp: httpx.Response) -> None:
        if resp.is_success:
            return
        body = resp.text
        lowered = body.lower()
        scope_signals = (
            "scope",
            "permission",
            "access_denied",
            "not authorized",
            "not enough permissions",
            "does not have access",
            "unpermitted",
            "_feed",  # the Community Management *_social_feed permissions
        )
        # A 403 on these collections is effectively always a missing partner
        # scope: w_member_social can post/comment but cannot reach the versioned
        # Reactions / socialMetadata collections, which need *_social_feed.
        if resp.status_code == 403 or (
            resp.status_code == 401 and any(s in lowered for s in scope_signals)
        ):
            raise ScopeError(
                f"LinkedIn rejected this call ({resp.status_code}): your token lacks "
                f"the required scope / page role. Reactions and social-metadata reads "
                f"need LinkedIn's Community Management permissions "
                f"(w_member_social_feed to react; r_member_social_feed — Restricted, "
                f"select developers only — to read counts), not plain w_member_social. "
                f"Org tools need rw_organization_admin / w_organization_social + a Page "
                f"role. Details: {body}",
                status=resp.status_code,
                body=body,
            )
        raise APIError(resp.status_code, f"LinkedIn API error {resp.status_code}", body)

    # -- generic verbs -------------------------------------------------------
    async def get(self, path: str, params: dict[str, Any] | None = None) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                f"{REST_BASE}{path}", headers=self._headers(), params=params
            )
        self._raise_for_status(resp)
        return resp

    async def post(
        self, path: str, json: dict[str, Any], extra_headers: dict[str, str] | None = None
    ) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{REST_BASE}{path}",
                headers=self._headers(extra_headers),
                json=json,
            )
        self._raise_for_status(resp)
        return resp

    async def delete(self, path: str) -> httpx.Response:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.delete(f"{REST_BASE}{path}", headers=self._headers())
        self._raise_for_status(resp)
        return resp

    # -- OIDC userinfo (v2, un-versioned) ------------------------------------
    async def userinfo(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(
                USERINFO_URL,
                headers={"Authorization": f"Bearer {self._tokens.get_token()}"},
            )
        self._raise_for_status(resp)
        return resp.json()

    # -- media upload (image / video / document) -----------------------------
    async def upload_media(self, author_urn: str, file_path: str, kind: str) -> str:
        """Run the 3-step upload and return the asset URN.

        kind: "images" | "videos" | "documents"
        """
        path = Path(file_path).expanduser()
        if not path.is_file():
            raise APIError(400, f"File not found: {path}")

        key = {
            "images": "image",
            "videos": "video",
            "documents": "document",
        }[kind]

        # Step 1 — initialize the upload.
        init = await self.post(
            f"/{kind}?action=initializeUpload",
            json={"initializeUploadRequest": {"owner": author_urn}},
        )
        value = init.json()["value"]
        upload_url = value["uploadUrl"]
        asset_urn = value[key]

        # Step 2 — PUT raw bytes to the signed URL. No auth header (the URL is signed).
        data = path.read_bytes()
        async with httpx.AsyncClient(timeout=120) as client:
            put = await client.put(
                upload_url,
                content=data,
                headers={"Content-Type": "application/octet-stream"},
            )
        if not put.is_success:
            raise APIError(put.status_code, "Binary upload to LinkedIn failed", put.text)

        # Step 3 — caller references ``asset_urn`` in the post body.
        return asset_urn
