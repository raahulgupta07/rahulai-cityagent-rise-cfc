"""
Auth dependency — lightweight HMAC-signed tokens, no heavy libs.

Token format: <role>:<exp_unix>:<hmac_hex>
  role   = one of viewer / ops / finance / admin
  exp    = Unix timestamp (int, UTC seconds)
  hmac   = HMAC-SHA256( "<role>:<exp>", SECRET_KEY ) hex-encoded

Generation (cli helper):
    python3 -c "from deps.auth import make_token; print(make_token('admin', 365))"

Config (env):
    SECRET_KEY     — required in prod, defaults to an insecure dev value
    AUTH_DISABLED  — set to "1" to skip auth entirely (dev only)

Usage in a route:
    from deps.auth import require_role, current_user
    @router.get("/admin-only")
    def admin_only(user=Depends(require_role("admin"))):
        ...
    @router.get("/any-logged-in")
    def any_route(user=Depends(current_user)):
        ...
"""
from __future__ import annotations
import hashlib, hmac, os, time
from functools import lru_cache
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

# ── config ────────────────────────────────────────────────────────────────────

_DEV_SECRET = "cfc-dev-insecure-secret-change-in-prod"
ROLES = {"viewer", "ops", "finance", "admin"}
COOKIE_NAME = "cfc_token"

@lru_cache(maxsize=1)
def _secret() -> bytes:
    return os.getenv("SECRET_KEY", _DEV_SECRET).encode()


# ── credential store (env-backed) ───────────────────────────────────────────────
# Superadmin comes from SUPERADMIN_EMAIL + SUPERADMIN_PASSWORD (role = admin).
# Optional extra accounts via AUTH_USERS = "email:password:role,email:password:role"
# (role ∈ viewer|ops|finance|admin). Passwords are plaintext in env by design.

def _env_users() -> dict[str, dict]:
    """Return {email_lower: {"password": str, "role": str}} from env. Never cached
    (so a container restart with new env is picked up; cheap enough per-login)."""
    users: dict[str, dict] = {}
    sa_email = os.getenv("SUPERADMIN_EMAIL", "").strip()
    sa_pw    = os.getenv("SUPERADMIN_PASSWORD", "")
    if sa_email and sa_pw:
        users[sa_email.lower()] = {"password": sa_pw, "role": "admin"}
    raw = os.getenv("AUTH_USERS", "").strip()
    for entry in raw.split(","):
        entry = entry.strip()
        if not entry:
            continue
        parts = entry.split(":")
        if len(parts) < 2:
            continue
        email, pw = parts[0].strip(), parts[1]
        role = (parts[2].strip() if len(parts) > 2 else "viewer") or "viewer"
        if not email or role not in ROLES:
            continue
        users[email.lower()] = {"password": pw, "role": role}
    return users


def authenticate(email: str, password: str) -> dict | None:
    """Validate email+password against env users. Returns {email, role} or None.
    Constant-time password compare; unknown email still runs a compare to avoid
    a timing oracle on which emails exist."""
    email = (email or "").strip().lower()
    users = _env_users()
    rec = users.get(email)
    reference = rec["password"] if rec else ""
    ok = hmac.compare_digest(reference.encode(), (password or "").encode())
    if rec and ok:
        return {"email": email, "role": rec["role"]}
    return None


def has_credentials_configured() -> bool:
    """True if at least one login account exists in env (superadmin or AUTH_USERS)."""
    return bool(_env_users())


def _auth_disabled() -> bool:
    return os.getenv("AUTH_DISABLED", "0") == "1"


def security_posture() -> dict:
    """Report auth/secret posture. In production, insecure defaults are hard failures."""
    insecure_secret = os.getenv("SECRET_KEY", "").strip() in ("", _DEV_SECRET)
    is_prod = os.getenv("APP_ENV", "").lower() in ("production", "prod")
    auth_off = _auth_disabled()
    return {
        "is_prod": is_prod,
        "insecure_secret": insecure_secret,
        "auth_disabled": auth_off,
        "ok": not (is_prod and (insecure_secret or auth_off)),
    }


# ── token creation ─────────────────────────────────────────────────────────────

def make_token(role: str, days: int = 30, email: str = "") -> str:
    """Create a signed token valid for `days` days, carrying the subject email.
    Format: <role>:<email>:<exp_unix>:<hmac>. Email must contain no ':'.
    Run from CLI to issue tokens (email optional)."""
    if role not in ROLES:
        raise ValueError(f"Unknown role {role!r}. Valid: {ROLES}")
    email = (email or "").replace(":", "")
    exp = int(time.time()) + days * 86400
    msg = f"{role}:{email}:{exp}"
    sig = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    return f"{msg}:{sig}"


def _verify_token(token: str) -> dict:
    """Return {actor, role, email} or raise HTTPException."""
    parts = token.split(":")
    if len(parts) != 4:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    role, email, exp_s, sig = parts
    if role not in ROLES:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Unknown role")
    msg = f"{role}:{email}:{exp_s}"
    expected = hmac.new(_secret(), msg.encode(), hashlib.sha256).hexdigest()
    if not hmac.compare_digest(expected, sig):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid token signature")
    try:
        expired = int(time.time()) > int(exp_s)
    except ValueError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Malformed token")
    if expired:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Token expired")
    return {"actor": f"user:{email or role}", "role": role, "email": email}


# ── FastAPI deps ──────────────────────────────────────────────────────────────

_bearer = HTTPBearer(auto_error=False)


def _extract_token(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> str | None:
    """Try Authorization: Bearer header first, then X-CFC-Token header, then cookie."""
    if creds and creds.credentials:
        return creds.credentials
    h = request.headers.get("X-CFC-Token")
    if h:
        return h
    return request.cookies.get("cfc_token")


def current_user(
    request: Request,
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """FastAPI dependency — returns {actor, role, email}. Bypass when AUTH_DISABLED=1."""
    if _auth_disabled():
        return {"actor": "dev", "role": "admin", "email": "dev@local"}
    token = _extract_token(request, creds)
    if not token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Authentication required")
    return _verify_token(token)


def resolve_identity(request: Request) -> dict | None:
    """Cookie/header identity WITHOUT the AUTH_DISABLED bypass — used by /auth/me so
    the login page is always enforced in the UI even when API auth is relaxed in dev.
    Returns {actor, role, email} or None (never raises)."""
    token = request.cookies.get(COOKIE_NAME) or request.headers.get("X-CFC-Token")
    if not token:
        auth = request.headers.get("Authorization", "")
        if auth.lower().startswith("bearer "):
            token = auth[7:].strip()
    if not token:
        return None
    try:
        return _verify_token(token)
    except HTTPException:
        return None


def require_role(*roles: str):
    """Return a FastAPI dependency that enforces membership in any of `roles`.

    Usage:
        @router.post("/ops-action")
        def action(user=Depends(require_role("ops", "admin"))):
            ...
    """
    allowed = set(roles)

    def _dep(user: dict = Depends(current_user)) -> dict:
        if user["role"] not in allowed:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                f"Role '{user['role']}' not allowed. Required: {allowed}",
            )
        return user

    return _dep
