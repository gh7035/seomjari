"""Agent 도구. 모든 수치 계산은 여기서만 한다 (LLM은 계산하지 않음).

모든 도구는 dict를 반환하며 `source`, `period`, `note` 필드를 포함한다.
"""
from __future__ import annotations

from typing import Any

BASE_PERIOD = "2018-01~2019-12"


def resolve_place(text: str) -> dict[str, Any]:
    """'애월', '노형' 같은 표현 → 표준 행정동명과 후보 목록."""
    raise NotImplementedError


def resolve_category(text: str) -> dict[str, Any]:
    """'카페', '커피숍' 같은 표현 → app_category와 후보 목록."""
    raise NotImplementedError


def get_demand(dong: str, category: str) -> dict[str, Any]:
    """월평균 매출, 관광 비중, 12개월 패턴, 연령대 비중. source=D1."""
    raise NotImplementedError


def get_supply(dong: str, category: str) -> dict[str, Any]:
    """점포 수와 업종 내 순위. source=D4."""
    raise NotImplementedError


def score_risk(dong: str, category: str, weights: dict[str, float] | None = None) -> dict[str, Any]:
    """지표 4개 값·백분위·신호등과 종합 점수."""
    raise NotImplementedError


def get_footfall(dong: str) -> dict[str, Any]:
    """거주·근무·방문 인구 월평균. source=D2."""
    raise NotImplementedError


def compare_places(category: str, dongs: list[str] | None = None, top_k: int = 3,
                   weights: dict[str, float] | None = None) -> dict[str, Any]:
    """업종 기준 지역 순위."""
    raise NotImplementedError


def find_gap_category(dong: str) -> dict[str, Any]:
    """수요 대비 공급이 부족한 업종 Top 5."""
    raise NotImplementedError


def get_trend(category: str) -> dict[str, Any]:
    """연도별 소비와 증감률. source=D3."""
    raise NotImplementedError


def render_map(layer: str, category: str | None = None, highlight: list[str] | None = None) -> dict[str, Any]:
    """UI에 지도 상태를 지시한다 (데이터 계산 없음)."""
    return {"layer": layer, "category": category, "highlight": highlight or []}


REGISTRY = {
    f.__name__: f
    for f in [
        resolve_place, resolve_category, get_demand, get_supply, score_risk,
        get_footfall, compare_places, find_gap_category, get_trend, render_map,
    ]
}
