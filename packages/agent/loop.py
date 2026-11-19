"""Agent 루프.

이벤트 형식 (SSE):
- step:    진행 단계 표시
- tool:    도구 호출 요약 (사람 읽는 한 줄)
- clarify: 입력 보완 요청 → report 없이 종료
- report:  최종 리포트 (`mode`: "full"|"partial"). 문장만 실패하면 이벤트 mode가 "fallback"
- error:   서버 오류

모드
- LLM_PROVIDER=none : 규칙 루프. 숫자와 문장을 서버가 만든다.
- LLM_PROVIDER=gemini: 같은 도구 순서 후 문장 1회. 점수·신호는 서버 값을 유지한다.

운영 포인트
- 프롬프트 인젝션 격리 (<user_input> 래핑)
- 리포트 jsonschema 검증 + 수치 grounding 런타임 검사
- 사람 읽는 tool 요약 (CONTRACT 준수)
"""
from __future__ import annotations

import asyncio
import json
import re
from typing import Any, AsyncIterator

from . import llm, prompts, signals as signals_mod, tools, validation
from .log import get_logger, log_event

log = get_logger("agent.loop")

STEPS = ["의도 파악", "분석 계획", "도구 실행", "결과 검증", "리포트 작성"]
DIAGNOSE_TOOLS = [
    "get_demand", "get_supply", "get_footfall", "get_survival",
    "get_recent_openings", "get_dong_vitality", "get_tourism_trend",
    "get_trend", "score_risk",
]


def _eok(krw: float) -> str:
    return f"{krw / 1e8:.2f}억 원"


def _planned_tools(dong: str | None, category: str | None, intent: str | None) -> list[str]:
    if dong and not category and intent == "category_recommend":
        return ["find_gap_category", "get_trend"]
    if category and not dong:
        return ["compare_places"]
    if dong and category:
        return list(DIAGNOSE_TOOLS)
    return []


# ---------- 가중치 ----------

def _weights_from_form(form: dict[str, Any]) -> dict[str, float]:
    w = {"tour": 20.0, "season": 15.0, "comp": 15.0,
         "demand": 15.0, "survival": 20.0, "churn": 15.0}
    risk = form.get("risk", "balanced")
    cust = form.get("customer", "any")
    if risk == "safe":
        w["tour"] += 10; w["season"] += 5; w["survival"] += 10
    elif risk == "aggressive":
        w["tour"] -= 5; w["season"] -= 5; w["demand"] += 10
    if cust == "tourist":
        w["tour"] = max(5.0, w["tour"] - 15)
    elif cust == "local":
        w["tour"] += 10
    return w


# ---------- 사람-읽는 tool 요약 (CONTRACT) ----------

