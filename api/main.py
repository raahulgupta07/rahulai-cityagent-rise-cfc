"""
CFC Forecaster API — FastAPI entrypoint.

main.py is STABLE: it never names a feature. Routers self-register
(see routes/__init__.py), so feature slices add files without touching this one.

Production posture (APP_ENV=production):
- Boot ABORTS if SECRET_KEY is unset/default or AUTH_DISABLED=1 (fail-closed, not just a log).
- CORS origins come from ALLOWED_ORIGINS (comma-separated); no localhost fallback in prod.
Dev posture stays permissive.
"""
from __future__ import annotations
import logging, os
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

from routes import all_routers

logging.basicConfig(
    level=os.getenv("LOG_LEVEL", "INFO"),
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
)
log = logging.getLogger("cfc")

app = FastAPI(title="CFC Forecaster API", version="1.0.0")


@app.on_event("startup")
def _check_security():
    from deps.auth import security_posture
    p = security_posture()
    if p["is_prod"]:
        problems = []
        if p["insecure_secret"]:
            problems.append("SECRET_KEY is unset/default — set a strong SECRET_KEY")
        if p["auth_disabled"]:
            problems.append("AUTH_DISABLED=1 — auth is OFF, set AUTH_DISABLED=0")
        if problems:
            # Fail closed: refuse to start an insecure production process.
            raise RuntimeError("SECURITY: refusing to start in production — " + "; ".join(problems))
        log.info("cfc api starting (production posture; security checks passed)")
    else:
        log.info("cfc api starting (dev posture; set APP_ENV=production to enforce security)")


# ── CORS ────────────────────────────────────────────────────────────────────
def _cors_origins() -> list[str]:
    raw = os.getenv("ALLOWED_ORIGINS", "").strip()
    if raw:
        return [o.strip() for o in raw.split(",") if o.strip()]
    if os.getenv("APP_ENV", "dev").lower().startswith("prod"):
        return []  # prod with no explicit origins = deny all cross-origin
    return ["http://localhost:5173", "http://localhost:3000",
            "http://localhost:8812", "http://127.0.0.1:8812"]


app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins(),
    allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)


# ── global error handler (no stack leak to clients) ─────────────────────────
@app.exception_handler(Exception)
async def _unhandled(request: Request, exc: Exception):
    log.exception("unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(status_code=500, content={"detail": "internal error"})


# ── health (deep: verifies the analytics store is reachable) ────────────────
@app.get("/health")
@app.get("/api/health")
def health():
    # Process health: if the API is up and serving, ok=true. Whether the LOCAL analytics
    # parquet is present is a SEPARATE signal (a fresh/Fabric-only deploy has no local
    # parquet yet — that's normal, not unhealthy).
    analytics_ready, detail = True, "ok"
    try:
        from deps.duck import healthcheck as _duck_health  # optional, if present
        analytics_ready, detail = _duck_health()
    except Exception:
        analytics_ready = False
        detail = "analytics helper unavailable"
    return {"ok": True, "service": "cfc-forecaster-api",
            "analytics_ready": analytics_ready, "detail": detail}


# Mount every router TWICE: at root (/auth, /overview, …) AND under /api (/api/auth, …).
# The SPA calls /api/*; a front proxy that strips /api hits the root mount, one that does
# NOT strip hits the /api mount — so login works regardless of proxy config. Bulletproofs
# the whole "/api prefix" class of deploy errors.
for r in all_routers():
    app.include_router(r)
    app.include_router(r, prefix="/api")

# Warm the Overview snapshot cache in a SINGLE background thread at startup. This computes
# the whole page payload once (and primes the Fabric ODBC connection in that same thread) so
# the first user load is instant. One thread only — concurrent pyodbc access → SIGSEGV.
@app.on_event("startup")
def _warm_overview():
    try:
        from routes import overview
        overview.warm_on_start()
    except Exception:
        pass


# scheduler (jobs default-disabled; see services/scheduler.py)
from services.scheduler import start as _sched_start, stop as _sched_stop
app.on_event("startup")(_sched_start)
app.on_event("shutdown")(_sched_stop)
