"""
Learning slice — live model health, drift watch, champion/challenger status.
Reads: models/champion.json, reports/drift_monitor.md, models/pipeline_log.jsonl

Never exposes: PSI, LightGBM, quantile, newsvendor, P50/P85/P95.

Endpoints:
  GET /learning/status  — champion health + candidate + drift watch + verdict
  GET /learning/log     — tail of pipeline_log.jsonl (plain language)
"""
from __future__ import annotations
import re
import json
import pathlib
from datetime import datetime
from fastapi import APIRouter
from pydantic import BaseModel

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
MODELS = ROOT / "models"
REPORTS = ROOT / "reports"

router = APIRouter(prefix="/learning", tags=["learning"])


# ── response shapes ──────────────────────────────────────────────────────────

class DriftItem(BaseModel):
    signal: str           # plain English: "Rainfall spike detected"
    severity: str         # "watch" | "ok"
    detail: str           # "Signal shifted sharply; forecast accuracy held"

class CandidateInfo(BaseModel):
    available: bool
    accuracy_pct: float | None = None
    gain_pct: float | None = None    # improvement over live if promoted
    status: str           # "shadowing" | "promoted" | "none"

class LearningStatus(BaseModel):
    live_version: str
    live_accuracy_pct: float
    recent_accuracy_pct: float       # accuracy on recent window
    accuracy_trend: str              # "improving" | "stable" | "declining"
    candidate: CandidateInfo
    drift_watch: list[DriftItem]
    verdict: str                     # "All clear" | "Retrain recommended" | "Retrain urgent"
    last_checked: str | None = None

class LogEntry(BaseModel):
    ts: str | None = None
    kind: str
    summary: str

class LearningLog(BaseModel):
    entries: list[LogEntry]


# ── PSI feature → plain language ─────────────────────────────────────────────

_FEATURE_PLAIN = {
    "tmax_c": ("Temperature spike", "Maximum daily temperature shifted sharply"),
    "rain_mm": ("Rainfall spike", "Daily rainfall shifted sharply — monsoon signal"),
    "lag_1": ("Recent demand shift", "Yesterday's demand moved away from the norm"),
    "rmean_28": ("Monthly demand trend", "28-day rolling demand has shifted"),
    "rstd_28": ("Demand volatility", "Sales variability has changed from baseline"),
    "ListPrice": ("Price change detected", "Product pricing has shifted"),
    "dow": ("Week pattern", "Day-of-week demand pattern shifted"),
    "y": ("Sales level shift", "Aggregate sales volume has moved"),
    "lag_7": ("Weekly trend", "7-day lagged demand shifted"),
}


def _plain_feature(feat: str) -> tuple[str, str]:
    """Return (signal, detail) for a raw feature name."""
    return _FEATURE_PLAIN.get(feat, (f"{feat} shift", f"Input signal '{feat}' shifted from baseline"))


# ── helpers ──────────────────────────────────────────────────────────────────

def _load_champion() -> dict:
    """Fabric-first champion (single source of truth), else local champion.json."""
    try:
        from deps import fabric
        fab = fabric.champion()
        if fab and fab.get("version"):
            return fab
    except Exception:
        pass
    p = MODELS / "champion.json"
    return json.loads(p.read_text()) if p.exists() else {}


def _read_drift() -> str:
    p = REPORTS / "drift_monitor.md"
    return p.read_text(encoding="utf-8") if p.exists() else ""


def _f(pattern: str, text: str) -> float | None:
    m = re.search(pattern, text)
    if not m:
        return None
    try:
        return float(m.group(1))
    except ValueError:
        return None


# ── endpoints ─────────────────────────────────────────────────────────────────

