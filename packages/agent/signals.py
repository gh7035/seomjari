"""신호 레지스트리 — 데이터 기반 선언.

각 신호는 요구 데이터 ID, 수요 계열 여부, 방향(높을수록 red / 낮을수록 red)을 메타로 가진다.
컴퓨트는 요구 데이터가 준비돼 있을 때만 호출되며, 실패하면 unavailable 신호를 반환한다.
score_risk는 이 레지스트리를 순회하여 signals를 만들고, 가용 신호 수와 수요 계열 존재
여부로 점수의 신뢰도를 결정한다.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable

import pandas as pd

from . import store

BASE_START = "2018-01"
BASE_END = "2019-12"


# ---------- SignalSpec ----------

@dataclass(frozen=True)
class SignalSpec:
    name: str              # UI 표시명
    key: str               # 가중치 키
    family: str            # demand | competition | seasonality | tourism | survival | lifecycle
    requires: tuple[str, ...]  # 요구 데이터 ID (D1/D2/D4/D5/D9)
    direction: str         # "high_red" | "low_red"


SIGNAL_SPECS: tuple[SignalSpec, ...] = (
    SignalSpec("관광 의존도", "tour", "tourism", ("D1",), "high_red"),
    SignalSpec("계절 변동성", "season", "seasonality", ("D1",), "high_red"),
    SignalSpec("수요 규모", "demand", "demand", ("D1",), "low_red"),
    SignalSpec("유동 수요", "footfall", "demand", ("D2",), "low_red"),
    SignalSpec("경쟁 밀도", "comp", "competition", ("D4",), "high_red"),
    SignalSpec("생존 리스크", "survival", "survival", ("D5",), "low_red"),
    SignalSpec("최근 개폐업", "churn", "lifecycle", ("D5",), "high_red"),
)


def by_name(name: str) -> SignalSpec | None:
    for s in SIGNAL_SPECS:
        if s.name == name:
            return s
    return None


# ---------- 계열 집합 ----------

def demand_family() -> set[str]:
    return {s.name for s in SIGNAL_SPECS if s.family == "demand"}


# ---------- 공용 유틸 ----------

def _base_slice(df: pd.DataFrame, col: str = "년월") -> pd.DataFrame:
    return df[(df[col] >= BASE_START) & (df[col] <= BASE_END)]


def _percentile(value: float, series: pd.Series) -> float:
    s = series.dropna()
    if len(s) == 0:
        return 0.5
    return float((s < value).mean())


def _level_from_pct(pct: float, direction: str) -> str:
    """pct(0~1, 높을수록 "나쁨 축의 상위")에서 레벨 산출.

    direction=high_red: 값이 높을수록 red
    direction=low_red : 값이 낮을수록 red → pct를 반전
    """
    if direction == "low_red":
        pct = 1 - pct
    if pct < 1 / 3:
        return "green"
    if pct < 2 / 3:
        return "yellow"
    return "red"


def _registry_as_of(id_: str) -> str:
    import json
    path = store.data_dir() / "registry.json"
    if not path.exists():
        return ""
    with path.open(encoding="utf-8") as f:
        for r in json.load(f):
            if r["id"] == id_:
                return r.get("as_of", "")
    return ""


def _unavailable(spec: SignalSpec, reason: str) -> dict:
    as_of = _registry_as_of(spec.requires[0]) if spec.requires else ""
    return {"name": spec.name, "value": "N/A", "level": "unavailable",
            "percentile": None, "reason": reason, "as_of": as_of,
            "spec": spec}


# ---------- 각 신호 compute ----------

def _ensure_tables(ids: tuple[str, ...]) -> dict[str, bool]:
    mapping = {"D1": "demand_monthly", "D2": "footfall_monthly",
               "D4": "supply", "D5": "survival"}
    return {i: store.has_optional(mapping.get(i, "")) if i != "D4"
             else (store.data_dir() / "supply.parquet").exists()
            for i in ids}


def _demand_slice(category: str) -> pd.DataFrame:
    d = store.table("demand_monthly")
    base = _base_slice(d)
    return base[base["app_category"] == category]


def compute_tour(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    cat = _demand_slice(category)
    if cat.empty or dong not in cat["dong"].unique():
        return _unavailable(spec, "D1에 해당 지역·업종 카드 데이터 없음")
    g = cat.groupby("dong")
    tourism_series = (g["이용금액_관광개별"].sum() + g["이용금액_관광단체"].sum()) / g["이용금액_합계"].sum()
    v = float(tourism_series.loc[dong])
    p = _percentile(v, tourism_series)
    return {"name": spec.name, "value": f"{v*100:.1f}%",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": "관광개별+관광단체 비중",
            "as_of": _registry_as_of("D1"), "spec": spec, "raw": v}


def compute_season(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    cat = _demand_slice(category)
    if cat.empty or dong not in cat["dong"].unique():
        return _unavailable(spec, "D1에 해당 지역·업종 카드 데이터 없음")
    c2 = cat.assign(m=cat["년월"].str[5:7].astype(int))
    ser = (c2.groupby(["dong", "m"])["이용금액_합계"].mean()
           .groupby(level=0).agg(lambda s: s.max() / s.min() if s.min() > 0 else None))
    if dong not in ser.index or pd.isna(ser.loc[dong]):
        return _unavailable(spec, "월별 분포 계산 불가")
    v = float(ser.loc[dong])
    p = _percentile(v, ser)
    return {"name": spec.name, "value": f"{v:.2f}배",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": "최고월/최저월 매출 비율",
            "as_of": _registry_as_of("D1"), "spec": spec, "raw": v}


def compute_demand(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    cat = _demand_slice(category)
    if cat.empty or dong not in cat["dong"].unique():
        return _unavailable(spec, "D1에 해당 지역·업종 카드 데이터 없음")
    g = cat.groupby("dong")
    monthly_avg = g["이용금액_합계"].sum() / g["년월"].nunique()
    v = float(monthly_avg.loc[dong])
    p = _percentile(v, monthly_avg)
    rank = int((monthly_avg > v).sum() + 1)
    return {"name": spec.name, "value": f"업종 내 {rank}위 / {len(monthly_avg)}",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": "기준 기간 월평균 이용금액 동별 순위",
            "as_of": _registry_as_of("D1"), "spec": spec, "raw": v}


def compute_footfall(dong: str, _category: str, spec: SignalSpec, ctx: dict) -> dict:
    """D2 방문인구. 업종 무관. constraints.ages가 있고 D2에 연령 컬럼이 있으면 필터링."""
    if not store.has_optional("footfall_monthly"):
        return _unavailable(spec, "D2 유동인구 데이터 없음")
    foot = store.table("footfall_monthly")
    ages = ctx.get("ages") or []
    if ages and "연령대" in foot.columns:
        foot = foot[foot["연령대"].isin(ages)]
    g = foot.groupby("dong")["방문인구"].mean()
    if dong not in g.index:
        return _unavailable(spec, "해당 행정동 유동인구 데이터 없음")
    v = float(g.loc[dong])
    p = _percentile(v, g)
    rank = int((g > v).sum() + 1)
    age_note = f" (연령 {','.join(ages)})" if ages and "연령대" in foot.columns else ""
    return {"name": spec.name,
            "value": f"방문인구 월평균 {v:,.0f}명 (업종 무관, {rank}위/{len(g)})",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": f"D2 방문인구 월평균{age_note}",
            "as_of": _registry_as_of("D2"), "spec": spec, "raw": v}


def compute_comp(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    sup = store.table("supply")
    sc = sup[sup["app_category"] == category].set_index("dong")["n_stores"]
    if dong not in sc.index or len(sc) == 0:
        return _unavailable(spec, "D4에 해당 지역·업종 점포 없음")
    # 카드 매출이 있으면 '점포/억원', 없으면 점포수 자체 백분위
    cat = _demand_slice(category)
    if not cat.empty and dong in cat["dong"].unique():
        g = cat.groupby("dong")
        monthly_oku = (g["이용금액_합계"].sum() / g["년월"].nunique()) / 1e8
        comp = sc.reindex(monthly_oku.index).fillna(0) / monthly_oku.replace(0, pd.NA)
        if dong in comp.index and pd.notna(comp.loc[dong]):
            v = float(comp.loc[dong])
            p = _percentile(v, comp)
            return {"name": spec.name, "value": f"{v:.2f} 점포/억원",
                    "level": _level_from_pct(p, spec.direction),
                    "percentile": round(p, 3),
                    "reason": "D4 점포수 / 월평균 매출(억원)",
                    "as_of": _registry_as_of("D4"), "spec": spec, "raw": v}
    v = float(sc.loc[dong])
    p = _percentile(v, sc)
    return {"name": spec.name,
            "value": f"{int(v)}개 점포 (업종 내 상위 {(1-p)*100:.0f}%)",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": "D4 점포수 백분위 (카드 데이터 없음)",
            "as_of": _registry_as_of("D4"), "spec": spec, "raw": v}


def compute_survival(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    if not store.has_optional("survival"):
        return _unavailable(spec, "D5 음식점 데이터 없음")
    sv = store.table("survival")
    cat = sv[sv["app_category"] == category]
    row = cat[cat["dong"] == dong]
    if row.empty:
        return _unavailable(spec, "D5에 해당 지역·업종 이력 없음")
    r = row.iloc[0]
    y3 = r["survival_3y"]
    if pd.isna(y3):
        return _unavailable(spec, "D5 3년 생존율 산출 불가 (표본 부족)")
    y3 = float(y3)
    overall = float(cat["survival_3y"].mean()) if cat["survival_3y"].notna().any() else None
    p = _percentile(y3, cat["survival_3y"])
    diff = (None if overall is None else y3 - overall)
    reason = (f"업종 평균 대비 {diff*100:+.1f}%p" if diff is not None else "업종 평균 비교 불가")
    return {"name": spec.name,
            "value": f"3년 생존율 {y3*100:.1f}% (n={int(r['n_3y'])})",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": reason, "as_of": _registry_as_of("D5"),
            "spec": spec, "raw": y3}


def compute_churn(dong: str, category: str, spec: SignalSpec, _ctx: dict) -> dict:
    if not store.has_optional("openings_closings_monthly"):
        return _unavailable(spec, "D5 개폐업 데이터 없음")
    oc = store.table("openings_closings_monthly")
    as_of = _registry_as_of("D5") or "2025-09-02"
    end_ym = as_of[:7]
    start_ym = (pd.Timestamp(end_ym + "-01") - pd.DateOffset(months=23)).strftime("%Y-%m")
    sub = oc[(oc["app_category"] == category)
             & (oc["년월"] >= start_ym) & (oc["년월"] <= end_ym)]
    if sub.empty:
        return _unavailable(spec, "D5에 해당 업종 24개월 이력 없음")
    dong_sub = sub[sub["dong"] == dong]
    if dong_sub.empty:
        return _unavailable(spec, "D5에 해당 지역 24개월 이력 없음")
    opens = int(dong_sub["개업수"].sum())
    closes = int(dong_sub["폐업수"].sum())
    net = opens - closes
    if opens == 0:
        return _unavailable(spec, "24개월 개업 없음 (비율 계산 불가)")
    churn = closes / opens
    # 업종 내 전체 동 분포
    ratios = []
    for _, grp in sub.groupby("dong"):
        o, c = grp["개업수"].sum(), grp["폐업수"].sum()
        if o > 0:
            ratios.append(c / o)
    series = pd.Series(ratios)
    p = _percentile(churn, series) if len(series) else 0.5
    return {"name": spec.name,
            "value": f"24개월 개업 {opens}/폐업 {closes} (순증 {net:+d})",
            "level": _level_from_pct(p, spec.direction),
            "percentile": round(p, 3),
            "reason": f"폐업/개업 {churn:.2f}",
            "as_of": _registry_as_of("D5"),
            "spec": spec, "raw": churn}


COMPUTE: dict[str, Callable[[str, str, SignalSpec, dict], dict]] = {
    "관광 의존도": compute_tour,
    "계절 변동성": compute_season,
    "수요 규모": compute_demand,
    "유동 수요": compute_footfall,
    "경쟁 밀도": compute_comp,
    "생존 리스크": compute_survival,
    "최근 개폐업": compute_churn,
}


def compute_all(dong: str, category: str, context: dict | None = None) -> list[dict]:
    """모든 신호 compute → 신호 dict 리스트 (일부 unavailable 가능)."""
    ctx = context or {}
    out: list[dict] = []
    for spec in SIGNAL_SPECS:
        fn = COMPUTE[spec.name]
        try:
            out.append(fn(dong, category, spec, ctx))
        except Exception as e:  # noqa: BLE001
            out.append(_unavailable(spec, f"컴퓨트 오류: {type(e).__name__}"))
    return out