def _summarize(name: str, result: dict[str, Any]) -> str:
    if not isinstance(result, dict):
        return "ok"
    if "error" in result:
        return f"err: {str(result['error'])[:100]}"
    if name == "parse_intent":
        return (f"intent={result.get('intent')} "
                f"(hints={result.get('hints')})")
    if name == "resolve_place":
        dong = result.get("dong")
        if dong:
            return f"지역 확정: {dong}"
        c = result.get("candidates") or []
        if c:
            return f"지역 후보 {len(c)}건: {', '.join(c[:5])}"
        return "지역 매칭 실패"
    if name == "resolve_category":
        cat = result.get("app_category")
        if cat:
            return f"업종 확정: {cat}"
        c = result.get("candidates") or []
        return f"업종 후보 {len(c)}건" if c else "업종 매칭 실패"
    if name == "get_demand":
        if not result.get("available"):
            return f"수요 데이터 없음 ({result.get('dong')} {result.get('category')})"
        return (f"{result['dong']} {result['category']} 월평균 {_eok(result['monthly_avg_krw'])}, "
                f"관광 {result['tourism_ratio']*100:.1f}% / 도민 {result['local_ratio']*100:.1f}%, "
                f"성수/비수 {result['season_ratio']}배")
    if name == "get_supply":
        if not result.get("available"):
            return f"D4 매핑 없음 ({result.get('category')})"
        return f"{result['dong']} {result['category']} 점포 {result['n_stores']}개 (업종 내 {result['rank']}위/{result['of']})"
    if name == "get_survival":
        if not result.get("available"):
            return f"D5에 {result.get('dong')} {result.get('category')} 이력 없음"
        y3 = result.get("survival_3y")
        diff = result.get("diff_from_overall_3y")
        if y3 is None:
            return f"{result['dong']} {result['category']} 3년 생존율 데이터 부족"
        return (f"{result['dong']} {result['category']} 3년 생존율 {y3*100:.1f}% "
                f"(n={result['n_3y']}), 업종 평균 대비 {diff*100:+.1f}%p")
    if name == "get_recent_openings":
        if not result.get("available"):
            return f"D5에 {result.get('dong')} {result.get('category')} 이력 없음"
        return (f"{result['dong']} {result['category']} 최근 {result['months']}개월 "
                f"개업 {result['opens']}/폐업 {result['closes']} (순증 {result['net']:+d}, "
                f"직전 동기 대비 {result['delta_vs_prev']:+d})")
    if name == "get_dong_vitality":
        if not result.get("available"):
            return f"D6에 {result.get('dong')} 이력 없음"
        picked = _latest_vitality_net(result)
        if picked:
            year, net = picked
            return f"{result['dong']} 사업체 생멸 {year}년 순증 {net:+d}"
        return f"{result['dong']} 생멸 기록 {len(result.get('records', []))}년"
    if name == "get_tourism_trend":
        if not result.get("available"):
            return "D9 입도객 데이터 없음"
        yoy = result.get("yoy_12m")
        return f"입도객 YoY {yoy*100:+.1f}%p, 성수/비수 {result.get('season_ratio_36m')}배"
    if name == "score_risk":
        if not result.get("available"):
            return f"{result.get('dong')} {result.get('category')} 데이터 없음"
        levels = [s["level"] for s in result["signals"]]
        emoji = {"green": "🟢", "yellow": "🟡", "red": "🔴", "unavailable": "⚪"}
        mode = result.get("mode", "full")
        vals = ", ".join(
            f"{s['name']} {s['value']}" for s in result.get("signals") or []
            if s.get("level") != "unavailable")
        return f"score={result['score']} ({mode}) · {''.join(emoji[l] for l in levels)} · {vals}"
    if name == "compare_places":
        if not result.get("available"):
            return "비교 불가"
        top = result.get("ranking", [])
        return "Top: " + ", ".join(f"{r['dong']}({r['score']})" for r in top[:3])
    if name == "render_map":
        return f"map layer={result.get('layer')} highlight={result.get('highlight')}"
    if name == "get_footfall":
        if not result.get("available"):
            return "D2 유동인구 없음"
        return (f"{result.get('dong')} 방문인구 {result.get('rank')}위/{result.get('of')}"
                f" (업종 무관 참고 {result.get('방문인구_월평균', 0):,}명)")
    if name == "find_gap_category":
        gaps = result.get("gaps") or []
        if not gaps:
            return f"{result.get('dong')} 빈틈 업종 없음"
        bits = [f"{g['category']} 수요 {g['demand_rank']}위/{g['demand_n']}"
                f" 점포 {g['n_stores']}개 ({g['store_rank']}위/{g['store_n']})"
                for g in gaps[:5]]
        return "빈틈: " + ", ".join(bits)
    if name == "get_trend":
        if not result.get("available"):
            return "D3 트렌드 없음"
        return result.get("text") or "D3 트렌드"
    if name == "plan":
        return result.get("summary") or "계획"
    return "ok"


# ---------- clarify ----------

def _clarify_category(reason: str = "업종을 알려주세요.") -> dict:
    cats = sorted(
        {c for c in tools.store.table("supply")["app_category"].unique()}
    )
    return {"type": "clarify", "question": reason, "field": "category",
            "options": [{"label": c, "value": c} for c in cats]}


def _clarify_dong(reason: str = "희망 지역을 알려주세요.") -> dict:
    meta = tools.store.table("dong_meta")
    return {"type": "clarify", "question": reason, "field": "dong",
            "options": [{"label": r["행정동명"], "value": r["행정동명"]}
                        for _, r in meta.iterrows()]}


# ---------- 리포트 조립 ----------

def _evidence_from_tools(dong: str | None, category: str | None,
                         demand: dict, supply: dict,
                         surv: dict, opens: dict, foot: dict | None = None) -> list[dict]:
    ev: list[dict] = []
    if demand.get("available"):
        ev.append({"source": "D1", "period": demand.get("period", "2018-01~2019-12"),
                   "detail": (f"{dong}·{category} 월평균 {_eok(demand['monthly_avg_krw'])} "
                              f"(관광 {demand['tourism_ratio']*100:.1f}% / 도민 {demand['local_ratio']*100:.1f}%)")})
    if supply.get("available"):
        ev.append({"source": "D4", "period": supply.get("period", "2025-09"),
                   "detail": f"{dong}·{category} 점포 {supply['n_stores']}개 (업종 내 {supply['rank']}위/{supply['of']})"})
    if surv.get("available") and surv.get("survival_3y") is not None:
        ev.append({"source": "D5", "period": surv.get("period", ""),
                   "detail": (f"{dong}·{category} 3년 생존율 {surv['survival_3y']*100:.1f}% "
                              f"(n={surv['n_3y']}), 업종 평균 대비 {surv['diff_from_overall_3y']*100:+.1f}%p")})
    if opens.get("available"):
        ev.append({"source": "D5", "period": opens.get("period", ""),
                   "detail": (f"{dong}·{category} 최근 {opens['months']}개월 "
                              f"개업 {opens['opens']}/폐업 {opens['closes']} (순증 {opens['net']:+d})")})
    if foot and foot.get("available"):
        ev.append({"source": "D2", "period": foot.get("period", tools.BASE_PERIOD),
                   "detail": (f"{dong} 방문인구 {foot.get('rank')}위/{foot.get('of')}"
                              f" (업종 무관 참고 {foot['방문인구_월평균']:,}명)")})
    return ev


