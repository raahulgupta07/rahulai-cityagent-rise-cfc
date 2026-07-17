"""
Router auto-registry. Wave-2 convention — DO NOT edit main.py to add a feature.

Each feature slice drops a file `api/routes/<name>.py` that defines a module-level
`router = APIRouter(prefix="/<name>", tags=["<name>"])`. This package imports every
sibling module on startup and collects their `router`. So 4 parallel agents each add
their OWN route file with ZERO shared-file edits → no merge conflicts.
"""
from __future__ import annotations
import importlib, pkgutil
from fastapi import APIRouter

def all_routers() -> list[APIRouter]:
    routers: list[APIRouter] = []
    for mod in pkgutil.iter_modules(__path__):
        if mod.name.startswith("_"):
            continue
        m = importlib.import_module(f"{__name__}.{mod.name}")
        r = getattr(m, "router", None)
        if isinstance(r, APIRouter):
            routers.append(r)
    return routers
