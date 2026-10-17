"""OAuth 2.0 for LinkedIn.

Two ways to get a bearer token, in priority order:

1. ``LINKEDIN_ACCESS_TOKEN`` env var — bring your own token (headless / Amazon
   Quick Suite / CI). Simplest; no client secret needed.
2. Interactive Authorization-Code-with-PKCE flow — if ``LINKEDIN_CLIENT_ID`` is
   set and no token env var is present, the server opens a browser, runs a tiny
   loopback HTTP server to catch the redirect, exchanges the code for a token,
   and caches it at ``~/.linkedin-mcp/token.json`` for reuse.

LinkedIn member tokens last 60 days. Refresh tokens require the ``offline_access``
product, which most apps are not approved for, so by default we re-prompt when a
cached token is near expiry.
"""

from __future__ import annotations

import base64
import hashlib
import json
import os
import secrets
import threading
import time
import urllib.parse
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer

import httpx

from .config import AUTHORIZE_URL, TOKEN_URL, Config
from .errors import AuthError

# Refresh/re-prompt if the cached token has fewer than this many seconds left.
_EXPIRY_SKEW = 5 * 60


def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class _CodeCatcher(BaseHTTPRequestHandler):
    """One-shot handler that captures ?code= from the OAuth redirect."""

    code: str | None = None
    state: str | None = None
    error: str | None = None
    expected_state: str = ""

    def do_GET(self):  # noqa: N802 (stdlib naming)
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != "/callback":
            self.send_response(404)
            self.end_headers()
            return
        params = urllib.parse.parse_qs(parsed.query)
        _CodeCatcher.error = (params.get("error") or [None])[0]
        _CodeCatcher.code = (params.get("code") or [None])[0]
        _CodeCatcher.state = (params.get("state") or [None])[0]
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        msg = (
            "LinkedIn authorization complete. You can close this tab and return "
            "to your MCP client."
            if _CodeCatcher.code
            else f"Authorization failed: {_CodeCatcher.error}"
        )
        self.wfile.write(
            f"<html><body style='font-family:sans-serif'><h3>{msg}</h3></body></html>".encode()
        )

    def log_message(self, *_args):  # silence the stdlib access log
        return


class TokenProvider:
    """Resolves and caches a LinkedIn bearer token for the process."""

    def __init__(self, config: Config):
        self._cfg = config
        self._token: str | None = None
        self._expires_at: float = 0.0

    # -- public API ----------------------------------------------------------
    def get_token(self) -> str:
        """Return a valid bearer token, acquiring one if necessary."""
        if self._cfg.access_token:
            return self._cfg.access_token

        if self._token and time.time() < self._expires_at - _EXPIRY_SKEW:
            return self._token

        cached = self._load_cache()
        if cached and time.time() < cached[1] - _EXPIRY_SKEW:
            self._token, self._expires_at = cached
            return self._token

        if not self._cfg.client_id:
            raise AuthError(
                "No LinkedIn credentials. Set LINKEDIN_ACCESS_TOKEN, or set "
                "LINKEDIN_CLIENT_ID/LINKEDIN_CLIENT_SECRET to run the interactive "
                "login flow. See .env.example."
            )
        self._token, self._expires_at = self._interactive_login()
        self._save_cache(self._token, self._expires_at)
        return self._token

    # -- interactive PKCE flow ----------------------------------------------
    def _interactive_login(self) -> tuple[str, float]:
        verifier = _b64url(secrets.token_bytes(32))
        challenge = _b64url(hashlib.sha256(verifier.encode("ascii")).digest())
        state = secrets.token_urlsafe(16)

        auth_params = {
            "response_type": "code",
            "client_id": self._cfg.client_id,
            "redirect_uri": self._cfg.redirect_uri,
            "scope": self._cfg.scopes,
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        auth_url = f"{AUTHORIZE_URL}?{urllib.parse.urlencode(auth_params)}"

        _CodeCatcher.code = None
        _CodeCatcher.error = None
        _CodeCatcher.state = None
        _CodeCatcher.expected_state = state

        server = HTTPServer(("127.0.0.1", self._cfg.oauth_port), _CodeCatcher)
        thread = threading.Thread(target=server.handle_request, daemon=True)
        thread.start()

        webbrowser.open(auth_url)
        # Wait up to 5 minutes for the redirect.
        deadline = time.time() + 300
        while thread.is_alive() and time.time() < deadline:
            time.sleep(0.25)
        server.server_close()

        if _CodeCatcher.error:
            raise AuthError(f"LinkedIn authorization denied: {_CodeCatcher.error}")
        if not _CodeCatcher.code:
            raise AuthError("Timed out waiting for LinkedIn authorization.")
        if _CodeCatcher.state != state:
            raise AuthError("OAuth state mismatch — possible CSRF, aborting.")

        return self._exchange_code(_CodeCatcher.code, verifier)

    def _exchange_code(self, code: str, verifier: str) -> tuple[str, float]:
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": self._cfg.redirect_uri,
            "client_id": self._cfg.client_id,
            "code_verifier": verifier,
        }
        if self._cfg.client_secret:
            data["client_secret"] = self._cfg.client_secret
        resp = httpx.post(TOKEN_URL, data=data, timeout=30)
        if resp.status_code != 200:
            raise AuthError(f"Token exchange failed: {resp.status_code} {resp.text}")
        payload = resp.json()
        token = payload["access_token"]
        expires_at = time.time() + float(payload.get("expires_in", 60 * 60 * 24 * 60))
        return token, expires_at

    # -- token cache ---------------------------------------------------------
    def _load_cache(self) -> tuple[str, float] | None:
        path = self._cfg.token_cache
        try:
            data = json.loads(path.read_text())
            return data["access_token"], float(data["expires_at"])
        except (OSError, KeyError, ValueError):
            return None

    def _save_cache(self, token: str, expires_at: float) -> None:
        path = self._cfg.token_cache
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(json.dumps({"access_token": token, "expires_at": expires_at}))
            os.chmod(path, 0o600)
        except OSError:
            # Caching is best-effort; a failure here must not break the flow.
            pass
