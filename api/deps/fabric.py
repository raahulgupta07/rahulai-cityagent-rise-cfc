"""
Fabric Lakehouse read layer — Phase 3.

When USE_FABRIC=1, the app reads the ML outputs the Fabric notebook writes
(cfc_backtest_preds / cfc_order_plan / cfc_model_runs / cfc_champion) LIVE from the
LK_CFC_Sales SQL endpoint, instead of local parquet. Sales/models never move — the
app just queries the results tables.

Auth = AAD username/password (ActiveDirectoryPassword) via ODBC Driver 18, same creds
as fabric_user_connector.py (.env: FABRIC_USER / FABRIC_PASSWORD). Endpoint + DB from
.env (FABRIC_SQL_ENDPOINT / FABRIC_SQL_DB). Everything is best-effort + flag-gated:
if disabled or unreachable, callers fall back to the local parquet path.

Requires the Microsoft ODBC driver in the image (api/Dockerfile installs msodbcsql18).
"""
from __future__ import annotations
import logging, os, threading

log = logging.getLogger(__name__)

_ENDPOINT = os.getenv("FABRIC_SQL_ENDPOINT", "")
_DB       = os.getenv("FABRIC_SQL_DB", "LK_CFC_Sales")
_USER     = os.getenv("FABRIC_USER", "")
_PW       = os.getenv("FABRIC_PASSWORD", "")
_SCHEMA   = os.getenv("FABRIC_SCHEMA", "dbo")

_lock = threading.Lock()
_conn = None  # lazily opened, reused


def enabled() -> bool:
    """True if the Fabric read path is turned on and configured."""
    return os.getenv("USE_FABRIC", "0") == "1" and bool(_ENDPOINT and _USER and _PW)


def table(name: str) -> str:
    """Schema-qualified table name (schema-enabled Lakehouse -> dbo.<name>)."""
    return f"{_SCHEMA}.{name}" if _SCHEMA else name


def _connect():
    import pyodbc
    cs = (
        "DRIVER={ODBC Driver 18 for SQL Server};"
        f"SERVER={_ENDPOINT},1433;DATABASE={_DB};"
        f"UID={_USER};PWD={_PW};"
        "Authentication=ActiveDirectoryPassword;"
        "Encrypt=yes;TrustServerCertificate=no;Connection Timeout=30"
    )
    return pyodbc.connect(cs, timeout=30)


def _get_conn():
    global _conn
    with _lock:
        if _conn is not None:
            try:
                _conn.cursor().execute("SELECT 1").fetchone()
                return _conn
            except Exception:
                try: _conn.close()
                except Exception: pass
                _conn = None
        _conn = _connect()
        return _conn


def q(sql: str, params: tuple = ()) -> list[dict]:
    """Run a query against the Fabric SQL endpoint, return list[dict]. Reconnects once on failure."""
    for attempt in (1, 2):
        try:
            cur = _get_conn().cursor()
            cur.execute(sql, params) if params else cur.execute(sql)
            cols = [d[0] for d in cur.description]
            return [dict(zip(cols, row)) for row in cur.fetchall()]
        except Exception as exc:
            global _conn
            with _lock:
                try:
                    if _conn: _conn.close()
                except Exception: pass
                _conn = None
            if attempt == 2:
                log.warning("fabric query failed: %s", exc)
                raise
    return []


def champion() -> dict | None:
    """Live champion {version, wmape, cutoff} from Fabric, or None if off/unavailable.
    Single source of truth so every screen (deploy/versions, learning, workflow, health)
    agrees on which model is live."""
    if not enabled():
        return None
    try:
        ch = q(f"SELECT TOP 1 version FROM {table('cfc_champion')} ORDER BY created DESC")
        if not ch:
            return None
        v = ch[0]["version"]
        mr = q(f"SELECT TOP 1 wmape, cutoff FROM {table('cfc_model_runs')} "
               f"WHERE version = ? ORDER BY created DESC", (v,))
        m = mr[0] if mr else {}
        return {"version": v, "wmape": m.get("wmape"), "cutoff": m.get("cutoff")}
    except Exception:
        return None


def healthcheck() -> tuple[bool, str]:
    if not enabled():
        return True, "fabric read path disabled"
    try:
        q(f"SELECT TOP 1 1 AS ok FROM {table('cfc_champion')}")
        return True, "fabric ok"
    except Exception as exc:
        return False, f"fabric unavailable: {exc}"
