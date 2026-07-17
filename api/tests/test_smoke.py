"""Every GET route answers; health is deep-green."""
import pytest

GET_ROUTES = [
    "/health",
    "/sources",
    "/data/manual",
    "/eda",
    "/experiments",
    "/results/summary",
    "/deploy/health",
    "/deploy/history",
    "/learning/status",
    "/agent/status",
    "/analysis",
    "/pipeline/stages",
    "/pipeline/jobs",
    "/settings/security",
    "/order/picklist?date=2026-06-20",
]


@pytest.mark.parametrize("path", GET_ROUTES)
def test_get_200(client, path):
    r = client.get(path)
    assert r.status_code == 200, f"{path} → {r.status_code}: {r.text[:200]}"


def test_health_deep_ok(client):
    body = client.get("/health").json()
    assert body["ok"] is True
    assert body["detail"] == "ok"  # DuckDB forecast view reachable
