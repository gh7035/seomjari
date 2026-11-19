"""SPEC §12 검증 — 리포트의 모든 수치가 도구 출력에 존재해야 한다.

재현성(3회 반복)과 수치 grounding을 같이 본다.
"""
from __future__ import annotations

import asyncio
import re

import pytest

from agent import loop


async def _collect(form: dict) -> list[dict]:
    return [ev async for ev in loop.run(form)]


def _run(form: dict) -> list[dict]:
    return asyncio.get_event_loop().run_until_complete(_collect(form))


S1 = {"category": "카페", "dong": "애월읍", "customer": "any", "ages": [], "risk": "safe"}
S2 = {"category": "카페", "dong": None, "customer": "local", "ages": [], "risk": "balanced"}
S4 = {"category": None, "dong": "애월읍", "customer": "any", "ages": [], "risk": "balanced"}
S5 = {"category": "자동차 정비소", "dong": "애월읍", "customer": "any", "ages": [], "risk": "balanced"}


def _extract_numbers(s: str) -> set[str]:
    """리포트 문자열에서 수치 토큰만 추출. 숫자(퍼센트/배/점 포함)와 N위/NN 형태."""
    pats = [
        r"\d+\.\d+%",      # 74.5%
        r"\d+%",           # 74%
        r"\d+\.\d+배",     # 1.96배
        r"\d+배",
        r"\d+(?:,\d{3})+원",  # 67,527,213원
        r"\d{4,}원",
        r"\d+위",
        r"\d+/\d+",        # 1/43
    ]
    out: set[str] = set()
    for p in pats:
        out.update(re.findall(p, s))
    return out


def test_s1_report_shape():
    evs = _run(S1)
    reps = [e for e in evs if e["type"] == "report"]
    assert len(reps) == 1
    r = reps[0]["report"]
    assert r["target"] == {"dong": "애월읍", "category": "카페"}
    assert {s["name"] for s in r["signals"]} == {
        "관광 의존도", "계절 변동성", "경쟁 밀도", "수요 규모",
        "유동 수요", "생존 리스크", "최근 개폐업"
    }
    assert r["score"] is None or 0 <= r["score"] <= 100
    assert len(r["evidence"]) >= 2
    assert len(r["limitations"]) >= 2
    # 모든 신호에 as_of 포함
    for s in r["signals"]:
        assert "as_of" in s and s["as_of"], f"signal {s['name']} missing as_of"


def test_s1_reproducible_3x():
    """같은 입력을 3회 실행 → score와 signal level이 동일해야 한다."""
    results = []
    for _ in range(3):
        evs = _run(S1)
        r = next(e for e in evs if e["type"] == "report")["report"]
        results.append((r["score"], tuple(s["level"] for s in r["signals"])))
    assert len(set(results)) == 1, f"비결정론적 결과: {results}"


def test_s1_signals_match_score_risk():
    """안정형 애월읍 카페의 신호 값·레벨·점수는 score_risk와 같다."""
    from agent import tools
    from agent.loop import _weights_from_form

    evs = _run(S1)
    rep = next(e for e in evs if e["type"] == "report")["report"]
    risk = tools.score_risk(
        "애월읍", "카페", weights=_weights_from_form(S1),
        context={"ages": [], "customer": "any"})
    assert rep["score"] == risk["score"]
    assert [(s["name"], s["value"], s["level"]) for s in rep["signals"]] == [
        (s["name"], s["value"], s["level"]) for s in risk["signals"]
    ]
    foot = next(s for s in rep["signals"] if s["name"] == "유동 수요")
    assert foot["as_of"] == "2018-01~2019-12"
    season = next(s for s in rep["signals"] if s["name"] == "계절 변동성")
    assert season["value"] == "8월/12월 1.96배"
    assert rep["score"] == 46
    first = rep["summary"].split("큽니다.", 1)[0]
    assert "74.5%" in first and "8월" in first and "12월" in first
    alt = rep["alternatives"][0]
    assert alt.get("tour_value") and alt.get("survival_value")
    assert float(alt["tour_value"].rstrip("%")) < 74.5
    cmp = tools.compare_places(
        "카페", top_k=3, weights=_weights_from_form(S1),
        exclude=["애월읍"], context={"ages": [], "customer": "any"})
    assert [(a["dong"], a["score"]) for a in rep["alternatives"]] == [
        (r["dong"], r["score"]) for r in cmp["ranking"]
    ]
    d6 = next(e for e in rep["evidence"] if e["source"] == "D6")
    assert "순증 자료 없음" not in d6["detail"]
    assert re.search(r"순증 [+-]\d+", d6["detail"])
    assert "D6" not in str(risk.get("weights", {}))


