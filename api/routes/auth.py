"""
Auth routes — /auth prefix. Env-backed superadmin + optional multi-user login.

POST /auth/login   {email, password, remember?} → set httponly cookie, return {ok, email, role}
POST /auth/logout  → clear cookie
GET  /auth/me      → {authenticated, email?, role?} (cookie-based, ignores AUTH_DISABLED)

Credentials live in env (see deps/auth._env_users): SUPERADMIN_EMAIL/PASSWORD (role admin)
plus optional AUTH_USERS. On success a signed HMAC token (deps/auth.make_token) is stored in
an httponly cookie so the browser JS never sees it; the SPA gates on GET /auth/me.
"""
from __future__ import annotations
import os, secrets
from fastapi import APIRouter, Request, Response, HTTPException, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from deps.auth import (
    authenticate, make_token, resolve_identity,
    has_credentials_configured, COOKIE_NAME,
)
from deps.audit import record_event
from deps import oidc

router = APIRouter(prefix="/auth", tags=["auth"])
_STATE_COOKIE = "cfc_oidc_state"

# session length (days): short by default, longer when "remember me" is ticked
SESSION_DAYS  = int(os.getenv("SESSION_DAYS", "1"))
REMEMBER_DAYS = int(os.getenv("REMEMBER_DAYS", "30"))


class LoginBody(BaseModel):
    email: str
    password: str
    remember: bool = False


def _is_prod() -> bool:
    return os.getenv("APP_ENV", "").lower().startswith("prod")


@router.post("/login")
def login(body: LoginBody, request: Request, response: Response):
    if not has_credentials_configured():
        # Fail loud: no way to log in until env creds are set.
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE,
                            "No login accounts configured. Set SUPERADMIN_EMAIL + SUPERADMIN_PASSWORD.")
    ident = authenticate(body.email, body.password)
    if not ident:
        record_event(f"user:{(body.email or '').strip().lower()}", "login_failed", "bad credentials")
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")

    days  = REMEMBER_DAYS if body.remember else SESSION_DAYS
    token = make_token(ident["role"], days=days, email=ident["email"])
    response.set_cookie(
        key=COOKIE_NAME, value=token,
        max_age=days * 86400,
        httponly=True, samesite="lax", secure=_is_prod(), path="/",
    )
    record_event(f"user:{ident['email']}", "login", ident["role"])
    return {"ok": True, "email": ident["email"], "role": ident["role"]}


@router.post("/logout")
def logout(request: Request, response: Response):
    ident = resolve_identity(request)
    response.delete_cookie(key=COOKIE_NAME, path="/")
    if ident:
        record_event(ident["actor"], "logout", ident.get("email", ""))
    return {"ok": True}


@router.get("/me")
def me(request: Request):
    ident = resolve_identity(request)
    if not ident:
        return {"authenticated": False, "configured": has_credentials_configured(),
                "sso": oidc.config_public()}
    return {"authenticated": True, "email": ident.get("email", ""), "role": ident["role"]}


# ── OIDC / Keycloak SSO ─────────────────────────────────────────────────────────

def _redirect_uri(request: Request) -> str:
    """Configured redirect URI, else derived from the incoming request."""
    env = oidc.redirect_uri()
    if env:
        return env
    base = str(request.base_url).rstrip("/")
    return f"{base}/auth/sso/callback"


@router.get("/sso/config")
def sso_config():
    """Public: lets the login page show/label the SSO button."""
    return oidc.config_public()


@router.get("/sso/login")
def sso_login(request: Request):
    """Kick off the OIDC auth-code flow: set a state cookie, redirect to the IdP."""
    if not oidc.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SSO not configured")
    state = secrets.token_urlsafe(24)
    try:
        url = oidc.build_auth_url(state, _redirect_uri(request))
    except Exception as exc:
        record_event("sso", "sso_discovery_failed", str(exc)[:120])
        return RedirectResponse("/login?sso_error=discovery", status_code=303)
    resp = RedirectResponse(url, status_code=303)
    resp.set_cookie(_STATE_COOKIE, state, max_age=300, httponly=True,
                    samesite="lax", secure=_is_prod(), path="/")
    return resp


@router.get("/sso/callback")
def sso_callback(request: Request, code: str = "", state: str = ""):
    """IdP returns here with a code. Validate state, exchange, map role, issue our cookie."""
    if not oidc.enabled():
        raise HTTPException(status.HTTP_404_NOT_FOUND, "SSO not configured")
    saved = request.cookies.get(_STATE_COOKIE)
    if not code or not state or not saved or not secrets.compare_digest(state, saved):
        return RedirectResponse("/login?sso_error=state", status_code=303)
    try:
        claims = oidc.exchange(code, _redirect_uri(request))
        email = oidc.email_of(claims)
        role = oidc.map_role(claims)
        if not email:
            raise RuntimeError("no email in userinfo")
    except Exception as exc:
        record_event("sso", "sso_exchange_failed", str(exc)[:120])
        return RedirectResponse("/login?sso_error=exchange", status_code=303)

    token = make_token(role, days=SESSION_DAYS, email=email)
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie(COOKIE_NAME, token, max_age=SESSION_DAYS * 86400,
                    httponly=True, samesite="lax", secure=_is_prod(), path="/")
    resp.delete_cookie(_STATE_COOKIE, path="/")
    record_event(f"user:{email}", "sso_login", role)
    return resp