# 데이터별 한계 문구 (동적 limitations 생성용)
DATASET_LIMIT_TEXT = {
    "D1": "D1 카드 매출: 데이터셋은 2021-05까지, 분석 창은 2018-01~2019-12 · 카드사 표본 영향",
    "D2": "D2 유동인구: 2021-05까지 · 월 평균 기반",
    "D3": "D3 업종별 카드 이용: 제주 전체 단위 (지역 구분 없음)",
    "D4": "D4 상가 정보: 2025-09 스냅샷 (실시간 상태 아님)",
    "D5": "D5 음식점 인허가 기준: 실제 영업 상태와 차이 가능",
    "D9": "D9 입도객: 제주 전체 단위 (지역 구분 없음)",
}


def _latest_vitality_net(vitality: dict | None) -> tuple[str, int] | None:
    """순증이 비어 있지 않은 가장 최근 연도. 없으면 None."""
    if not vitality or not vitality.get("available"):
        return None
    best: tuple[int, int] | None = None
    for rec in vitality.get("records") or []:
        net = rec.get("순증")
        if net is None:
            continue
        try:
            if net != net:
                continue
            value = int(net)
            year = int(rec.get("year"))
        except (TypeError, ValueError):
            continue
        if best is None or year >= best[0]:
            best = (year, value)
    if best is None:
        return None
    return str(best[0]), best[1]


def _worst_red(signals: list[dict]) -> dict | None:
    """빨강 중 리스크 백분위가 가장 큰 신호. 관광 의존도가 빨강이면 그것을 고른다."""
    reds = [s for s in signals if s.get("level") == "red"]
    tour = next((s for s in reds if s.get("name") == "관광 의존도"), None)
    if tour:
        return tour
    best = None
    best_risk = -1.0
    for s in reds:
        spec = signals_mod.by_name(s.get("name", ""))
        pct = s.get("percentile")
        if spec is None or pct is None:
            risk = 0.0
        elif spec.direction == "low_red":
            risk = 1 - float(pct)
        else:
            risk = float(pct)
        if risk >= best_risk:
            best = s
            best_risk = risk
    return best


def _enforce_server_fields(report: dict, form: dict, constraints: dict | None) -> dict:
    """LLM 리포트에 서버 산출 필드를 강제 주입.

    - active_signals/total_signals: signals 배열에서 재계산
    - score / confidence: 신뢰도 규칙 재적용 (active<3 또는 수요 계열 없음)
    - limitations: 신호의 data ID 사용/누락에서 동적 생성
    - form_applied: 폼+constraints 병합
    """
    signals = report.get("signals") or []
    active = [s for s in signals if s.get("level") != "unavailable"]
    total = len(signals)
    report["active_signals"] = len(active)
    report["total_signals"] = total

    demand_family_names = signals_mod.demand_family()
    has_demand = any(s["name"] in demand_family_names for s in active)

    if len(active) < tools.MIN_SIGNALS_FOR_SCORE:
        report["score"] = None
        report["confidence"] = "low"
        report["confidence_reason"] = f"가용 신호 {len(active)}/{total} < {tools.MIN_SIGNALS_FOR_SCORE}"
    elif not has_demand:
        report["score"] = None
        report["confidence"] = "low"
        report["confidence_reason"] = "수요 계열(수요 규모·유동 수요) 신호 없음 — 경쟁 밀도만으로 추천 금지"
    else:
        report.setdefault("confidence", "normal")

    # 동적 limitations: 신호 → SIGNAL_SPECS 로 data ID 추출
    ids_used: set[str] = set()
    ids_missing: dict[str, str] = {}
    for s in signals:
        spec = signals_mod.by_name(s.get("name", ""))
        if spec is None:
            continue
        if s.get("level") == "unavailable":
            for d in spec.requires:
                ids_missing.setdefault(d, s.get("reason", "데이터 없음"))
        else:
            for d in spec.requires:
                ids_used.add(d)
    lim: list[str] = []
    for d in sorted(ids_used):
        if d in DATASET_LIMIT_TEXT:
            lim.append(DATASET_LIMIT_TEXT[d])
    for d, reason in ids_missing.items():
        lim.append(f"{d} 미가용: {reason}")
    report["limitations"] = lim

    # form_applied
    tgt = report.get("target") or {}
    c = dict(constraints or {})
    report["form_applied"] = {
        "category": tgt.get("category"),
        "dong": tgt.get("dong"),
        "customer": c.get("customer") or form.get("customer", "any"),
        "ages": c.get("ages") or form.get("ages") or [],
        "risk": form.get("risk", "balanced"),
    }
    if c:
        report["constraints"] = c
    return report


