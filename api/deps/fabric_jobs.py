"""
Fabric notebook job trigger — Phase 2.

Lets the app LAUNCH the Fabric ML notebook (run experiment / promote a version) and
poll its status, via the Fabric REST Job Scheduler API. Same mechanism used to drive
the pipeline headlessly. Auth = AAD ROPC (username/password from .env, MFA off).

Env:
  FABRIC_TENANT_ID, FABRIC_USER, FABRIC_PASSWORD   (creds; shared with deps/fabric.py)
  FABRIC_WORKSPACE_ID   HUB-AI workspace id
  FABRIC_NOTEBOOK_ID    CFC_ML_Pipeline notebook id

Best-effort + flag-gated on USE_FABRIC. Never raises into a request unguarded.
"""
from __future__ import annotations
import logging, os, time
import httpx

log = logging.getLogger(__name__)

_TENANT   = os.getenv("FABRIC_TENANT_ID", "")
_USER     = os.getenv("FABRIC_USER", "")
_PW       = os.getenv("FABRIC_PASSWORD", "")
_WS       = os.getenv("FABRIC_WORKSPACE_ID", "")
_NB       = os.getenv("FABRIC_NOTEBOOK_ID", "")
# Azure CLI public client — allows ROPC (resource-owner password) token flow.
_CLIENT   = "04b07795-8ddb-461a-bbee-02f9e1bf7b46"
_API      = "https://api.fabric.microsoft.com/v1"

# in-memory map: our job_id -> Fabric status URL (Location header)
_jobs: dict[str, str] = {}


def configured() -> bool:
    return bool(_TENANT and _USER and _PW and _WS and _NB)


def _token() -> str:
    r = httpx.post(
        f"https://login.microsoftonline.com/{_TENANT}/oauth2/v2.0/token",
        data={"grant_type": "password", "client_id": _CLIENT,
              "scope": "https://api.fabric.microsoft.com/.default",
              "username": _USER, "password": _PW}, timeout=30)
    r.raise_for_status()
    return r.json()["access_token"]


def run(mode: str, params: dict | None = None) -> dict:
    """Trigger the notebook with MODE=<mode> (+ extra params). Returns {job_id, status_url}."""
    p = {"MODE": {"value": mode, "type": "string"}}
    for k, v in (params or {}).items():
        if v not in (None, ""):
            p[k] = {"value": str(v), "type": "string"}
    r = httpx.post(
        f"{_API}/workspaces/{_WS}/items/{_NB}/jobs/instances?jobType=RunNotebook",
        headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
        json={"executionData": {"parameters": p}}, timeout=60)
    if r.status_code not in (200, 201, 202):
        raise RuntimeError(f"fabric job start {r.status_code}: {r.text[:200]}")
    loc = r.headers.get("Location", "")
    job_id = loc.rstrip("/").split("/")[-1] or f"job-{int(time.time())}"
    _jobs[job_id] = loc
    return {"job_id": job_id, "status_url": loc, "mode": mode}


def schedules() -> list[dict]:
    """List RunNotebook schedules on the notebook (best-effort, [] on failure)."""
    try:
        r = httpx.get(f"{_API}/workspaces/{_WS}/items/{_NB}/jobs/RunNotebook/schedules",
                      headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
        r.raise_for_status()
        out = []
        for s in r.json().get("value", []):
            c = s.get("configuration", {})
            out.append({"id": s.get("id"), "enabled": s.get("enabled"),
                        "type": c.get("type"), "times": c.get("times"),
                        "timezone": c.get("localTimeZoneId")})
        return out
    except Exception:
        return []


def status(job_id: str) -> dict:
    """Poll one job. Returns {status, job_id}. status in NotStarted/InProgress/Completed/Failed/…"""
    loc = _jobs.get(job_id)
    if not loc:
        loc = f"{_API}/workspaces/{_WS}/items/{_NB}/jobs/instances/{job_id}"
    r = httpx.get(loc, headers={"Authorization": f"Bearer {_token()}"}, timeout=30)
    r.raise_for_status()
    j = r.json()
    return {"job_id": job_id, "status": j.get("status"),
            "start": j.get("startTimeUtc"), "end": j.get("endTimeUtc"),
            "failure": (j.get("failureReason") or {}).get("message") if j.get("failureReason") else None}
