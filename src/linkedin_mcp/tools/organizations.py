"""Organization tools — Tier 2 (partner-approved: rw_organization_admin /
r_organization_social / w_organization_social + a Page admin role).

These are implemented in full so the product is complete, but will return a
clear ScopeError until your LinkedIn app is approved for the relevant org
scopes. The client turns LinkedIn's 403/invalid-scope responses into an
actionable message.
"""

from __future__ import annotations

from .._compat import MCPServer

from ..client import LinkedInClient
from ..errors import tool_safe


def register(mcp: MCPServer, client: LinkedInClient, enable_org: bool = False) -> None:
    # All organization tools need Marketing/Organization partner scopes. Skip
    # registration entirely unless LINKEDIN_ENABLE_ORG is set.
    if not enable_org:
        return

    @mcp.tool()
    @tool_safe
    async def linkedin_get_organization(organization_id: str) -> dict:
        """Look up a company Page by its numeric organization ID.

        Requires an approved org scope (rw_organization_admin / r_organization_social).

        Args:
            organization_id: The numeric org ID (e.g. "1035"), not the full URN.
        """
        resp = await client.get(f"/organizations/{organization_id}")
        return resp.json()

    @mcp.tool()
    @tool_safe
    async def linkedin_find_organization_by_vanity(vanity_name: str) -> dict:
        """Find a company Page by its vanity name (the slug in its LinkedIn URL).

        Requires an approved org scope.

        Args:
            vanity_name: The URL slug, e.g. "microsoft" for linkedin.com/company/microsoft.
        """
        resp = await client.get(
            "/organizations",
            params={"q": "vanityName", "vanityName": vanity_name},
        )
        return resp.json()

    @mcp.tool()
    @tool_safe
    async def linkedin_get_org_follower_count(organization_urn: str) -> dict:
        """Get follower statistics for a company Page.

        Requires rw_organization_admin or r_organization_social.

        Args:
            organization_urn: Full org URN, e.g. "urn:li:organization:1035".
        """
        resp = await client.get(
            "/organizationalEntityFollowerStatistics",
            params={"q": "organizationalEntity", "organizationalEntity": organization_urn},
        )
        return resp.json()

    @mcp.tool()
    @tool_safe
    async def linkedin_list_admined_organizations() -> dict:
        """List the company Pages the authenticated member can administer.

        Useful for discovering which organization URNs you may post as. Requires
        rw_organization_admin.
        """
        resp = await client.get(
            "/organizationAcls",
            params={"q": "roleAssignee", "role": "ADMINISTRATOR", "state": "APPROVED"},
        )
        return resp.json()