def _dynamic_limitations(risk: dict, extra: list[str] | None = None) -> list[str]:
    """score_risk의 data_ids_used / data_ids_missing로 한계 문구를 동적 생성.

    - used된 데이터 ID 각각 → DATASET_LIMIT_TEXT
    - missing된 ID → '{ID} 미가용: {사유}'
    """
    out: list[str] = []
    for d in risk.get("data_ids_used") or []:
        if d in DATASET_LIMIT_TEXT:
            out.append(DATASET_LIMIT_TEXT[d])
    for d, reason in (risk.get("data_ids_missing") or {}).items():
        out.append(f"{d} 미가용: {reason}")
    for e in extra or []:
        out.append(e)
    # 중복 제거 (순서 유지)
    seen: set[str] = set()
    uniq = []
    for s in out:
        if s not in seen:
            seen.add(s); uniq.append(s)
    return uniq


def _monthly_pattern_payload(total: dict, tourism: dict | None) -> dict:
    """1~12월 전체 매출과 관광객 매출. 없는 달은 0."""
    tour = tourism or {}
    return {
        "labels": [f"{m}월" for m in range(1, 13)],
        "values": [int(total.get(m, 0)) for m in range(1, 13)],
        "tourism_values": [int(tour.get(m, 0)) for m in range(1, 13)],
    }


_LAYERS = {"demand", "tourism", "supply", "footfall", "survival"}
_OPEN_INTENTS = {"category_recommend", "place_recommend", "clarify"}
_PLAN_INTENTS = _OPEN_INTENTS | {"diagnose"}


def _map_layer(signals: list[dict], model_layer: str | None) -> str:
    """생존 빨강, 관광 빨강 순으로 서버가 우선한다. 둘 다 아니면 모델 레이어."""
    red_names = [s["name"] for s in signals if s.get("level") == "red"]
    if "생존 리스크" in red_names:
        return "survival"
    if "관광 의존도" in red_names:
        return "tourism"
    if model_layer in _LAYERS:
        return model_layer
    return "demand"


def _alt_from_rank(row: dict, why: str) -> dict:
    alt = {
        "dong": row["dong"],
        "score": row.get("score"),
        "confidence": row.get("confidence", "normal"),
        "active_signals": row.get("active_signals"),
        "total_signals": row.get("total_signals"),
        "why": why,
    }
    if row.get("tour_value"):
        alt["tour_value"] = row["tour_value"]
    if row.get("survival_value"):
        alt["survival_value"] = row["survival_value"]
    return alt


def _build_report(form: dict, dong: str | None, category: str | None,
                  demand: dict, supply: dict, surv: dict, opens: dict,
                  risk: dict, alts: list[dict], foot: dict | None = None,
                  constraints: dict | None = None,
                  form_applied: dict | None = None,
                  trend: dict | None = None,
                  vitality: dict | None = None,
                  tourism: dict | None = None,
                  model_layer: str | None = None) -> dict:
    signals = risk.get("signals", []) if risk.get("available") else []
    score = risk.get("score") if risk.get("available") else None
    confidence = risk.get("confidence", "normal")
    unavail_count = sum(1 for s in signals if s["level"] == "unavailable")
    active_count = len(signals) - unavail_count
    mode = "partial" if unavail_count > 0 else "full"

    raw_cat = (form.get("category") or "").strip()
    partial_lead = ""
    if confidence == "low":
        partial_lead = f"판단 보류 (가용 신호 {active_count}/{len(signals)}) · 참고용. "
    elif mode == "partial" and unavail_count > 0:
        missing_names = [s["name"] for s in signals if s["level"] == "unavailable"]
        if any(n in missing_names for n in ("관광 의존도", "수요 규모", "계절 변동성")):
            partial_lead = "카드 매출 데이터가 없어 수요는 판단하지 못했어요. "

    vitality_net = _latest_vitality_net(vitality)
    if dong and category and risk.get("available"):
        if confidence == "low" or score is None:
            summary = f"{partial_lead}{dong}·{category} — 신호가 부족해 종합 점수를 보류했습니다."
        else:
            worst = _worst_red(signals)
            season = next((s for s in signals if s.get("name") == "계절 변동성"
                           and s.get("level") != "unavailable"), None)
            season_months = None
            if season:
                season_months = re.fullmatch(
                    r"(\d{1,2})월/(\d{1,2})월 (\d+\.\d+배)", str(season.get("value") or ""))
            if worst and worst.get("name") == "관광 의존도" and season_months:
                peak, low, ratio = season_months.groups()
                caution = (f"관광 의존도 {worst['value']}이고, "
                           f"매출은 {peak}월이 {low}월의 {ratio}라 성수기 착시 위험이 큽니다")
            elif worst and worst.get("name") == "관광 의존도":
                caution = f"관광 의존도 {worst['value']} 때문에 성수기 착시 위험이 큽니다"
            elif worst:
                caution = f"{worst['name']} {worst['value']}이 가장 큰 주의 신호입니다"
            else:
                caution = "데이터상 유리한 신호가 많습니다"
            summary = (f"{partial_lead}{dong}에서 {category} 창업은 종합 {score}점이고, {caution}.")
            if vitality_net:
                year, net = vitality_net
                summary += f" {dong} 사업체 생멸 {year}년 순증 {net:+d}은 업종과 무관한 참고입니다."
    elif category and not dong:
        summary = f"{category} 업종 상위 지역 Top {len(alts)}을 제안."
    elif raw_cat and not category:
        summary = f"'{raw_cat}'은 지원 업종에 없습니다. 지원 업종 중 선택해주세요."
    elif dong and not category:
        summary = f"업종이 모호합니다. {dong} 지역에서 어떤 업종을 검토할지 선택하세요."
    else:
        summary = "입력이 모호함. 업종과 지역을 확정해 주세요."

    evidence = _evidence_from_tools(dong, category, demand, supply, surv, opens, foot)
    trend_text = None
    if trend and trend.get("available") and trend.get("text"):
        trend_text = trend["text"]
        evidence.append({"source": "D3", "period": trend.get("period", ""),
                         "detail": trend_text})
    if vitality and vitality.get("available"):
        if vitality_net:
            year, net = vitality_net
            detail = f"{dong} 사업체 생멸 {year}년 순증 {net:+d} (업종 무관 참고)"
        else:
            detail = f"{dong} 사업체 생멸 순증 자료 없음 (업종 무관 참고)"
        evidence.append({
            "source": "D6",
            "period": vitality.get("period", ""),
            "detail": detail,
        })
    extra_limits = []
    if tourism is not None and not tourism.get("available"):
        extra_limits.append("D9 입도객 없음")
    limitations = _dynamic_limitations(risk, extra_limits)

    highlight = [dong] if dong else []
    for a in alts:
        if a.get("dong") not in highlight:
            highlight.append(a["dong"])

    layer = _map_layer(signals, model_layer)

    report = {
        "summary": summary,
        "target": {"dong": dong, "category": category},
        "signals": signals,
        "score": score,                        # None 가능
        "confidence": confidence,              # "normal" | "low"
        "active_signals": active_count,
        "total_signals": len(signals),
        "alternatives": alts, "trend": trend_text,
        "evidence": evidence, "limitations": limitations,
        "map": {"layer": layer, "highlight": highlight},
        "mode": mode,
    }
    if constraints:
        report["constraints"] = constraints
    if form_applied:
        report["form_applied"] = form_applied

    # 월별 패턴 (근거 패널 차트용) — get_demand 결과에서 추출
    mp = demand.get("monthly_pattern") if demand.get("available") else None
    if mp:
        report["monthly_pattern"] = _monthly_pattern_payload(
            mp, demand.get("monthly_tourism_pattern"))
    return report


