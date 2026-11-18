from fastapi.testclient import TestClient

from apps.api.main import app


def test_health():
    r = TestClient(app).get("/api/health")
    assert r.status_code == 200
    assert r.json()["ok"] is True


def test_diagnose_stream_ends_with_report():
    c = TestClient(app)
    run_id = c.post("/api/diagnose", json={"category": "카페", "dong": "애월읍"}).json()["run_id"]
    with c.stream("GET", f"/api/diagnose/{run_id}/events") as r:
        body = "".join(r.iter_text())
    assert "event: report" in body
