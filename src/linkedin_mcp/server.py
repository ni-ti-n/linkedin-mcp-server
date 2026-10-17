"""LinkedIn MCP Server entry point.

Builds one FastMCP app, registers every tool domain, and runs over the transport
chosen by ``LINKEDIN_MCP_TRANSPORT``:

  stdio  (default) — Amazon Quick Desktop local connector, Amazon Q CLI,
                     Claude Desktop, Cline, Continue, etc.
  http            — streamable HTTP, for hosting behind Amazon Quick Suite
                     (cloud) / Bedrock AgentCore Runtime.
"""

from __future__ import annotations

import sys

from ._compat import MCPServer
from .auth import TokenProvider
from .client import LinkedInClient
from .config import Config
from .tools import media, organizations, posts, profile, social


def build_server(config: Config | None = None) -> MCPServer:
    cfg = config or Config.from_env()
    tokens = TokenProvider(cfg)
    client = LinkedInClient(cfg, tokens)

    mcp = MCPServer(
        "linkedin",
        instructions=(
            "Tools to publish and manage LinkedIn content. Call "
            "linkedin_get_profile first to obtain the author_urn (urn:li:person:...) "
            "that post-creation tools require. Image/video/document posts need a "
            "two-step flow: upload the file (returns an asset URN), then pass that "
            "URN to linkedin_create_post. Organization tools require partner-approved "
            "scopes and return a clear error if the token lacks them."
        ),
    )

    for module in (profile, media, posts):
        module.register(mcp, client)
    social.register(mcp, client, enable_social_feed=cfg.enable_social_feed)
    organizations.register(mcp, client, enable_org=cfg.enable_org)

    return mcp


def main() -> None:
    cfg = Config.from_env()
    mcp = build_server(cfg)

    if cfg.transport == "http":
        # Streamable HTTP (for hosting). Bind host/port come from env.
        # `settings` exists on both SDK versions but we set defensively.
        settings = getattr(mcp, "settings", None)
        if settings is not None:
            try:
                settings.host = cfg.http_host
                settings.port = cfg.http_port
            except (AttributeError, ValueError):
                pass
        print(
            f"linkedin-mcp: streamable-http on {cfg.http_host}:{cfg.http_port}",
            file=sys.stderr,
        )
        mcp.run(transport="streamable-http")
    else:
        mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