async def _run_gap(form: dict[str, Any], dong: str,
                   constraints: dict[str, Any],
                   model_layer: str | None = None) -> AsyncIterator[dict[str, Any]]:
    """지역만 있고 업종 추천 의도일 때 빈틈 업종 리포트."""

    async def step(i: int, status: str):
        return {"type": "step", "index": i, "name": STEPS[i], "status": status}

    yield await step(2, "running")
    gap = tools.find_gap_category(dong)
    yield {"type": "tool", "name": "find_gap_category", "args": {"dong": dong},
           "summary": _summarize("find_gap_category", gap)}
    gaps = gap.get("gaps") or []
    trend = {"available": False}
    if gaps:
        trend = tools.get_trend(gaps[0]["category"])
        yield {"type": "tool", "name": "get_trend",
               "args": {"category": gaps[0]["category"]},
               "summary": _summarize("get_trend", trend)}
    yield await step(2, "done")
    yield await step(3, "running")
    yield await step(3, "done")
    yield await step(4, "running")

    alts = [{
        "dong": g["category"],
        "score": int(round(g["gap"] * 100)),
        "why": (f"수요 {g['demand_rank']}위/{g['demand_n']} · "
                f"점포 {g['n_stores']}개 ({g['store_rank']}위/{g['store_n']}). "
                "수요에 비해 점포가 적다."),
    } for g in gaps]
    evidence: list[dict] = []
    if gaps:
        g0 = gaps[0]
        evidence.append({
            "source": "D1", "period": tools.BASE_PERIOD,
            "detail": f"{dong}·{g0['category']} 수요 {g0['demand_rank']}위/{g0['demand_n']}",
        })
        evidence.append({
            "source": "D4", "period": gap.get("as_of") or "2025-09",
            "detail": f"{dong}·{g0['category']} 점포 {g0['n_stores']}개 ({g0['store_rank']}위/{g0['store_n']})",
        })
    if trend.get("available") and trend.get("text"):
        evidence.append({"source": "D3", "period": trend.get("period", ""),
                         "detail": trend["text"]})
    report = {
        "summary": f"{dong}에서 수요는 높은데 점포는 적은 업종 {len(alts)}개를 골랐습니다.",
        "target": {"dong": dong, "category": None},
        "signals": [],
        "score": None,
        "confidence": "normal",
        "active_signals": 0,
        "total_signals": 0,
        "alternatives": alts,
        "trend": trend.get("text") if trend.get("available") else None,
        "evidence": evidence,
        "limitations": [
            DATASET_LIMIT_TEXT["D1"],
            DATASET_LIMIT_TEXT["D4"],
            "D9 입도객 없음",
        ],
        "map": {"layer": _map_layer([], model_layer), "highlight": [dong]},
        "mode": "full",
        "focus": "gap",
        "form_applied": {
            "category": None,
            "dong": dong,
            "customer": constraints.get("customer") or form.get("customer", "any"),
            "ages": constraints.get("ages") or form.get("ages") or [],
            "risk": form.get("risk", "balanced"),
        },
    }
    yield await step(4, "done")
    yield {"type": "report", "report": report, "mode": report["mode"]}


