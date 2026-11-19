"""FE_REQUESTS 반영 검증.

3) /api/map/{layer} 포인트별 monthly 배열
4) report.monthly_pattern
6) /api/stores 신규 엔드포인트
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DB", str(tmp_path / "s.sqlite3"))
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "0")  # 끔
    monkeypatch.setenv("LLM_PROVIDER", "none")
    from agent import config, sessions
    config.reload_settings()
    sessions._conn = None  # noqa: SLF001
    import importlib
    from apps.api import main as main_module
    importlib.reload(main_module)
    return TestClient(main_module.app)


# ---- 3) /api/map monthly ----

def test_map_demand_points_include_monthly(client):
    r = client.get("/api/map/demand", params={"category": "카페"})
    assert r.status_code == 200
    data = r.json()
    # 카테고리 지정 시 포인트에 monthly 12개
    awol = next((p for p in data["points"] if p["dong"] == "애월읍"), None)
    assert awol is not None
    assert "monthly" in awol
    assert len(awol["monthly"]) == 12


def test_map_without_category_omits_monthly(client):
    r = client.get("/api/map/demand")
    data = r.json()
    pt = data["points"][0]
    assert "monthly" not in pt


# ---- 4) report.monthly_pattern ----

def test_report_contains_monthly_pattern_when_demand_available(client):
    run_id = client.post("/api/diagnose",
                         json={"category": "카페", "dong": "애월읍",
                               "customer": "any", "risk": "safe"}).json()["run_id"]
    with client.stream("GET", f"/api/diagnose/{run_id}/events") as resp:
        body = "".join(resp.iter_text())
    assert "event: report" in body
    import json, re
    for line in body.splitlines():
        if line.startswith("data:") and '"type": "report"' in line:
            payload = json.loads(line[6:])
            r = payload["report"]
            assert "monthly_pattern" in r, "report에 monthly_pattern 없음"
            assert len(r["monthly_pattern"]["values"]) == 12
            assert len(r["monthly_pattern"]["labels"]) == 12
            assert len(r["monthly_pattern"]["tourism_values"]) == 12
            assert sum(r["monthly_pattern"]["tourism_values"]) > 0
            return
    raise AssertionError("report 이벤트 없음")


def test_chat_keeps_ages_and_demand_reason(client):
    """20대를 고른 뒤 다른 지역을 물으면 수요 사유에 20대가 남는다."""
    import json
    first = client.post("/api/diagnose", json={
        "category": "카페", "dong": "애월읍", "customer": "any",
        "ages": ["20대"], "risk": "safe",
    }).json()["run_id"]
    followed = client.post("/api/chat", json={"run_id": first, "question": "한림읍은?"})
    assert followed.status_code == 200
    body = followed.json()
    assert body["parsed"]["dong"] == "한림읍"
    run_id = body["run_id"]
    with client.stream("GET", f"/api/diagnose/{run_id}/events") as resp:
        text = "".join(resp.iter_text())
    report = None
    for line in text.splitlines():
        if line.startswith("data:") and '"type": "report"' in line:
            report = json.loads(line[6:])["report"]
    assert report is not None
    demand = next(s for s in report["signals"] if s["name"] == "수요 규모")
    assert "20대" in demand["reason"]


# ---- 6) /api/stores ----

def test_stores_dong_only(client):
    r = client.get("/api/stores", params={"dong": "애월읍", "limit": 5})
    assert r.status_code == 200
    data = r.json()
    assert data["dong"] == "애월읍"
    assert data["total"] > 0
    assert len(data["items"]) <= 5
    item = data["items"][0]
    for k in ("name", "address", "lon", "lat", "category"):
        assert k in item


def test_stores_dong_and_category(client):
    r = client.get("/api/stores",
                   params={"dong": "애월읍", "category": "카페", "limit": 3})
    data = r.json()
    assert data["total"] >= 3
    # D4 카페 카테고리는 '커피 전문점' 또는 '기타 비알코올 음료점업' sub
    for it in data["items"]:
        assert "커피" in it["category"] or "비알코올" in it["category"]


def test_stores_with_near_sorts_by_distance(client):
    r = client.get("/api/stores",
                   params={"dong": "애월읍", "category": "카페",
                           "limit": 5, "near": "126.33,33.46"})
    data = r.json()
    dists = [it["distance_m"] for it in data["items"]]
    assert dists == sorted(dists)


def test_stores_unknown_dong_returns_empty(client):
    r = client.get("/api/stores", params={"dong": "없는동XYZ"})
    data = r.json()
    assert data["total"] == 0
    assert data["items"] == []


def test_stores_validation(client):
    assert client.get("/api/stores", params={"dong": "애월읍", "limit": 0}).status_code == 400
    assert client.get("/api/stores", params={"dong": "애월읍", "limit": 500}).status_code == 400
    assert client.get("/api/stores",
                     params={"dong": "애월읍", "near": "bad"}).status_code == 400
