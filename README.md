# LinkedIn MCP Server (Python)

A [Model Context Protocol](https://modelcontextprotocol.io/) server that lets any
MCP client — **Amazon Quick**, **Amazon Q**, Claude Desktop, Cline, Continue —
publish and manage LinkedIn content in natural language: create posts (text,
image, multi-image, video, document, article, poll), upload media, edit/delete,
comment, and reshare on a self-serve token. Reactions, engagement reads, and
company-Page tools are also built in, gated behind opt-in flags because LinkedIn
requires partner approval for them.

By default the server advertises the **10 tools that work on a self-serve token**;
the 7 partner-scoped tools stay hidden until you opt in (see
[Feature tiers](#feature-tiers-what-your-token-can-actually-reach)).

Built with Python + [FastMCP](https://github.com/modelcontextprotocol/python-sdk),
plain LinkedIn REST, and OAuth 2.0. Runs over **stdio** (local) or **streamable
HTTP** (hosted) from the same codebase.

> Unofficial integration. Not affiliated with LinkedIn. Use within
> [LinkedIn's API Terms](https://legal.linkedin.com/api-terms-of-use).

---

## Amazon Quick Desktop vs Amazon Quick Web — read this first

Amazon Quick comes in two forms with **different MCP requirements**:

| Surface | Transport it needs | How to run this server |
|---|---|---|
| **Amazon Quick Desktop** (native app) | Local connector (runs a command) **or** remote HTTP | Run over **stdio** (default). Add as a *Local* connector. |
| **Amazon Quick Web** (browser / cloud, aka Quick Suite) | **Remote only** — streamable HTTP / SSE over HTTPS; stdio **not** supported | Run over **HTTP** and host it (e.g. behind Bedrock AgentCore Runtime), then add as a remote MCP connector. |

Every **other** MCP client — Amazon Q Developer CLI, Claude Desktop, Cline,
Continue — runs the default **stdio** server locally, exactly like Quick Desktop.

The transport is a single env var (`LINKEDIN_MCP_TRANSPORT=stdio|http`) — no code
change between the two.

---

## Feature tiers (what your token can actually reach)

The server advertises **10 tools by default** — exactly the ones that work on a
self-serve token. The other 7 are built in full but **hidden behind two
default-off flags**, because LinkedIn requires partner approval for the scopes
they need. Flip a flag only once your app is approved for that program; otherwise
those tools would only return a ScopeError.

| Flag | Default | Adds | Needs |
|---|---|---|---|
| *(none)* | — | the 10 self-serve tools below | `openid profile email w_member_social` |
| `LINKEDIN_ENABLE_SOCIAL_FEED` | `false` | 3 reaction/metadata tools | Community Management (`*_social_feed`) |
| `LINKEDIN_ENABLE_ORG` | `false` | 4 organization tools | Marketing/Org scopes + Page admin role |

Tool count: default **10** → `+SOCIAL_FEED` **13** → `+ORG` **14** → both **17**.

### ✅ Self-serve — advertised by default (10 tools)
Scopes `openid profile email w_member_social`, granted instantly by adding the
**Sign In with LinkedIn (OIDC)** and **Share on LinkedIn** products to your app.

| Tool | What it does |
|---|---|
| `linkedin_get_profile` | Your name, email, picture, and **person URN** |
| `linkedin_create_post` | Text / image / multi-image / video / document / article post |
| `linkedin_create_poll` | Poll post (2–4 options, 1/3/7/14-day) |
| `linkedin_reshare_post` | Reshare an existing post with commentary |
| `linkedin_update_post` | Edit a post's text |
| `linkedin_delete_post` | Delete a post |
| `linkedin_upload_image` | Upload an image → image URN |
| `linkedin_upload_video` | Upload a video → video URN |
| `linkedin_upload_document` | Upload a PDF/document → document URN |
| `linkedin_comment` | Comment on a post / reply to a comment |

### ⚠️ Community Management — gated behind `LINKEDIN_ENABLE_SOCIAL_FEED` (3 tools)
Need `w_member_social_feed` (reactions) / `r_member_social_feed` (metadata, which
LinkedIn marks **Restricted — granted to select developers only**). Plain
`w_member_social` is **not** sufficient — these endpoints return 403 until your
app is approved for the Community Management API.

| Tool | What it does | Scope |
|---|---|---|
| `linkedin_react` | Add a reaction to a post/comment | `w_member_social_feed` |
| `linkedin_unreact` | Remove your reaction | `w_member_social_feed` |
| `linkedin_get_social_metadata` | Like/comment counts + reaction summary | `r_member_social_feed` |

### 🏢 Organization — gated behind `LINKEDIN_ENABLE_ORG` (4 tools)
Need Marketing Developer Platform approval or a Page admin role
(`rw_organization_admin`, `r_organization_social`). Fully implemented; until
approved they return a clear ScopeError.

| Tool | What it does |
|---|---|
| `linkedin_get_organization` | Look up a company Page by org ID |
| `linkedin_find_organization_by_vanity` | Find a Page by its URL slug |
| `linkedin_get_org_follower_count` | Follower statistics for a Page |
| `linkedin_list_admined_organizations` | Pages you can administer |

Posting **as an organization** also works through `linkedin_create_post` — pass an
`urn:li:organization:...` author URN (needs `w_organization_social` + a Page role).

> **Clear errors, not opaque failures.** Every tool is wrapped so a LinkedIn
> error comes back as a structured `{error, status, linkedin_response, hint}`
> dict — a missing-scope 403 names the exact permission required instead of
> failing silently.

> **No native scheduling.** LinkedIn's public Posts API only accepts
> `lifecycleState: PUBLISHED`. Scheduling must live in your own layer.

---

## Install

```bash
git clone <this-repo>
cd linkedin-mcp-server
python3 -m venv .venv && source .venv/bin/activate
pip install -e .
```

## Get a LinkedIn access token (quickest path)

1. Create a **Company Page** (LinkedIn requires every app to be linked to one):
   [linkedin.com/company/setup/new](https://www.linkedin.com/company/setup/new).
2. Create an app at the [Developer Portal](https://developer.linkedin.com/) linked
   to that Page.
3. **Products** tab → request access to **Sign In with LinkedIn using OpenID
   Connect** and **Share on LinkedIn** (both auto-approved).
4. **Auth** tab → add redirect URL
   `https://www.linkedin.com/developers/tools/oauth/redirect` (for the token
   generator) and `http://localhost:8765/callback` (for this server's interactive
   login).
5. Generate a token at the
   [token generator](https://www.linkedin.com/developers/tools/oauth/token-generator)
   with scopes `openid profile email w_member_social` (expires in 60 days), **or**
   let this server run the interactive login (see Config below).

## Configure

Copy `.env.example` → `.env`, or set the vars in your MCP client. Two auth modes:

- **Bring your own token** (simplest / headless): set `LINKEDIN_ACCESS_TOKEN`.
- **Interactive OAuth (PKCE)**: set `LINKEDIN_CLIENT_ID` (+ `LINKEDIN_CLIENT_SECRET`
  if your app is confidential). The server opens a browser on first use and caches
  the token at `~/.linkedin-mcp/token.json`.

**Partner-scoped tool groups** are off by default. Once LinkedIn approves your app
for the relevant program, set `LINKEDIN_ENABLE_SOCIAL_FEED=true` (reactions /
social metadata) and/or `LINKEDIN_ENABLE_ORG=true` (organization tools) to make
them appear. See [Feature tiers](#feature-tiers-what-your-token-can-actually-reach).

---

## Client setup

### Amazon Quick Desktop (Local connector)
Desktop App → **Customize → Connectors → Create → Create local connector → Local**:

- **Command**: `/absolute/path/to/.venv/bin/python`
- **Arguments**: `-m linkedin_mcp.server`
- **Environment variables**: `LINKEDIN_ACCESS_TOKEN` = your token

### Amazon Quick Web (browser / cloud, remote HTTP)
Host the server with `LINKEDIN_MCP_TRANSPORT=http` behind an HTTPS endpoint
(e.g. Bedrock AgentCore Runtime). Then in the Quick console →
**Connectors → Model Context Protocol (MCP)** → set the **MCP server endpoint**
to your `https://.../mcp` URL and pick an auth method (No Auth / OAuth / S2S).

### Amazon Q Developer CLI
```bash
q mcp add --name linkedin \
  --command /absolute/path/to/.venv/bin/python \
  --args '["-m", "linkedin_mcp.server"]'
# then set LINKEDIN_ACCESS_TOKEN in the environment / agent config
```

### Claude Desktop / Cline / Continue
```json
{
  "mcpServers": {
    "linkedin": {
      "command": "/absolute/path/to/.venv/bin/python",
      "args": ["-m", "linkedin_mcp.server"],
      "env": { "LINKEDIN_ACCESS_TOKEN": "paste-your-token-here" }
    }
  }
}
```

---

## Try it

> "What's my LinkedIn profile?" → returns your name, email, and person URN.
> "Post on LinkedIn: Excited to share our new MCP server!"
> "Upload ~/pic.png and post it with the caption 'Launch day 🚀'."
> "Reshare urn:li:share:123 with the note 'This is great.'"
> "Delete my last post."

## Development

```bash
pip install -e ".[dev]"
pytest           # LinkedIn calls are mocked with respx — no network, no token
```

## Architecture

```
src/linkedin_mcp/
  server.py          FastMCP app + stdio|http transport
  config.py          env-driven config
  auth.py            OAuth 2.0 PKCE loopback flow + token cache + env fallback
  client.py          REST client: versioned headers, URN encoding, media upload, error mapping
  errors.py          AuthError / ScopeError / APIError + tool_safe (structured-error wrapper)
  tools/
    profile.py       whoami
    posts.py         create / poll / reshare / update / delete
    media.py         image / video / document upload
    social.py        comment (always) + react / unreact / social metadata (LINKEDIN_ENABLE_SOCIAL_FEED)
    organizations.py company tools, gated behind LINKEDIN_ENABLE_ORG
```

## License

MIT