def test_balanced_aewol_summary_names_tourism_and_score():
    evs = _run({"category": "카페", "dong": "애월읍", "customer": "any",
                "ages": [], "risk": "balanced"})
    rep = next(e for e in evs if e["type"] == "report")["report"]
    first = rep["summary"].split("큽니다.", 1)[0]
    assert "74.5%" in first and "8월" in first and "12월" in first
    assert str(rep["score"]) in first


def test_llm_keeps_server_score_when_model_forges_99(monkeypatch):
    """문장만 바꾸고 score 99를 넣어도 신호와 점수는 서버 값이다. 호출은 1회."""
    import json
    import agent.llm as llm_mod

    calls = {"n": 0}

    def fake(messages, tools):  # noqa: ARG001
        calls["n"] += 1
        payload = json.loads(messages[-1]["content"])
        dong = payload["alternatives"][0]["dong"]
        return {"text": json.dumps({
            "summary": "모델이 쓴 결론입니다.",
            "score": 99,
            "signals": [{"name": "관광 의존도", "value": "1%", "level": "green"}],
            "alternatives": [{"dong": dong, "why": "모델이 쓴 이유", "score": 1}],
        }, ensure_ascii=False), "tool_calls": []}

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", fake)
    evs = _run(S1)
    assert calls["n"] == 1
    ev = next(e for e in evs if e["type"] == "report")
    rep = ev["report"]
    from agent import tools
    from agent.loop import _weights_from_form
    risk = tools.score_risk(
        "애월읍", "카페", weights=_weights_from_form(S1),
        context={"ages": [], "customer": "any"})
    assert rep["score"] == risk["score"]
    assert rep["score"] != 99
    assert rep["mode"] == "full"
    assert ev["mode"] == "llm"
    assert rep["summary"] == "모델이 쓴 결론입니다."
    assert [(s["name"], s["value"], s["level"]) for s in rep["signals"]] == [
        (s["name"], s["value"], s["level"]) for s in risk["signals"]
    ]
    alt = rep["alternatives"][0]
    assert alt["why"] == "모델이 쓴 이유"
    assert alt["score"] != 1


def test_llm_rejects_summary_99_points(monkeypatch):
    """문장 안의 99점은 서버 점수 46과 다르므로 규칙 문장을 유지한다."""
    import json
    import agent.llm as llm_mod

    def fake(messages, tools):  # noqa: ARG001
        return {"text": json.dumps({"summary": "종합 99점입니다.", "score": 99}),
                "tool_calls": []}

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", fake)
    evs = _run(S1)
    ev = next(e for e in evs if e["type"] == "report")
    rep = ev["report"]
    assert rep["score"] == 46
    assert "99점" not in rep["summary"]
    assert "74.5%" in rep["summary"] and "8월" in rep["summary"]
    assert rep.get("narrative") == "rule"
    assert ev["mode"] == "fallback"


def test_llm_accepts_server_month_and_score(monkeypatch):
    import json
    import agent.llm as llm_mod

    summary = "관광 의존도 74.5%이고 8월이 높아 종합 46점입니다."

    def fake(messages, tools):  # noqa: ARG001
        return {"text": json.dumps({"summary": summary}), "tool_calls": []}

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", fake)
    evs = _run(S1)
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["summary"] == summary
    assert rep["score"] == 46


def test_open_question_plan_failure_still_reports_gap(monkeypatch):
    import agent.llm as llm_mod

    def boom(messages, tools):  # noqa: ARG001
        raise RuntimeError("plan down")

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", boom)
    evs = _run({"category": None, "dong": None, "customer": "any", "ages": [],
                "risk": "balanced", "question": "성산에 뭐 하면 좋을까"})
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["focus"] == "gap"
    assert rep["target"]["dong"] == "성산읍"
    assert rep["score"] is None


def test_open_question_plan_score_is_ignored(monkeypatch):
    import json
    import agent.llm as llm_mod

    calls = {"n": 0}

    def fake(messages, tools):  # noqa: ARG001
        calls["n"] += 1
        return {"text": json.dumps({
            "intent": "category_recommend",
            "map_layer": "footfall",
            "score": 99,
        }, ensure_ascii=False), "tool_calls": []}

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", fake)
    evs = _run({"category": None, "dong": None, "customer": "any", "ages": [],
                "risk": "balanced", "question": "성산에 뭐 하면 좋을까"})
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert calls["n"] == 2
    assert rep["focus"] == "gap"
    assert rep["target"]["dong"] == "성산읍"
    assert rep["score"] is None
    assert rep["score"] != 99


