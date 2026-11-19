"""resolve_place_via_landmark: 랜드마크·생활 지명 → 행정동.

LLM 호출을 monkeypatch로 교체해 결정론적으로 검증.
"""
from __future__ import annotations

from agent import tools


LANDMARK_FIXTURES = {
    "제주시청 근처": "이도1동",
    "함덕 해수욕장": "조천읍",
    "성산일출봉": "성산읍",
    "중문 관광단지": "중문동",
    "모름없는랜드마크XYZ": None,  # 모를 땐 UNKNOWN
}


def _fake_llm_factory(target_dong: str | None):
    def _fake(messages, tools):  # noqa: ARG001
        if target_dong:
            text = '{"dong": "' + target_dong + '"}'
        else:
            text = '{"dong": "UNKNOWN"}'
        return {"text": text, "tool_calls": [], "_raw_content": None}
    return _fake


def test_resolve_place_via_landmark_known(monkeypatch):
    """알려진 랜드마크 3개 이상이 LLM 매핑으로 해결되는지."""
    import agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    resolved_count = 0
    for text, expected in LANDMARK_FIXTURES.items():
        monkeypatch.setattr(llm_mod, "chat_with_tools", _fake_llm_factory(expected))
        r = tools.resolve_place_via_landmark(text)
        if expected is None:
            assert r["dong"] is None
            assert r["not_found"] is True
        else:
            assert r["dong"] == expected, f"{text}: 기대 {expected}, 실제 {r['dong']}"
            resolved_count += 1
    assert resolved_count >= 3, "최소 3개 랜드마크는 해결돼야 함"


def test_resolve_place_via_landmark_no_llm(monkeypatch):
    """LLM 미설정이면 not_found=True + 전체 43개 후보 반환."""
    import agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "provider", lambda: "none")
    r = tools.resolve_place_via_landmark("제주시청 근처")
    assert r["dong"] is None
    assert r["not_found"] is True
    assert len(r["candidates"]) == 43


def test_resolve_place_via_landmark_invalid_dong(monkeypatch):
    """LLM이 43개 밖의 이름을 반환해도 받아들이지 않는다."""
    import agent.llm as llm_mod
    monkeypatch.setattr(llm_mod, "provider", lambda: "gemini")
    monkeypatch.setattr(llm_mod, "chat_with_tools",
                        _fake_llm_factory("가상동_없는동"))
    r = tools.resolve_place_via_landmark("제주시청")
    assert r["dong"] is None
    assert r["not_found"] is True
