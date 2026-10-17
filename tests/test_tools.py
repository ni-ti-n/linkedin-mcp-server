"""Tool-level tests: exercise the registered tools end-to-end with mocked HTTP."""

from __future__ import annotations

import json

import httpx
import pytest
import respx

from linkedin_mcp.config import REST_BASE, USERINFO_URL
from linkedin_mcp.server import build_server


@pytest.fixture
def server(config):
    return build_server(config)


import dataclasses

from linkedin_mcp.config import Config

_SELF_SERVE = {
    "linkedin_get_profile",
    "linkedin_create_post",
    "linkedin_create_poll",
    "linkedin_reshare_post",
    "linkedin_update_post",
    "linkedin_delete_post",
    "linkedin_comment",
    "linkedin_upload_image",
    "linkedin_upload_video",
    "linkedin_upload_document",
}
_SOCIAL_FEED = {"linkedin_react", "linkedin_unreact", "linkedin_get_social_metadata"}
_ORG = {
    "linkedin_get_organization",
    "linkedin_find_organization_by_vanity",
    "linkedin_get_org_follower_count",
    "linkedin_list_admined_organizations",
}


async def _tool_names(server) -> set[str]:
    return {t.name for t in await server.list_tools()}


async def test_default_config_advertises_only_self_serve_tools(config):
    """Flags off → exactly the 10 w_member_social tools, none of the gated 7."""
    cfg = dataclasses.replace(config, enable_social_feed=False, enable_org=False)
    names = await _tool_names(build_server(cfg))
    assert names == _SELF_SERVE
    assert len(names) == 10
    assert not (names & _SOCIAL_FEED)
    assert not (names & _ORG)


async def test_social_feed_flag_adds_only_feed_tools(config):
    cfg = dataclasses.replace(config, enable_social_feed=True, enable_org=False)
    names = await _tool_names(build_server(cfg))
    assert names == _SELF_SERVE | _SOCIAL_FEED
    assert not (names & _ORG)


async def test_all_flags_on_advertises_full_surface(config):
    cfg = dataclasses.replace(config, enable_social_feed=True, enable_org=True)
    names = await _tool_names(build_server(cfg))
    assert names == _SELF_SERVE | _SOCIAL_FEED | _ORG
    assert len(names) == 17


async def _call(server, name: str, args: dict):
    """Invoke a registered tool's underlying function directly.

    Going through the raw callable (``Tool.fn``) rather than the MCP dispatch
    wrapper keeps real return dicts and real exception types (APIError /
    ScopeError) intact, which is what we assert on.
    """
    tool = server._tool_manager.get_tool(name)
    return await tool.fn(**args)


@respx.mock
async def test_get_profile_builds_person_urn(server):
    respx.get(USERINFO_URL).mock(
        return_value=httpx.Response(200, json={"sub": "xyz", "name": "Jane", "email": "j@x.com"})
    )
    out = await _call(server, "linkedin_get_profile", {})
    assert out["person_urn"] == "urn:li:person:xyz"
    assert out["name"] == "Jane"


@respx.mock
async def test_create_text_post(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:111"})
    )
    out = await _call(
        server,
        "linkedin_create_post",
        {"author_urn": "urn:li:person:me", "commentary": "hello world"},
    )
    assert out["post_urn"] == "urn:li:share:111"
    body = json.loads(route.calls.last.request.content)
    assert body["commentary"] == "hello world"
    assert body["lifecycleState"] == "PUBLISHED"
    assert "content" not in body  # text-only


