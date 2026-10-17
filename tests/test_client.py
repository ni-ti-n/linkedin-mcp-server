"""Client + flow tests. LinkedIn HTTP mocked with respx."""

from __future__ import annotations

import httpx
import pytest
import respx

from linkedin_mcp.client import LinkedInClient
from linkedin_mcp.config import REST_BASE, USERINFO_URL
from linkedin_mcp.errors import APIError, ScopeError


def test_encode_urn():
    assert LinkedInClient.encode_urn("urn:li:share:123") == "urn%3Ali%3Ashare%3A123"


@respx.mock
async def test_headers_include_version_and_restli(client: LinkedInClient):
    route = respx.get(f"{REST_BASE}/posts/x").mock(
        return_value=httpx.Response(200, json={"ok": True})
    )
    await client.get("/posts/x")
    sent = route.calls.last.request
    assert sent.headers["Authorization"] == "Bearer test-token"
    assert sent.headers["LinkedIn-Version"] == "202606"
    assert sent.headers["X-Restli-Protocol-Version"] == "2.0.0"


@respx.mock
async def test_userinfo(client: LinkedInClient):
    respx.get(USERINFO_URL).mock(
        return_value=httpx.Response(
            200, json={"sub": "abc", "name": "Jane", "email": "j@x.com"}
        )
    )
    info = await client.userinfo()
    assert info["sub"] == "abc"


@respx.mock
async def test_scope_error_mapping(client: LinkedInClient):
    respx.get(f"{REST_BASE}/organizations/1").mock(
        return_value=httpx.Response(403, text="Not authorized — missing scope")
    )
    with pytest.raises(ScopeError):
        await client.get("/organizations/1")


@respx.mock
async def test_generic_api_error(client: LinkedInClient):
    respx.get(f"{REST_BASE}/posts/x").mock(
        return_value=httpx.Response(500, text="boom")
    )
    with pytest.raises(APIError) as exc:
        await client.get("/posts/x")
    assert exc.value.status == 500


@respx.mock
async def test_upload_media_three_steps(client: LinkedInClient, tmp_path):
    img = tmp_path / "pic.png"
    img.write_bytes(b"\x89PNG\r\n\x1a\n")

    init = respx.post(f"{REST_BASE}/images?action=initializeUpload").mock(
        return_value=httpx.Response(
            200,
            json={"value": {"uploadUrl": "https://upload.example/abc", "image": "urn:li:image:999"}},
        )
    )
    put = respx.put("https://upload.example/abc").mock(
        return_value=httpx.Response(201)
    )

    urn = await client.upload_media("urn:li:person:me", str(img), "images")
    assert urn == "urn:li:image:999"
    assert init.called
    assert put.called
    # The PUT must NOT carry our bearer token (the signed URL handles auth).
    assert "Authorization" not in put.calls.last.request.headers


@respx.mock
async def test_upload_media_missing_file(client: LinkedInClient):
    with pytest.raises(APIError):
        await client.upload_media("urn:li:person:me", "/no/such/file.png", "images")
