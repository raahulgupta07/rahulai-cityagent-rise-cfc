"""SQLite operational stores + heavy-lock + security posture."""
from deps import jobs, store, audit
from deps.auth import security_posture


def test_job_lifecycle_durable():
    j = jobs.new_job("predict", {"date": "2026-06-21"}, heavy=True, mode="real")
    jobs.finish_job(j["id"], 0)
    got = jobs.get_job(j["id"])
    assert got["status"] == "done"
    assert any(r["id"] == j["id"] for r in jobs.list_jobs())


def test_heavy_lock_non_reentrant():
    assert jobs.try_acquire_heavy() is True
    assert jobs.try_acquire_heavy() is False   # second caller blocked
    jobs.release_heavy()
    assert jobs.try_acquire_heavy() is True     # freed after release
    jobs.release_heavy()


def test_audit_and_uploads_persist():
    store.record_audit("promo_calendar", "promo.csv", 42, True)
    audit.record_event("user:admin", "promote", "v_test")
    assert any(r["key"] == "promo_calendar" for r in store.list_audits())
    assert any(r["action"] == "promote" for r in audit.list_events())


def test_security_posture_dev_ok():
    p = security_posture()
    assert p["is_prod"] is False
    assert p["ok"] is True


def test_security_posture_prod_insecure(monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.delenv("SECRET_KEY", raising=False)
    monkeypatch.setenv("AUTH_DISABLED", "1")
    p = security_posture()
    assert p["is_prod"] is True
    assert p["insecure_secret"] is True
    assert p["auth_disabled"] is True
    assert p["ok"] is False