@respx.mock
async def test_empty_commentary_coerced_to_space(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:1"})
    )
    await _call(
        server,
        "linkedin_create_post",
        {"author_urn": "urn:li:person:me", "commentary": ""},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["commentary"] == " "


@respx.mock
async def test_single_image_post_shape(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:2"})
    )
    await _call(
        server,
        "linkedin_create_post",
        {
            "author_urn": "urn:li:person:me",
            "commentary": "pic",
            "image_urns": ["urn:li:image:1"],
            "image_alt_texts": ["a cat"],
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body["content"]["media"] == {"id": "urn:li:image:1", "altText": "a cat"}


@respx.mock
async def test_multi_image_post_shape(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:3"})
    )
    await _call(
        server,
        "linkedin_create_post",
        {
            "author_urn": "urn:li:person:me",
            "commentary": "gallery",
            "image_urns": ["urn:li:image:1", "urn:li:image:2"],
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert len(body["content"]["multiImage"]["images"]) == 2


@respx.mock
async def test_article_post_shape(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:4"})
    )
    await _call(
        server,
        "linkedin_create_post",
        {
            "author_urn": "urn:li:person:me",
            "commentary": "read this",
            "article_url": "https://example.com",
            "article_title": "Title",
        },
    )
    body = json.loads(route.calls.last.request.content)
    assert body["content"]["article"]["source"] == "https://example.com"


async def test_two_media_types_rejected(server):
    from linkedin_mcp.errors import APIError

    with pytest.raises(APIError):
        await _call(
            server,
            "linkedin_create_post",
            {
                "author_urn": "urn:li:person:me",
                "commentary": "x",
                "image_urns": ["urn:li:image:1"],
                "video_urn": "urn:li:video:1",
            },
        )


async def test_poll_option_count_validation(server):
    from linkedin_mcp.errors import APIError

    with pytest.raises(APIError):
        await _call(
            server,
            "linkedin_create_poll",
            {"author_urn": "urn:li:person:me", "question": "q", "options": ["only one"]},
        )


@respx.mock
async def test_poll_post_shape(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:5"})
    )
    await _call(
        server,
        "linkedin_create_poll",
        {
            "author_urn": "urn:li:person:me",
            "question": "Tabs or spaces?",
            "options": ["Tabs", "Spaces"],
            "duration": "THREE_DAYS",
        },
    )
    body = json.loads(route.calls.last.request.content)
    poll = body["content"]["poll"]
    assert poll["settings"]["duration"] == "THREE_DAYS"
    assert len(poll["options"]) == 2


@respx.mock
async def test_update_post_partial_update_header(server):
    route = respx.post(f"{REST_BASE}/posts/urn%3Ali%3Ashare%3A6").mock(
        return_value=httpx.Response(200)
    )
    out = await _call(
        server,
        "linkedin_update_post",
        {"post_urn": "urn:li:share:6", "commentary": "edited"},
    )
    assert out["status"] == "updated"
    req = route.calls.last.request
    assert req.headers.get("X-RestLi-Method") == "PARTIAL_UPDATE"
    assert json.loads(req.content)["patch"]["$set"]["commentary"] == "edited"


@respx.mock
async def test_delete_post(server):
    route = respx.delete(f"{REST_BASE}/posts/urn%3Ali%3Ashare%3A7").mock(
        return_value=httpx.Response(204)
    )
    out = await _call(server, "linkedin_delete_post", {"post_urn": "urn:li:share:7"})
    assert out["status"] == "deleted"
    assert route.called


@respx.mock
async def test_reshare_sets_reshare_context(server):
    route = respx.post(f"{REST_BASE}/posts").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:share:8"})
    )
    await _call(
        server,
        "linkedin_reshare_post",
        {"author_urn": "urn:li:person:me", "reshared_post_urn": "urn:li:share:orig"},
    )
    body = json.loads(route.calls.last.request.content)
    assert body["reshareContext"]["parent"] == "urn:li:share:orig"


@respx.mock
async def test_organization_tool_scope_error(server):
    respx.get(f"{REST_BASE}/organizations/1035").mock(
        return_value=httpx.Response(403, text="access_denied: scope required")
    )
    # Tools now RETURN a structured error dict instead of raising, so the opaque
    # MCP "Error executing tool" wrapper never fires and the real cause is visible.
    result = await _call(server, "linkedin_get_organization", {"organization_id": "1035"})
    assert result["error"] == "ScopeError"
    assert result["status"] == 403
    assert "access_denied" in result["linkedin_response"]
    assert "hint" in result


@respx.mock
async def test_react_scope_error_is_surfaced(server):
    respx.post(url__regex=rf"{REST_BASE}/reactions.*").mock(
        return_value=httpx.Response(
            403,
            text='{"message":"Not enough permissions to access: createReaction","status":403}',
        )
    )
    result = await _call(
        server,
        "linkedin_react",
        {
            "actor_urn": "urn:li:person:me",
            "object_urn": "urn:li:activity:123",
            "reaction": "LIKE",
        },
    )
    assert result["error"] == "ScopeError"
    assert result["status"] == 403
    assert "createReaction" in result["linkedin_response"]


@respx.mock
async def test_react_sends_correct_body_and_header(server):
    route = respx.post(url__regex=rf"{REST_BASE}/reactions.*").mock(
        return_value=httpx.Response(201, headers={"x-restli-id": "urn:li:reaction:1"})
    )
    await _call(
        server,
        "linkedin_react",
        {
            "actor_urn": "urn:li:person:me",
            "object_urn": "urn:li:activity:123",
            "reaction": "PRAISE",
        },
    )
    req = route.calls.last.request
    # actor is a query param; body carries root + reactionType; CREATE method set.
    assert "actor=urn%3Ali%3Aperson%3Ame" in str(req.url)
    body = json.loads(req.content)
    assert body == {"root": "urn:li:activity:123", "reactionType": "PRAISE"}
    assert req.headers.get("x-restli-method") == "CREATE"


@respx.mock
async def test_social_metadata_scope_error_is_surfaced(server):
    respx.get(url__regex=rf"{REST_BASE}/socialMetadata/.*").mock(
        return_value=httpx.Response(403, text='{"message":"forbidden","status":403}')
    )
    result = await _call(
        server, "linkedin_get_social_metadata", {"object_urn": "urn:li:activity:123"}
    )
    assert result["error"] == "ScopeError"
    assert result["status"] == 403