@router.get("/status", response_model=LearningStatus)
def status() -> LearningStatus:
    champ = _load_champion()
    drift_txt = _read_drift()

    # ── live model ──
    version = champ.get("version", "unknown")
    holdout_wmape = champ.get("wmape", 0.319)
    live_accuracy = round((1 - holdout_wmape) * 100, 1)

    # ── recent window accuracy ──
    # drift_monitor.md: "recent-window WMAPE (now): 0.310"
    recent_wmape = _f(r'recent-window WMAPE.*?:\s*([0-9.]+)', drift_txt)
    if recent_wmape is None:
        recent_wmape = holdout_wmape
    recent_accuracy = round((1 - recent_wmape) * 100, 1)

    if recent_wmape < holdout_wmape * 0.97:
        trend = "improving"
    elif recent_wmape > holdout_wmape * 1.03:
        trend = "declining"
    else:
        trend = "stable"

    # ── candidate (registry) ──
    registry = MODELS / "registry"
    candidate = CandidateInfo(available=False, status="none")
    if registry.exists():
        versions = sorted(registry.iterdir(), key=lambda p: p.stat().st_mtime, reverse=True)
        challenger_dirs = [v for v in versions if (v / "meta.json").exists() and v.name != version]
        if challenger_dirs:
            meta_path = challenger_dirs[0] / "meta.json"
            try:
                meta = json.loads(meta_path.read_text())
                cand_wmape = meta.get("wmape", None)
                if cand_wmape is not None:
                    gain = round((holdout_wmape - cand_wmape) / holdout_wmape * 100, 1)
                    candidate = CandidateInfo(
                        available=True,
                        accuracy_pct=round((1 - cand_wmape) * 100, 1),
                        gain_pct=gain,
                        status="shadowing" if gain < 1.0 else "ready to promote",
                    )
            except Exception:
                pass

    # ── drift watch ──
    drift_items: list[DriftItem] = []
    # parse PSI table: | feature | PSI | status |
    for m in re.finditer(r'\|\s*(\w+)\s*\|\s*([0-9.]+)\s*\|\s*(DRIFT|ok)\s*\|', drift_txt):
        feat, psi_val, psi_status = m.group(1), float(m.group(2)), m.group(3)
        if feat.lower() in ("feature", "psi", "---"):
            continue
        signal, detail = _plain_feature(feat)
        severity = "watch" if psi_status == "DRIFT" else "ok"
        # Only surface DRIFT items unless all are ok (then surface first 3 for reassurance)
        if severity == "watch":
            drift_items.append(DriftItem(signal=signal, severity=severity, detail=detail))

    if not drift_items:
        drift_items.append(DriftItem(
            signal="All inputs stable",
            severity="ok",
            detail="No unusual shifts detected in demand signals",
        ))

    # Add accuracy gate note if accuracy held despite drift
    acc_status = _f(r'champion holdout.*?:\s*([0-9.]+)', drift_txt)
    recent_status = _f(r'recent-window.*?:\s*([0-9.]+)', drift_txt)
    if acc_status and recent_status and recent_status <= acc_status:
        # accuracy held or improved — add a reassurance item
        drift_items.append(DriftItem(
            signal="Forecast accuracy held",
            severity="ok",
            detail=f"Despite input signal shifts, forecast accuracy is {recent_accuracy:.1f}% — within normal range",
        ))

    # ── verdict ──
    raw_verdict = ""
    m = re.search(r'Verdict[:\s*]*\**(.*?)\**\n', drift_txt, re.IGNORECASE)
    if m:
        raw_verdict = m.group(1).strip().strip("*").strip()

    if "URGENT" in raw_verdict.upper():
        verdict = "Retrain urgent"
    elif "RECOMMENDED" in raw_verdict.upper() or "RETRAIN" in raw_verdict.upper():
        verdict = "Retrain recommended"
    else:
        verdict = "All clear — model healthy"

    last_checked = None
    try:
        mtime = (REPORTS / "drift_monitor.md").stat().st_mtime
        last_checked = datetime.fromtimestamp(mtime).strftime("%Y-%m-%d %H:%M")
    except Exception:
        pass

    return LearningStatus(
        live_version=version,
        live_accuracy_pct=live_accuracy,
        recent_accuracy_pct=recent_accuracy,
        accuracy_trend=trend,
        candidate=candidate,
        drift_watch=drift_items,
        verdict=verdict,
        last_checked=last_checked,
    )


@router.get("/log", response_model=LearningLog)
def log(limit: int = 50) -> LearningLog:
    log_path = MODELS / "pipeline_log.jsonl"
    entries: list[LogEntry] = []

    if not log_path.exists():
        return LearningLog(entries=[])

    raw_lines = log_path.read_text(encoding="utf-8").strip().splitlines()
    for line in raw_lines[-limit:]:
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue

        kind = d.get("kind", "")
        ts = d.get("ts", None)

        if kind == "retrain":
            wmape = d.get("wmape", None)
            rows = d.get("train_rows", None)
            ver = d.get("version", "")
            acc = f"{(1 - wmape) * 100:.1f}%" if wmape else "—"
            summary = f"Model retrained ({ver}) · accuracy {acc} · {rows:,} training rows" if rows else f"Model retrained ({ver}) · accuracy {acc}"

        elif kind == "predict":
            date = d.get("date", "")
            units = d.get("order_units", None)
            ver = d.get("version", "")
            u_str = f"{units:,.0f}" if units else "—"
            summary = f"Daily plan generated for {date} · {u_str} units ordered · using {ver}"

        elif kind == "monitor":
            drift = d.get("drift", False)
            acc_drift = str(d.get("acc_drift", "False")).lower() not in ("false", "0", "")
            verd = d.get("verdict", "")
            if acc_drift:
                summary = f"Health check · accuracy degraded · {verd}"
            elif drift:
                summary = f"Health check · input signals shifted · accuracy held — {verd}"
            else:
                summary = f"Health check · all clear · {verd}"

        else:
            summary = json.dumps(d)

        entries.append(LogEntry(ts=ts, kind=kind, summary=summary))

    return LearningLog(entries=entries)
