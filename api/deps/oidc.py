"""
OIDC / Keycloak SSO helper — env-driven, no secrets in the UI/DB.

Authorization-code flow with a confidential client. The app redirects to the IdP, the IdP
returns a code, we exchange it back-channel (over TLS, so the tokens are trustworthy without
local JWKS/JWT verification) and read the user's email + groups/roles from the userinfo
endpoint. We then issue our OWN signed cfc_token cookie (deps/auth.make_token) — the rest of
the app is unchanged.

Config (env):
  OIDC_ENABLED=1
  OIDC_PROVIDER_NAME=Keycloak            # button label ("Continue with Keycloak")
  OIDC_ISSUER=https://iam.example.com/realms/city-group
  OIDC_CLIENT_ID=city-agent-rise
  OIDC_CLIENT_SECRET=...
  OIDC_REDIRECT_URI=https://rise.example.com/api/auth/sso/callback   # must match Keycloak
  OIDC_SCOPES=openid email profile
  OIDC_ROLE_CLAIM=groups                 # claim holding group/role names
  OIDC_ADMIN_GROUP=rise-admin            # membership → role admin
  OIDC_OPS_GROUP=rise-ops
  OIDC_FINANCE_GROUP=rise-finance
  OIDC_DEFAULT_ROLE=viewer               # any other authenticated SSO user
"""
from __future__ import annotations
import os, threading, time
from typing import Any

_disc_cache: dict[str, Any] = {}
_disc_at: float = 0.0
_lock = threading.Lock()


def enabled() -> bool:
    return os.getenv("OIDC_ENABLED", "0") == "1" and bool(os.getenv("OIDC_ISSUER"))


def provider_name() -> str:
    return os.getenv("OIDC_PROVIDER_NAME", "SSO")


def _issuer() -> str:
    return os.getenv("OIDC_ISSUER", "").rstrip("/")


def redirect_uri(default: str = "") -> str:
    return os.getenv("OIDC_REDIRECT_URI", default)


def scopes() -> str:
    return os.getenv("OIDC_SCOPES", "openid email profile")


def discovery(force: bool = False) -> dict:
    """Fetch + cache the IdP's .well-known/openid-configuration (10 min TTL)."""
    global _disc_cache, _disc_at
    with _lock:
        if not force and _disc_cache and (time.time() - _disc_at) < 600:
            return _disc_cache
        import httpx
        url = _issuer() + "/.well-known/openid-configuration"
        r = httpx.get(url, timeout=10, headers={"User-Agent": "CityAgentRISE/1.0"})
        r.raise_for_status()
        _disc_cache = r.json()
        _disc_at = time.time()
        return _disc_cache


def build_auth_url(state: str, redirect: str) -> str:
    from urllib.parse import urlencode
    d = discovery()
    q = urlencode({
        "response_type": "code",
        "client_id": os.getenv("OIDC_CLIENT_ID", ""),
        "redirect_uri": redirect,
        "scope": scopes(),
        "state": state,
    })
    return f"{d['authorization_endpoint']}?{q}"


def exchange(code: str, redirect: str) -> dict:
    """Trade the auth code for tokens, then read userinfo. Returns the userinfo claims."""
    import httpx
    d = discovery()
    tok = httpx.post(d["token_endpoint"], timeout=15,
                     headers={"User-Agent": "CityAgentRISE/1.0"},
                     data={
                         "grant_type": "authorization_code",
                         "code": code,
                         "redirect_uri": redirect,
                         "client_id": os.getenv("OIDC_CLIENT_ID", ""),
                         "client_secret": os.getenv("OIDC_CLIENT_SECRET", ""),
                     })
    tok.raise_for_status()
    access = tok.json().get("access_token")
    if not access:
        raise RuntimeError("no access_token from IdP")
    ui = httpx.get(d["userinfo_endpoint"], timeout=15,
                   headers={"Authorization": f"Bearer {access}", "User-Agent": "CityAgentRISE/1.0"})
    ui.raise_for_status()
    return ui.json()


def _roles_from(claims: dict) -> list[str]:
    """Collect group/role names from the common Keycloak places, normalised (strip '/')."""
    out: list[str] = []
    claim = os.getenv("OIDC_ROLE_CLAIM", "groups")
    v = claims.get(claim)
    if isinstance(v, str):
        out += v.split()
    elif isinstance(v, list):
        out += v
    ra = (claims.get("realm_access") or {}).get("roles")
    if isinstance(ra, list):
        out += ra
    if isinstance(claims.get("groups"), list):
        out += claims["groups"]
    return [str(x).lstrip("/").strip() for x in out if x]


def map_role(claims: dict) -> str:
    roles = set(_roles_from(claims))
    for env_key, app_role in [("OIDC_ADMIN_GROUP", "admin"),
                              ("OIDC_OPS_GROUP", "ops"),
                              ("OIDC_FINANCE_GROUP", "finance")]:
        g = os.getenv(env_key, "").strip()
        if g and g in roles:
            return app_role
    return os.getenv("OIDC_DEFAULT_ROLE", "viewer")


def email_of(claims: dict) -> str:
    return (claims.get("email") or claims.get("preferred_username")
            or claims.get("sub") or "").strip()


def config_public() -> dict:
    """Minimal, safe config the login page can read (no secrets)."""
    return {"enabled": enabled(), "provider": provider_name(),
            "login_url": "/api/auth/sso/login"}


def status() -> dict:
    """Admin-facing SSO status for the Settings screen (no secret values)."""
    s = {
        "enabled": enabled(),
        "provider": provider_name(),
        "issuer": _issuer() or None,
        "client_id": os.getenv("OIDC_CLIENT_ID") or None,
        "redirect_uri": redirect_uri() or None,
        "default_role": os.getenv("OIDC_DEFAULT_ROLE", "viewer"),
        "admin_group": os.getenv("OIDC_ADMIN_GROUP") or None,
        "discovery_ok": None,
        "error": None,
    }
    if enabled():
        try:
            d = discovery(force=True)
            s["discovery_ok"] = bool(d.get("authorization_endpoint"))
        except Exception as exc:
            s["discovery_ok"] = False
            s["error"] = str(exc)[:200]
    return s
