"""의도 파악·clarify·부분 진단 테스트 (실사용 피드백 반영)."""
from __future__ import annotations

import asyncio

from agent.loop import run
from agent.tools import (
    category_availability, parse_intent, resolve_category, resolve_place,
    score_risk,
)


def _collect(form: dict) -> list[dict]:
    async def _c():
        return [ev async for ev in run(form)]
    return asyncio.new_event_loop().run_until_complete(_c())


# ---------- 의도 파싱 ----------

def test_parse_intent_cc_only_triggers_clarify():
    r = parse_intent("위치 ㅊㅊ")
    assert r["intent"] == "clarify"


def test_parse_intent_place_recommend_from_pcbang():
    r = parse_intent("피씨방 하려는데 할만한 지역 추천해줘")
    assert r["intent"] == "place_recommend"
    assert r["hints"].get("category") == "PC방"


def test_parse_intent_category_recommend_from_dong():
    r = parse_intent("애월에 뭐 하지?")
    assert r["intent"] == "category_recommend"
    assert r["hints"].get("dong") == "애월읍"


def test_resolve_place_does_not_confuse_non_place():
    """'뭐', '할만한' 같은 자연어는 지역으로 단정하지 않는다."""
    for q in ("뭐", "할만한", "추천"):
        r = resolve_place(q)
        assert r["dong"] is None


def test_resolve_category_pcbang_alias():
    r = resolve_category("피씨방")
    assert r["app_category"] == "PC방"


# ---------- 업종 가용성 ----------

def test_category_availability_partial():
    av = category_availability("PC방")
    assert av == {"has_card": False, "has_store": True, "has_license": False}


def test_category_availability_full():
    av = category_availability("카페")
    assert av == {"has_card": True, "has_store": True, "has_license": True}


# ---------- 부분 진단 ----------

def test_partial_mode_pcbang():
    """PC방: D4+D2만 있음 → partial, 신뢰도 규칙으로 score=null 가능."""
    r = score_risk("애월읍", "PC방")
    assert r["available"] is True
    assert r["mode"] == "partial"
    comp = next(s for s in r["signals"] if s["name"] == "경쟁 밀도")
    assert comp["level"] in ("green", "yellow", "red")


def test_partial_mode_hair_salon():
    r = score_risk("노형동", "미용실")
    assert r["mode"] == "partial"


def test_score_null_when_few_active_signals():
    """경쟁 밀도만 가용(수요 계열 없음) → score=null, confidence=low."""
    # D2 유동 수요가 대부분 가용하므로 경쟁 밀도 외 1개 더 가용 가능.
    # 그래도 수요 계열 없는 상황을 만들기 위해 임의의 미등록 동을 피해 실제 분기 확인.
    r = score_risk("애월읍", "PC방")
    # PC방은 D1/D5 모두 매핑 없음 → 가용은 경쟁 밀도 + 유동 수요만 가능
    # 유동 수요도 가용이면 score 산출 가능. 판정은 active_signals 기반.
    if r.get("active_signals", 0) < 3 or not any(
        s["name"] in ("수요 규모", "유동 수요") and s["level"] != "unavailable"
        for s in r["signals"]
    ):
        assert r["score"] is None
        assert r["confidence"] == "low"
    else:
        assert r["score"] is not None


# ---------- 루프에서 clarify ----------

def test_loop_emits_clarify_for_empty_input():
    evs = _collect({"category": None, "dong": None, "customer": "any",
                    "ages": [], "risk": "balanced", "question": None})
    clarify_evs = [e for e in evs if e["type"] == "clarify"]
    assert len(clarify_evs) == 1
    assert clarify_evs[0]["field"] in ("category", "dong")
    # clarify 후에는 report 없음
    assert not any(e["type"] == "report" for e in evs)


def test_loop_emits_clarify_for_position_cc():
    evs = _collect({"category": None, "dong": None, "customer": "any",
                    "ages": [], "risk": "balanced", "question": "위치 ㅊㅊ"})
    assert any(e["type"] == "clarify" for e in evs)


def test_loop_partial_report_for_pcbang_place_recommend():
    """'피씨방 ... 할만한 지역' → place_recommend 모드 + 대안 지역."""
    evs = _collect({"category": None, "dong": None, "customer": "any",
                    "ages": [], "risk": "balanced",
                    "question": "피씨방 하려는데 할만한 지역 추천해줘"})
    reports = [e for e in evs if e["type"] == "report"]
    assert len(reports) == 1, f"리포트 1개여야 함, 받은 {len(reports)}개"
    r = reports[0]["report"]
    assert r["target"]["category"] == "PC방"
    assert r["target"]["dong"] is None
    assert len(r["alternatives"]) >= 1


def test_loop_full_mode_for_cafe_awol():
    """기존 카페·애월읍 시나리오는 여전히 full 모드 + 6 signals."""
    evs = _collect({"category": "카페", "dong": "애월읍", "customer": "any",
                    "ages": [], "risk": "safe"})
    r = next(e for e in evs if e["type"] == "report")["report"]
    assert r["mode"] == "full"
    assert len(r["signals"]) == 7  # 유동 수요 추가
    # 모든 신호에 as_of 존재
    for s in r["signals"]:
        assert "as_of" in s and s["as_of"]
