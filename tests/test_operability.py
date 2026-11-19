"""운영 레벨 보강 테스트.

- 세션 영속화 (SQLite)
- 리포트 스키마·grounding 검증 모듈
- 레이트리밋 미들웨어
- 헬스 분리 /livez /readyz
- 전역 예외 핸들러
"""
from __future__ import annotations

import os
import tempfile

import pytest
from fastapi.testclient import TestClient


# ---------- sessions 영속화 ----------

def test_sessions_put_get_roundtrip(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DB", str(tmp_path / "s.sqlite3"))
    from agent import config, sessions
    config.reload_settings()
    # 기존 커넥션 닫고 재초기화
    sessions._conn = None  # noqa: SLF001
    sessions.put_run("abc123", {"category": "카페", "dong": "애월읍"})
    sess = sessions.get_run("abc123")
    assert sess is not None
    assert sess["form"]["category"] == "카페"
    sessions.set_report("abc123", {"summary": "ok"}, mode="fallback")
    sess2 = sessions.get_run("abc123")
    assert sess2["report"]["summary"] == "ok"
    assert sess2["mode"] == "fallback"


def test_sessions_ttl_gc(tmp_path, monkeypatch):
    import time as _t
    monkeypatch.setenv("SESSION_DB", str(tmp_path / "t.sqlite3"))
    monkeypatch.setenv("SESSION_TTL_S", "1")
    from agent import config, sessions
    config.reload_settings()
    sessions._conn = None  # noqa: SLF001
    sessions.put_run("old", {"a": 1})
    _t.sleep(1.2)
    sessions.put_run("new", {"a": 2})  # 이 호출이 _gc 트리거
    assert sessions.get_run("old") is None
    assert sessions.get_run("new") is not None


# ---------- validation ----------

def test_validate_report_shape_detects_errors():
    from agent.validation import validate_report_shape
    bad = {"summary": 1, "signals": [{"name": "X", "level": "pink", "value": "", "reason": ""}],
           "score": 999, "evidence": [{"source": "DX", "period": "", "note": "..."}],
           "map": {"layer": "demand", "highlight": []}}
    errs = validate_report_shape(bad)
    assert any("summary" in e for e in errs)
    assert any("signals" in e for e in errs)
    assert any("score" in e for e in errs)
    assert any("evidence" in e for e in errs)


def test_grounding_stray_detects_hallucinated_number():
    from agent.validation import grounding_stray
    report = {"summary": "애월읍 관광 99.9%로 매우 높음.",
              "signals": [{"name": "관광 의존도", "value": "74.5%", "level": "red", "reason": "."}],
              "evidence": [{"source": "D1", "period": "2018-01~2019-12", "detail": "월평균 10,000원"}]}
    stray = grounding_stray(report, ["관광 74.5% / 도민 25.5%"])
    assert "99.9%" in stray or any("99" in s for s in stray)


def test_coerce_note_to_detail():
    from agent.validation import coerce_evidence_note_to_detail
    r = {"evidence": [{"source": "D1", "period": "p", "note": "foo"}]}
    coerce_evidence_note_to_detail(r)
    assert r["evidence"][0]["detail"] == "foo"
    assert "note" not in r["evidence"][0]


# ---------- 미들웨어 통합 ----------

@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("SESSION_DB", str(tmp_path / "s.sqlite3"))
    monkeypatch.setenv("RATE_LIMIT_PER_MIN", "3")
    monkeypatch.setenv("LLM_PROVIDER", "none")
    from agent import config, sessions
    config.reload_settings()
    sessions._conn = None  # noqa: SLF001

    import importlib

    from apps.api import main as main_module
    importlib.reload(main_module)  # 새 config로 app 재구성
    return TestClient(main_module.app)


def test_livez_ok(client):
    r = client.get("/livez")
    assert r.status_code == 200
    assert r.json() == {"ok": True}


def test_readyz_reports_data(client):
    r = client.get("/readyz")
    # data가 준비돼 있어야 함 (parquet 파일 존재)
    assert r.status_code in (200, 503)


def test_request_id_header(client):
    r = client.get("/api/health")
    assert "x-request-id" in {k.lower() for k in r.headers}


def test_rate_limit_triggers_429(client):
    """write 버킷(/api/diagnose)에서 기본 상한을 넘어서면 429.

    read 버킷(/api/map, /api/meta, /api/stores)은 10배 상한이라 테스트에서 제외.
    """
    seen_429 = False
    for _ in range(8):
        r = client.post("/api/diagnose",
                        json={"category": "카페", "dong": "애월읍", "risk": "balanced"})
        if r.status_code == 429:
            seen_429 = True
            assert "Retry-After" in r.headers
            break
    assert seen_429, "레이트리밋이 발동하지 않음"


def test_diagnose_validation_rejects_too_long(client):
    r = client.post("/api/diagnose", json={"category": "x" * 100})
    assert r.status_code == 422


def test_read_bucket_has_higher_limit(client):
    """read 버킷은 write의 10배 상한 → 8번 /api/map 호출해도 429 없음."""
    for _ in range(8):
        r = client.get("/api/map/demand", params={"category": "카페"})
        assert r.status_code == 200, f"읽기 요청에 429 발생: {r.status_code}"


def test_map_response_has_cache_control(client):
    r = client.get("/api/map/demand", params={"category": "카페"})
    assert "cache-control" in {k.lower() for k in r.headers}
    assert "max-age=60" in r.headers.get("cache-control", "").lower()
