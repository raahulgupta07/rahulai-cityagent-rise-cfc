"""
Settings routes — /settings prefix.

GET  /settings            → system overview: fabric, schedule, econ, brand
POST /settings/reconnect  → stub for Fabric credential refresh
GET  /settings/audit      → recent audit_log entries (admin only)
"""
from __future__ import annotations
import csv, logging, os, pathlib
from fastapi import APIRouter, Depends
from deps.auth import current_user, require_role
from deps.audit import list_events, record_event
from services.scheduler import get_status as scheduler_status

router = APIRouter(prefix="/settings", tags=["settings"])
log    = logging.getLogger(__name__)

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent


# ── helpers ───────────────────────────────────────────────────────────────────

def _fabric_connected() -> bool:
    """Light probe: all four required env vars present (avoids a real network call)."""
    return all(
        os.getenv(k)
        for k in ("FABRIC_SERVER", "FABRIC_DATABASE", "FABRIC_USER", "FABRIC_PASSWORD")
    )


def _econ_status() -> dict:
    """
    Read data/product_econ.csv and report whether GM is uniform (all rows == same value)
    or has real per-product variation.  Uniform = still using demo stubs.
    """
    path = ROOT / "data" / "product_econ.csv"
    if not path.exists():
        return {"found": False, "row_count": 0, "gm_uniform": None, "warn": True,
                "message": "product_econ.csv not found — economics not configured"}
    try:
        rows: list[dict] = []
        with open(path, newline="") as f:
            rows = list(csv.DictReader(f))
        if not rows:
            return {"found": True, "row_count": 0, "gm_uniform": None, "warn": True,
                    "message": "product_econ.csv is empty"}
        gm_values = set()
        for r in rows:
            v = r.get("gm", "")
            if v.strip():
                try:
                    gm_values.add(round(float(v), 4))
                except ValueError:
                    pass
        uniform = len(gm_values) <= 1
        warn    = uniform  # uniform = still demo stubs, warn the user
        msg     = (
            "All products share the same GM — likely demo defaults. "
            "Edit data/product_econ.csv with real per-product margin & shelf-life."
            if uniform else
            "Per-product economics loaded. Newsvendor orders will reflect real margins."
        )
        return {
            "found":      True,
            "row_count":  len(rows),
            "gm_uniform": uniform,
            "gm_values":  sorted(gm_values),
            "warn":       warn,
            "message":    msg,
        }
    except Exception as exc:
        log.warning("econ_status read failed: %s", exc)
        return {"found": True, "row_count": None, "gm_uniform": None, "warn": True,
                "message": f"Could not read economics file: {exc}"}


def _schedule_summary() -> dict:
    """Compact schedule summary for the settings overview."""
    jobs = scheduler_status()
    any_enabled = any(j["enabled"] for j in jobs)
    return {
        "any_enabled":  any_enabled,
        "job_count":    len(jobs),
        "enabled_jobs": [j["label"] for j in jobs if j["enabled"]],
    }


# ── routes ────────────────────────────────────────────────────────────────────

@router.get("")
def get_settings(user: dict = Depends(current_user)):
    """Return system overview.  All authenticated roles can view."""
    return {
        "brand":              "City Agent RISE",
        "version":            "1.0.0",
        "auth_mode":          "dev-bypass" if os.getenv("AUTH_DISABLED") == "1" else "token",
        "fabric_connected":   _fabric_connected(),
        "fabric_server":      os.getenv("FABRIC_SERVER", "(not set)"),
        "econ":               _econ_status(),
        "schedule":           _schedule_summary(),
        "current_user":       user,
    }


@router.post("/reconnect")
def reconnect_fabric(user: dict = Depends(require_role("admin"))):
    """
    Stub: trigger a Fabric connectivity test and refresh any cached connections.
    In production, this would re-run src/extract.py with fresh credentials or
    rotate the FABRIC_PASSWORD from a secrets manager.
    """
    connected = _fabric_connected()
    record_event(user["actor"], "fabric_reconnect", "stub")
    return {
        "ok":      connected,
        "message": "Credentials present — real reconnect requires container restart with updated .env"
                   if connected else
                   "Fabric credentials missing from environment. Check .env file.",
    }


@router.get("/audit")
def get_audit(limit: int = 50, user: dict = Depends(require_role("admin"))):
    """Return recent audit_log entries. Admin only."""
    return {"events": list_events(limit=limit)}


@router.get("/sso")
def get_sso(user: dict = Depends(require_role("admin"))):
    """SSO / OIDC (Keycloak) status. Config is env-driven — this reports it + tests discovery.
    No secret values are returned. Admin only."""
    from deps import oidc
    st = oidc.status()
    st["redirect_uri_hint"] = st.get("redirect_uri") or "<ORIGIN>/api/auth/sso/callback"
    st["env_keys"] = ["OIDC_ENABLED", "OIDC_ISSUER", "OIDC_CLIENT_ID", "OIDC_CLIENT_SECRET",
                      "OIDC_REDIRECT_URI", "OIDC_ADMIN_GROUP", "OIDC_DEFAULT_ROLE"]
    return st


@router.get("/security")
def get_security(user: dict = Depends(require_role("admin"))):
    """Security posture — flags insecure prod config (default secret / auth off). Admin only."""
    from deps.auth import security_posture
    p = security_posture()
    warnings = []
    if p["is_prod"] and p["insecure_secret"]:
        warnings.append("SECRET_KEY is unset/default — set a strong value.")
    if p["is_prod"] and p["auth_disabled"]:
        warnings.append("AUTH_DISABLED=1 — authentication is OFF.")
    return {**p, "warnings": warnings}
