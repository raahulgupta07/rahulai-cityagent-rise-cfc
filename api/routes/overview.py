"""
Overview snapshot — one cached payload for the whole Overview page.

Why: the Overview used to fire ~15 live queries (several hitting Fabric) on every load,
so every visit paid Fabric latency + a cold-connection blank window. Instead we compute
the whole payload ONCE, cache it to a local JSON file, and serve that instantly. The user
pulls fresh numbers on demand via POST /overview/sync ("Sync live" button).

  GET  /overview        -> cached snapshot (computes + caches on first ever call)
  POST /overview/sync   -> recompute from live sources, overwrite cache, return fresh
  GET  /overview/meta   -> {cached_at, exists, age_seconds}

Cache: data/cache/overview.json (durable on the mounted ./data volume; heavy tabular data
stays in parquet — this file is just the small nested KPI/array payload the page renders).
"""
from __future__ import annotations
import json, os, pathlib, tempfile, threading
from datetime import datetime, timezone
from fastapi import APIRouter, Depends

from deps.auth import current_user, require_role

router = APIRouter(prefix="/overview", tags=["overview"])

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
CACHE = ROOT / "data" / "cache" / "overview.json"

# Compute is ~30s and hits Fabric via pyodbc (NOT thread-safe). Serialize it so only ONE
# compute ever runs at a time — otherwise two threads share the Fabric connection → SIGSEGV.
_LOCK = threading.Lock()


def _json(v):
    """Make route return values JSON-safe (pydantic models → dict)."""
    if hasattr(v, "model_dump"):
        return v.model_dump()
    if isinstance(v, list):
        return [_json(x) for x in v]
    return v


def _compute() -> dict:
    """Gather the full Overview payload by calling each slice's function directly.
    Every source is isolated: one failure yields null/[] for that key, not a dead page."""
    from routes import (results, accuracy, deploy, order, data, sources,
                        insights, workflow, learning, demand, pipeline)

    def safe(fn, default=None):
        try:
            return _json(fn())
        except Exception:
            return default

    # NB: functions with `= Query(...)` defaults MUST be called with explicit args here —
    # direct (non-HTTP) calls don't get FastAPI's Query→value resolution.
    return {
        "network":          safe(lambda: demand.network(None), []),
        "dates":            safe(demand.dates, []),
        "results":          safe(results.summary),
        "learning":         safe(learning.status),
        "accuracy_summary": safe(accuracy.summary),
        "accuracy_daily":   safe(lambda: accuracy.daily(30)),
        "versions":         safe(deploy.versions),
        "health":           safe(deploy.health),
        "dial":             safe(lambda: order.dial(None)),
        "gaps":             safe(data.gaps, []),
        "econ":             safe(insights.economics_impact),
        "workflow":         safe(workflow.status),
        "jobs":             safe(lambda: pipeline.list_jobs(6), []),
        "sources":          safe(sources.sources),
    }


def _write_cache(payload: dict) -> str:
    CACHE.parent.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
    doc = {"cached_at": ts, "data": payload}
    # atomic write
    fd, tmp = tempfile.mkstemp(dir=str(CACHE.parent), suffix=".tmp")
    with os.fdopen(fd, "w") as f:
        json.dump(doc, f)
    os.replace(tmp, CACHE)
    return ts


def _read_cache() -> dict | None:
    if not CACHE.exists():
        return None
    try:
        return json.loads(CACHE.read_text())
    except Exception:
        return None


def _compute_and_cache() -> str | None:
    """Compute + write cache under the single-run lock. Skips if a compute is already
    running (returns None). Serialization prevents concurrent pyodbc → SIGSEGV."""
    if not _LOCK.acquire(blocking=False):
        return None
    try:
        return _write_cache(_compute())
    finally:
        _LOCK.release()


def _bg_warm() -> None:
    """Kick a background compute if one isn't already running."""
    if _LOCK.locked():
        return
    threading.Thread(target=_compute_and_cache, daemon=True).start()


def warm_on_start() -> None:
    """Called from app startup — build the cache in the background so the first page load
    is instant (and prime the Fabric connection in that same single thread)."""
    _bg_warm()


def _age(cached_at) -> float | None:
    try:
        return (datetime.now(timezone.utc) - datetime.fromisoformat(cached_at)).total_seconds()
    except Exception:
        return None


@router.get("")
def get_overview(user: dict = Depends(current_user)):
    """Instant cached snapshot. If the cache doesn't exist yet, kick a background build and
    return building=True (never blocks the request on the ~30s compute)."""
    doc = _read_cache()
    if doc is None:
        _bg_warm()
        return {"cached_at": None, "age_seconds": None, "live": False,
                "building": True, "data": {}}
    return {"cached_at": doc.get("cached_at"), "age_seconds": _age(doc.get("cached_at")),
            "live": False, "building": _LOCK.locked(), "data": doc.get("data", {})}


@router.post("/sync")
def sync_overview(user: dict = Depends(require_role("ops", "admin"))):
    """Pull fresh from live sources (Fabric + local), overwrite the cache, return it.
    Blocks up to ~90s on the single-run lock; if a build is already running, returns the
    current cache with building=True instead of double-computing."""
    if not _LOCK.acquire(blocking=True, timeout=90):
        doc = _read_cache() or {"cached_at": None, "data": {}}
        return {"cached_at": doc.get("cached_at"), "age_seconds": _age(doc.get("cached_at")),
                "live": False, "building": True, "data": doc.get("data", {})}
    try:
        payload = _compute()
        ts = _write_cache(payload)
    finally:
        _LOCK.release()
    return {"cached_at": ts, "age_seconds": 0, "live": True, "building": False, "data": payload}


@router.get("/meta")
def overview_meta(user: dict = Depends(current_user)):
    doc = _read_cache()
    if not doc:
        return {"exists": False, "cached_at": None, "age_seconds": None}
    age = None
    try:
        age = (datetime.now(timezone.utc)
               - datetime.fromisoformat(doc["cached_at"])).total_seconds()
    except Exception:
        pass
    return {"exists": True, "cached_at": doc.get("cached_at"), "age_seconds": age}