# ---------- fallback 루프 ----------

async def _run_fallback(form: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """LLM 없이 도구만으로 리포트 또는 clarify 응답."""

    async def step(i: int, status: str):
        return {"type": "step", "index": i, "name": STEPS[i], "status": status}

    weights = _weights_from_form(form)

    yield await step(0, "running")

    text_dong = (form.get("dong") or "").strip()
    text_cat = (form.get("category") or "").strip()
    question = (form.get("question") or "").strip()

    # parse_intent: 폼이 비어 있거나 자연어가 있으면 호출
    hints: dict[str, Any] = {}
    constraints: dict[str, Any] = {}
    intent: dict[str, Any] = {}
    if question and (not text_cat or not text_dong):
        intent = tools.parse_intent(question)
        yield {"type": "tool", "name": "parse_intent",
               "args": {"text": question}, "summary": _summarize("parse_intent", intent)}
        hints = intent.get("hints") or {}
        constraints = intent.get("constraints") or {}

    # resolve category
    if text_cat:
        r_cat = tools.resolve_category(text_cat)
    elif hints.get("category"):
        r_cat = tools.resolve_category(hints["category"])
    else:
        r_cat = {"app_category": None, "candidates": [], "not_found": True,
                 "source": "mapping", "period": "", "as_of": "",
                 "note": "입력 없음"}
    yield {"type": "tool", "name": "resolve_category",
           "args": {"text": text_cat or hints.get("category") or ""},
           "summary": _summarize("resolve_category", r_cat)}

    # resolve place: 문자열 매칭 → 실패시 landmark LLM 보조
    place_text = text_dong or hints.get("dong") or ""
    # question에 명시적 지역이 안 잡혔으면 전체 질문을 landmark로 시도
    landmark_text = place_text or (question if question and not hints.get("dong") else "")
    if place_text:
        r_place = tools.resolve_place(place_text)
    else:
        r_place = {"dong": None, "candidates": [], "not_found": True,
                   "source": "D4", "period": "", "as_of": "", "note": "입력 없음"}
    yield {"type": "tool", "name": "resolve_place",
           "args": {"text": place_text},
           "summary": _summarize("resolve_place", r_place)}

    if r_place.get("not_found") and not r_place.get("candidates") and landmark_text:
        r_landmark = tools.resolve_place_via_landmark(landmark_text)
        yield {"type": "tool", "name": "resolve_place_via_landmark",
               "args": {"text": landmark_text},
               "summary": _summarize("resolve_place_via_landmark", r_landmark)}
        if r_landmark.get("dong"):
            r_place = r_landmark

    dong = r_place.get("dong")
    category = r_cat.get("app_category")
    intent_name = intent.get("intent")
    model_layer: str | None = None
    # 업종·지역이 질문 때문에 비어 의도가 갈릴 때만 계획 1회. 확정 진단은 호출하지 않는다.
    if (llm.provider() != "none" and question and (not text_cat or not text_dong)
            and intent_name in _OPEN_INTENTS):
        plan = _ask_plan(question)
        if plan:
            chosen = plan.get("intent")
            if chosen in _PLAN_INTENTS:
                intent_name = chosen
            if plan.get("map_layer") in _LAYERS:
                model_layer = plan["map_layer"]
    yield await step(0, "done")

    # ② 계획 — 이번 실행에서 호출할 도구를 먼저 보여 준다
    planned = _planned_tools(dong, category, intent_name)
    yield await step(1, "running")
    if planned:
        yield {"type": "tool", "name": "plan",
               "args": {"tools": planned},
               "summary": "계획: " + ", ".join(planned)}
    yield await step(1, "done")

    # 라우팅
    if not category and not dong:
        if r_cat.get("candidates"):
            yield _clarify_category("업종이 모호합니다. 아래 중 선택해 주세요.")
        else:
            yield _clarify_category("어떤 업종을 생각하세요?")
        return
    if not category and intent_name == "category_recommend":
        async for ev in _run_gap(form, dong, constraints, model_layer):
            yield ev
        return
    if not category:
        yield _clarify_category(f"'{dong}' 지역에서 어떤 업종을 검토할지 선택해 주세요.")
        return

    # 지역 없음 + 업종 있음 → place_recommend
    place_recommend = (dong is None)

    # ③ 도구 실행 (context에 constraints 전달)
    yield await step(2, "running")
    ctx = {
        "ages": constraints.get("ages") or form.get("ages") or [],
        "customer": constraints.get("customer") or form.get("customer"),
    }
    demand = supply = surv = opens = {"available": False}
    foot: dict = {"available": False}
    trend: dict = {"available": False}
    vitality: dict = {"available": False}
    tourism: dict = {"available": False}
    risk = {"available": False}
    alts: list[dict] = []

    if place_recommend:
        cmp_res = tools.compare_places(category, top_k=3, weights=weights, context=ctx)
        yield {"type": "tool", "name": "compare_places",
               "args": {"category": category, "top_k": 3},
               "summary": _summarize("compare_places", cmp_res)}
        if cmp_res.get("available"):
            alts = [_alt_from_rank(
                r, f"가용 신호 {r.get('active_signals','?')}/{r.get('total_signals','?')} 중 green "
                   f"{sum(1 for v in r['signals'].values() if v=='green')}개")
                    for r in cmp_res["ranking"]]
        trend = tools.get_trend(category)
        yield {"type": "tool", "name": "get_trend",
               "args": {"category": category}, "summary": _summarize("get_trend", trend)}
    else:
        demand = tools.get_demand(dong, category)
        yield {"type": "tool", "name": "get_demand",
               "args": {"dong": dong, "category": category},
               "summary": _summarize("get_demand", demand)}
        supply = tools.get_supply(dong, category)
        yield {"type": "tool", "name": "get_supply",
               "args": {"dong": dong, "category": category},
               "summary": _summarize("get_supply", supply)}
        foot = tools.get_footfall(dong, ages=ctx.get("ages"))
        yield {"type": "tool", "name": "get_footfall",
               "args": {"dong": dong, "ages": ctx.get("ages")},
               "summary": _summarize("get_footfall", foot)}
        surv = tools.get_survival(dong, category)
        yield {"type": "tool", "name": "get_survival",
               "args": {"dong": dong, "category": category},
               "summary": _summarize("get_survival", surv)}
        opens = tools.get_recent_openings(dong, category, months=24)
        yield {"type": "tool", "name": "get_recent_openings",
               "args": {"dong": dong, "category": category, "months": 24},
               "summary": _summarize("get_recent_openings", opens)}
        tourism = tools.get_tourism_trend()
        yield {"type": "tool", "name": "get_tourism_trend",
               "args": {}, "summary": _summarize("get_tourism_trend", tourism)}
        vitality = tools.get_dong_vitality(dong)
        yield {"type": "tool", "name": "get_dong_vitality",
               "args": {"dong": dong}, "summary": _summarize("get_dong_vitality", vitality)}
        trend = tools.get_trend(category)
        yield {"type": "tool", "name": "get_trend",
               "args": {"category": category}, "summary": _summarize("get_trend", trend)}
        risk = tools.score_risk(dong, category, weights=weights, context=ctx)
        yield {"type": "tool", "name": "score_risk",
               "args": {"dong": dong, "category": category, "weights": weights, "context": ctx},
               "summary": _summarize("score_risk", risk)}
    yield await step(2, "done")

    yield await step(3, "running")
    red = sum(1 for s in risk.get("signals", []) if s["level"] == "red")
    if dong and category and red >= 2 and not alts:
        cmp_res = tools.compare_places(category, top_k=3, weights=weights,
                                        exclude=[dong], context=ctx)
        yield {"type": "tool", "name": "compare_places",
               "args": {"category": category, "top_k": 3, "exclude": [dong]},
               "summary": _summarize("compare_places", cmp_res)}
        if cmp_res.get("available"):
            alts = [_alt_from_rank(r, "원 선택지보다 리스크 신호가 적음")
                    for r in cmp_res["ranking"]]
    yield await step(3, "done")

    # ⑤ 리포트 + form_applied
    yield await step(4, "running")
    form_applied = {
        "category": category,
        "dong": dong,
        "customer": constraints.get("customer") or form.get("customer", "any"),
        "ages": constraints.get("ages") or form.get("ages") or [],
        "risk": form.get("risk", "balanced"),
    }
    report = _build_report(form, dong, category, demand, supply, surv, opens, risk, alts,
                           foot=foot, constraints=constraints, form_applied=form_applied,
                           trend=trend, vitality=vitality, tourism=tourism,
                           model_layer=model_layer)
    yield await step(4, "done")
    yield {"type": "report", "report": report, "mode": report.get("mode", "fallback")}


# ---------- LLM 루프 ----------

def _narrative_payload(report: dict) -> str:
    """모델에 넘기는 서버 결과. 점수와 신호는 읽기 전용이다."""
    payload = {
        "target": report.get("target"),
        "score": report.get("score"),
        "signals": [
            {"name": s.get("name"), "value": s.get("value"), "level": s.get("level"),
             "reason": s.get("reason"), "as_of": s.get("as_of")}
            for s in report.get("signals") or []
        ],
        "alternatives": [
            {"dong": a.get("dong"), "score": a.get("score")}
            for a in report.get("alternatives") or []
        ],
        "evidence": [
            {"source": e.get("source"), "detail": e.get("detail")}
            for e in report.get("evidence") or []
        ],
    }
    return json.dumps(payload, ensure_ascii=False)


def _sentence_haystack(report: dict, tool_summaries: list[str]) -> str:
    parts = list(tool_summaries)
    score = report.get("score")
    parts.append(str(score))
    if isinstance(score, int):
        parts.append(f"{score}점")
    for s in report.get("signals") or []:
        parts.append(f"{s.get('value', '')} {s.get('reason', '')} {s.get('as_of', '')}")
    for e in report.get("evidence") or []:
        parts.append(str(e.get("detail", "")))
    for a in report.get("alternatives") or []:
        parts.append(f"{a.get('dong', '')} {a.get('score', '')}점 {a.get('why', '')} "
                     f"{a.get('tour_value', '')} {a.get('survival_value', '')}")
    return " ".join(parts)


def _sentence_ok(text: str, haystack: str) -> bool:
    return not {n for n in validation.extract_numbers(text) if n not in haystack}


def _ask_narrative(report: dict, tool_summaries: list[str]) -> tuple[str, dict[str, str]] | None:
    """문장 1회. 실패·빈 응답·서버에 없는 숫자면 None."""
    messages = [
        {"role": "system", "content": prompts.SYSTEM_PROMPT},
        {"role": "user", "content": _narrative_payload(report)},
    ]
    try:
        result = llm.chat_with_tools(messages, [])
    except Exception as e:  # noqa: BLE001
        log_event(log, 40, "llm_narrative_failed", error=f"{type(e).__name__}: {e}"[:200])
        return None
    parsed = _parse_report_json(result.get("text") or "")
    if not parsed:
        return None
    summary = parsed.get("summary")
    if not isinstance(summary, str) or not summary.strip():
        return None
    haystack = _sentence_haystack(report, tool_summaries)
    if not _sentence_ok(summary, haystack):
        log_event(log, 30, "llm_narrative_stray")
        return None
    whys: dict[str, str] = {}
    for item in parsed.get("alternatives") or []:
        if not isinstance(item, dict):
            continue
        dong = item.get("dong")
        why = item.get("why")
        if (isinstance(dong, str) and isinstance(why, str) and why.strip()
                and _sentence_ok(why, haystack)):
            whys[dong] = why.strip()
    return summary.strip(), whys


def _mark_rule_sentence(report: dict) -> dict:
    lim = list(report.get("limitations") or [])
    note = "문장은 규칙으로 작성"
    if note not in lim:
        lim.append(note)
    report["limitations"] = lim
    report["narrative"] = "rule"
    return report


async def _run_llm(form: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """도구는 규칙 루프와 같은 순서. 모델은 그 결과로 문장만 한 번 쓴다."""
    tool_summaries: list[str] = []
    report_ev: dict | None = None
    async for ev in _run_fallback(form):
        if ev.get("type") == "tool":
            tool_summaries.append(ev.get("summary") or "")
        if ev.get("type") == "report":
            report_ev = ev
            continue
        yield ev
    if report_ev is None:
        return

    report = report_ev["report"]
    adopted = await asyncio.to_thread(_ask_narrative, report, tool_summaries)
    if adopted is None:
        _mark_rule_sentence(report)
        yield {"type": "report", "report": report, "mode": "fallback"}
        return

    summary, whys = adopted
    report["summary"] = summary
    for alt in report.get("alternatives") or []:
        why = whys.get(alt.get("dong"))
        if why:
            alt["why"] = why
    yield {"type": "report", "report": report, "mode": "llm"}


def _parse_json_object(text: str) -> dict | None:
    if not text:
        return None
    stripped = text.strip()
    if stripped.startswith("```"):
        stripped = stripped.split("```", 2)[1]
        if stripped.lstrip().startswith("json"):
            stripped = stripped.lstrip()[4:]
    try:
        obj = json.loads(stripped.strip())
    except json.JSONDecodeError:
        start = stripped.find("{")
        end = stripped.rfind("}")
        if start < 0 or end < start:
            return None
        try:
            obj = json.loads(stripped[start:end + 1])
        except json.JSONDecodeError:
            return None
    return obj if isinstance(obj, dict) else None


def _parse_report_json(text: str) -> dict | None:
    obj = _parse_json_object(text)
    return obj if isinstance(obj, dict) and "summary" in obj else None


def _ask_plan(question: str) -> dict | None:
    """비어 있는 자연어의 의도만. 실패하면 None이고 parse_intent를 유지한다."""
    messages = [
        {"role": "system", "content": prompts.PLAN_PROMPT},
        {"role": "user", "content": question},
    ]
    try:
        result = llm.chat_with_tools(messages, [])
    except Exception as e:  # noqa: BLE001
        log_event(log, 40, "llm_plan_failed", error=f"{type(e).__name__}: {e}"[:200])
        return None
    return _parse_json_object(result.get("text") or "")


async def run(form: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    if llm.provider() == "none":
        async for ev in _run_fallback(form):
            yield ev
    else:
        async for ev in _run_llm(form):
            yield ev
