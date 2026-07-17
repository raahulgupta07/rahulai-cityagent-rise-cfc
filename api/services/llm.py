"""
LLM helper — OpenRouter only (per cross-project rule; never a direct provider SDK).

The agent uses this to narrate its plan and interpret results in plain language.
It is OPTIONAL: if OPENROUTER_API_KEY is unset or the call fails, callers fall back
to a deterministic template, so Autopilot always works offline.

Env:
    OPENROUTER_API_KEY   required to enable LLM narration
    AGENT_MODEL          model slug (default anthropic/claude-3.5-haiku)
    EXPLAIN_MODEL        model slug for plain-language forecast explanations
                         (default z-ai/glm-4.6, via OpenRouter)
"""
from __future__ import annotations
import os
import logging

log = logging.getLogger(__name__)

_ENDPOINT = "https://openrouter.ai/api/v1/chat/completions"


def enabled() -> bool:
    return bool(os.getenv("OPENROUTER_API_KEY"))


def model() -> str:
    return os.getenv("AGENT_MODEL", "anthropic/claude-3.5-haiku")


def explain_model() -> str:
    return os.getenv("EXPLAIN_MODEL", "z-ai/glm-4.6")


def _call(model: str, system: str, user: str, max_tokens: int = 300,
          timeout: float = 25.0) -> str | None:
    """Single-shot OpenRouter completion for a given model. Returns text or None on failure."""
    key = os.getenv("OPENROUTER_API_KEY")
    if not key:
        return None
    try:
        import httpx
        r = httpx.post(
            _ENDPOINT,
            headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system},
                    {"role": "user", "content": user},
                ],
                "max_tokens": max_tokens,
                "temperature": 0.3,
            },
            timeout=timeout,
        )
        r.raise_for_status()
        return r.json()["choices"][0]["message"]["content"].strip()
    except Exception as exc:
        log.warning("OpenRouter call failed (model=%s: %s); falling back", model, exc)
        return None


def chat(system: str, user: str, max_tokens: int = 300, timeout: float = 25.0) -> str | None:
    """Single-shot completion via OpenRouter. Returns text or None on any failure."""
    return _call(model(), system, user, max_tokens=max_tokens, timeout=timeout)


def explain(system: str, user: str, max_tokens: int = 500) -> str | None:
    """Plain-language explanation. Tries EXPLAIN_MODEL (GLM) first, then falls back to
    the default chat model (haiku), then None so the caller uses a template."""
    if not os.getenv("OPENROUTER_API_KEY"):
        return None
    txt = _call(explain_model(), system, user, max_tokens=max_tokens)
    if txt:
        return txt
    return _call(model(), system, user, max_tokens=max_tokens)
