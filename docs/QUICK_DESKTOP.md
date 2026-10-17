# Amazon Quick Desktop — Local Connector Setup

This guides you through connecting the LinkedIn MCP server to **Amazon Quick
Desktop** as a local connector. Quick Desktop runs the server as a local
subprocess over **stdio** — no hosting required.

> **Prerequisite — a LinkedIn access token.** The connector needs
> `LINKEDIN_ACCESS_TOKEN` set. Generate a 60‑day token with scopes
> `openid profile email w_member_social` at the
> [LinkedIn OAuth token generator](https://www.linkedin.com/developers/tools/oauth/token-generator)
> (requires a LinkedIn app with the **Sign In with LinkedIn (OIDC)** and
> **Share on LinkedIn** products added). If you don't have a token yet, ask me
> to walk you through it.

Command template (replace the path with your checkout's absolute path):

```
Command:   /absolute/path/to/linkedin-mcp-server/.venv/bin/python
Arguments: -m linkedin_mcp.server
```

The venv Python boots the server and advertises the **10 self-serve tools** over
stdio (profile, posts, media, comment). The 7 partner-scoped tools stay hidden
unless you enable them (see "Partner-scoped tools" below). Using the venv's own
Python means no `PATH`/activation needed.

---

## Option A — Local connection (type the fields in)

1. Open **Amazon Quick Desktop** → **Customize** → **Connectors** tab.
2. Choose **Create** → **Create local connector**.
3. In the dialog, pick connection type **Local**, then fill in:

   | Field | Value |
   |---|---|
   | **Name** | `LinkedIn` |
   | **Command** | `/absolute/path/to/linkedin-mcp-server/.venv/bin/python` |
   | **Arguments** | `-m linkedin_mcp.server` |
   | **Description** | `Publish and manage LinkedIn content — profile, posts (text/image/video/document/article/poll), edit, delete, reshare, comments, reactions, social metadata, and org lookups.` |
   | **Timeout (seconds)** | `30` (default is fine) |

4. Under **Environment variables**, choose **+ Add variable** and add:

   | Key | Value |
   |---|---|
   | `LINKEDIN_ACCESS_TOKEN` | *your 60‑day token* |
   | `LINKEDIN_API_VERSION` | `202606` |
   | `LINKEDIN_MCP_TRANSPORT` | `stdio` |

5. Save. Quick Desktop launches the server, performs the MCP handshake, and the
   10 self-serve tools become available to agents in chat and scheduled tasks.

---

## Option B — Import an existing config

Quick Desktop's **Import** connection type scans an `mcp.json` and detects the
servers in it. A ready file is at:

```
/absolute/path/to/linkedin-mcp-server/examples/quick-desktop.mcp.json
```

1. Edit that file: replace the `command` path with your checkout's absolute path
   and `PASTE_YOUR_60_DAY_TOKEN_HERE` with your real token.
2. In the connector dialog choose **Import**, and for **Config file path** enter:
   `/absolute/path/to/linkedin-mcp-server/examples/quick-desktop.mcp.json`
3. Save.

> ⚠️ A token in a plain file is a credential on disk. Prefer **Option A** (enter
> the token as an environment variable in the dialog) so it isn't stored in the
> repo tree. `examples/quick-desktop.mcp.json` ships with a placeholder, not a
> real token — don't commit a real one.

---

## Verify it works

Once connected, ask the Quick agent:

> "Use the LinkedIn tools to show my profile."

That calls `linkedin_get_profile`, which hits the OIDC `/v2/userinfo` endpoint
and returns your name, email, picture, and person URN — the first real round
trip and the simplest proof the token and connector are both good.

## Troubleshooting

- **Server won't start / timeout** — confirm the Command path exists:
  `ls /absolute/path/to/linkedin-mcp-server/.venv/bin/python`.
  If you moved/rebuilt the venv, update the path.
- **401 / auth errors on a tool call** — the token is missing, expired (60‑day
  limit, no refresh on self‑serve), or lacks `w_member_social`. Regenerate it.
- **Only 10 tools show up** — that's the default. The 3 Community Management
  tools (react/unreact/social metadata) and 4 organization tools are hidden
  until you opt in with `LINKEDIN_ENABLE_SOCIAL_FEED=true` /
  `LINKEDIN_ENABLE_ORG=true` in the connector's env — and they need LinkedIn
  partner approval to actually work.
