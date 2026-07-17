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
import logging, os, pathlib
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException as StarletteHTTPException

from routes import all_routers

# Single-container mode (OpenWebUI-style): if the built SPA is baked in (WEB_DIST set +
# present), this ONE process serves the UI at / and the API at /api — no separate web
# container, no reverse proxy, no /api-strip config. Everything on one port.
WEB_DIST = pathlib.Path(os.getenv("WEB_DIST", "")) if os.getenv("WEB_DIST") else None
SERVE_SPA = bool(WEB_DIST and (WEB_DIST / "index.html").exists())

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


# ── gzip (BIG win for remote users: JSON + JS bundle compress ~70-85%) ───────
# MUST NOT compress SSE: EventSource needs each event flushed as-is — gzip
# buffering breaks/starves the live streams (pipeline log, experiment run).
from starlette.middleware.gzip import GZipMiddleware


class _GZipNoSSE(GZipMiddleware):
    async def __call__(self, scope, receive, send):
        if scope["type"] == "http":
            accept = ""
            for k, v in scope.get("headers", []):
                if k == b"accept":
                    accept = v.decode("latin-1")
                    break
            if "text/event-stream" in accept:
                await self.app(scope, receive, send)   # bypass gzip for SSE
                return
        await super().__call__(scope, receive, send)


app.add_middleware(_GZipNoSSE, minimum_size=1024)


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


# API mounting:
#  - Always under /api (/api/auth, /api/overview, …) — what the SPA calls.
#  - ALSO at root (/auth, …) ONLY in multi-container mode, so a proxy that strips /api still
#    works. In single-container mode the root is reserved for the SPA, so we skip the root
#    mount (avoids /accuracy, /data, … API routes shadowing the web pages of the same name).
#  - SECURITY: every router except /auth gets a login gate (current_user). Login/logout/me/SSO
#    must stay reachable pre-auth; everything else requires a valid cfc_token. Individual
#    routes still layer require_role(...) on top for mutating/heavy actions.
from fastapi import Depends as _Depends
from deps.auth import current_user as _current_user

_OPEN_PREFIXES = {"/auth"}
for r in all_routers():
    _deps = [] if r.prefix in _OPEN_PREFIXES else [_Depends(_current_user)]
    app.include_router(r, prefix="/api", dependencies=_deps)
    if not SERVE_SPA:
        app.include_router(r, dependencies=_deps)

# ONE startup background thread (pyodbc is not thread-safe → never run Fabric concurrently):
#   1. hydrate local serving parquet from Fabric (so a fresh server needs no shipped data)
#   2. rebuild the DuckDB views now that the parquet exists
#   3. warm the Overview snapshot cache
@app.on_event("startup")
def _boot_background():
    import threading

    def _work():
        try:
            from deps.hydrate import hydrate_from_fabric
            hydrate_from_fabric()
        except Exception:
            log.warning("startup hydrate skipped", exc_info=False)
        try:
            from deps import duck, order_views
            duck.reset()                # close + rebuild DuckDB views with the new parquet
            order_views._registered = False
        except Exception:
            pass
        try:
            from routes import overview
            overview._compute_and_cache()
        except Exception:
            pass

    threading.Thread(target=_work, daemon=True).start()


# scheduler (jobs default-disabled; see services/scheduler.py)
from services.scheduler import start as _sched_start, stop as _sched_stop
app.on_event("startup")(_sched_start)
app.on_event("shutdown")(_sched_stop)


# ── single-container: serve the built SPA at / (must be LAST — catches all non-API paths) ──
if SERVE_SPA:
    class _SPAStatic(StaticFiles):
        """Serve static assets; fall back to index.html for client-side routes (SPA).

        EXCEPT /api/*: an unknown/mistyped API path must stay a 404 — returning the SPA
        shell (200 HTML) to an API client makes JSON.parse fail confusingly downstream.
        """
        async def get_response(self, path, scope):
            try:
                resp = await super().get_response(path, scope)
            except StarletteHTTPException as exc:
                if exc.status_code == 404 and not (path == "api" or path.startswith("api/")):
                    resp = await super().get_response("index.html", scope)
                    resp.headers["Cache-Control"] = "no-cache"   # shell must revalidate on deploy
                    return resp
                raise
            # SvelteKit emits content-hashed files under _app/immutable/ — safe to cache
            # forever; repeat visits skip re-downloading the whole JS/CSS bundle.
            if path.startswith("_app/immutable/"):
                resp.headers["Cache-Control"] = "public, max-age=31536000, immutable"
            elif path in ("index.html", "") or path.endswith(".html"):
                resp.headers["Cache-Control"] = "no-cache"
            return resp

    app.mount("/", _SPAStatic(directory=str(WEB_DIST), html=True), name="spa")
    log.info("serving bundled SPA from %s (single-container mode)", WEB_DIST)