def test_llm_exception_keeps_partial_nail(monkeypatch):
    """문장 호출이 죽어도 리포트가 나오고, 네일샵 mode는 partial이다."""
    import agent.llm as llm_mod

    def boom(messages, tools):  # noqa: ARG001
        raise RuntimeError("402 RESOURCE_EXHAUSTED")

    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools", boom)
    evs = _run({"category": "네일샵", "dong": "애월읍", "customer": "any",
                "ages": [], "risk": "balanced"})
    ev = next(e for e in evs if e["type"] == "report")
    rep = ev["report"]
    assert ev["mode"] == "fallback"
    assert rep["mode"] == "partial"
    assert rep["score"] is None
    assert rep.get("narrative") == "rule"
    assert "문장은 규칙으로 작성" in rep["limitations"]
    assert "LLM 오류로 규칙 기반으로 재생성" not in " ".join(rep["limitations"])


def test_s1_numbers_grounded():
    """리포트 텍스트의 모든 수치가 도구 tool 이벤트의 summary에 존재해야 한다."""
    evs = _run(S1)
    tool_summaries = " ".join(e["summary"] for e in evs if e["type"] == "tool")
    rep = next(e for e in evs if e["type"] == "report")["report"]
    haystack = tool_summaries

    text_in_report = " ".join(
        [rep["summary"]]
        + [e["detail"] for e in rep["evidence"]]
        + [a["why"] + str(a["score"]) for a in rep["alternatives"]]
    )

    report_nums = _extract_numbers(text_in_report)
    stray: set[str] = set()
    for n in report_nums:
        if n in haystack:
            continue
        # score는 숫자(위/점수) — 수요 규모의 "N위" 형태는 signals에 있어 통과
        # 알림: alternatives의 점수는 compare_places 호출에서 만들어지며 요약에 들어가 있음
        stray.add(n)
    assert not stray, f"도구 출력에 없는 수치가 리포트에 등장: {stray}"


def test_s2_region_recommendation():
    evs = _run(S2)
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["target"]["dong"] is None
    assert len(rep["alternatives"]) >= 1  # Top 3 지역 제안


def test_gap_category_for_place_question():
    """지역만 묻고 업종을 추천해 달라면 빈틈 업종 리포트를 낸다."""
    evs = _run({"category": None, "dong": None, "customer": "any", "ages": [],
                "risk": "balanced", "question": "성산에 뭐 하면 좋을까"})
    assert not [e for e in evs if e["type"] == "clarify"]
    rep = next(e for e in evs if e["type"] == "report")["report"]
    assert rep["focus"] == "gap"
    assert rep["target"]["dong"] == "성산읍"
    assert rep["target"]["category"] is None
    assert rep["score"] is None
    assert len(rep["alternatives"]) >= 1
    assert rep["trend"]


def test_age_changes_demand_reason():
    evs = _run({"category": "카페", "dong": "애월읍", "customer": "any",
                "ages": ["20대"], "risk": "safe"})
    rep = next(e for e in evs if e["type"] == "report")["report"]
    demand = next(s for s in rep["signals"] if s["name"] == "수요 규모")
    assert "20대" in demand["reason"]
    foot = next(s for s in rep["signals"] if s["name"] == "유동 수요")
    assert "연령 미적용" in foot["reason"]


def test_s4_ambiguous_category():
    """지역만 있고 업종 없음 → clarify 이벤트."""
    evs = _run(S4)
    clarify = [e for e in evs if e["type"] == "clarify"]
    reports = [e for e in evs if e["type"] == "report"]
    assert len(clarify) == 1
    assert clarify[0]["field"] == "category"
    assert not reports, "clarify 응답에서는 report를 보내지 않는다"


def test_s5_unsupported_category_no_hallucination():
    """지원 매핑에 없는 업종 → clarify(category)."""
    evs = _run(S5)
    # 매핑에 없으므로 resolve_category 실패 → clarify(category)
    clarify = [e for e in evs if e["type"] == "clarify"]
    assert len(clarify) == 1
    assert clarify[0]["field"] == "category"


@pytest.fixture(scope="session", autouse=True)
def _ensure_loop():
    try:
        asyncio.get_event_loop()
    except RuntimeError:
        asyncio.set_event_loop(asyncio.new_event_loop())
