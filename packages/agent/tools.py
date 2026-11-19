"""Agent 도구. 모든 수치 계산은 여기서만 한다 (LLM은 계산하지 않음).

모든 도구는 dict를 반환하며 `source`, `period`, `as_of`, `note` 필드를 포함한다.
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

import pandas as pd

from . import signals as signals_mod
from . import store

BASE_PERIOD = "2018-01~2019-12"
BASE_START = "2018-01"
BASE_END = "2019-12"

# 신호등 임계: 업종 내 백분위 (하위 1/3 / 중간 / 상위 1/3)
P_LOW, P_HIGH = 1 / 3, 2 / 3

# 기본 가중치 — 6개 신호 (SPEC 변경)
DEFAULT_WEIGHTS = {
    "tour": 20.0, "season": 15.0, "comp": 15.0,
    "demand": 15.0, "survival": 20.0, "churn": 15.0,
}

# 각 신호의 가중치 키 — 재정규화에 사용
SIGNAL_KEYS: dict[str, str] = {
    "관광 의존도": "tour", "계절 변동성": "season",
    "경쟁 밀도": "comp", "수요 규모": "demand",
    "생존 리스크": "survival", "최근 개폐업": "churn",
}


# ---------- 내부 유틸 ----------

def _base_slice(df: pd.DataFrame, col: str = "년월") -> pd.DataFrame:
    return df[(df[col] >= BASE_START) & (df[col] <= BASE_END)]


def _percentile(value: float, series: pd.Series) -> float:
    s = series.dropna()
    if len(s) == 0:
        return 0.5
    return float((s < value).mean())


def _level_from_pct(pct: float, reverse: bool = False) -> str:
    if reverse:
        pct = 1 - pct
    if pct < P_LOW:
        return "green"
    if pct < P_HIGH:
        return "yellow"
    return "red"


def _rank_in_category(series: pd.Series, value: float) -> tuple[int, int]:
    sorted_vals = series.sort_values(ascending=False).values
    rank = int((sorted_vals > value).sum() + 1)
    return rank, int(len(sorted_vals))


def _registry() -> dict[str, dict]:
    path = store.data_dir() / "registry.json"
    if not path.exists():
        return {}
    with path.open(encoding="utf-8") as f:
        data = json.load(f)
    return {r["id"]: r for r in data}


def _as_of(id_: str) -> str:
    return _registry().get(id_, {}).get("as_of", "")


# ---------- category_map 접근 ----------

_CMAP_PATH = Path(__file__).resolve().parents[1] / "pipeline" / "category_map.csv"


def _load_cmap() -> pd.DataFrame:
    return pd.read_csv(_CMAP_PATH).fillna("")


def category_availability(category: str) -> dict[str, bool]:
    """업종별 데이터 가용성.

    - has_card:    D1 (카드 매출) 매핑이 존재
    - has_store:   D4 (상가 정보) 매핑이 존재
    - has_license: D5 (음식점 인허가) 매핑이 존재
    """
    m = _load_cmap()
    row = m[m["app_category"] == category]
    if row.empty:
        return {"has_card": False, "has_store": False, "has_license": False}
    r = row.iloc[0]
    return {
        "has_card": bool(str(r["d1_업종명"]).strip()),
        "has_store": bool(str(r["d4_표준산업분류명"]).strip()),
        "has_license": bool(str(r["d5_업종소분류"]).strip()),
    }


# ---------- 의도 파악 ----------

# "추천 모드" 암시 토큰
_RECO_TOKENS = ("ㅊㅊ", "추천", "추천해", "어디가 좋", "어디 좋", "할만한", "어디서",
                "어디에", "어느", "뭐 하")

# "장소 추천" (지역이 비어 있고 업종이 있을 때)
_PLACE_HINT = ("어디", "할만한", "지역 추천", "장소 추천", "어디가 좋")

# "업종 추천" (업종이 비어 있고 장소가 있을 때)
_CAT_HINT = ("뭐 하", "뭐할", "무슨 업종", "뭘 하")


_AGE_PAT = re.compile(r"(\d{2})\s*대")
_AGE_NAMED = {
    "청년": ["20대", "30대"], "중년": ["40대", "50대"],
    "시니어": ["60대", "70대"], "실버": ["60대", "70대"],
    "10대": ["10대"], "20대": ["20대"], "30대": ["30대"],
    "40대": ["40대"], "50대": ["50대"], "60대": ["60대"], "70대": ["70대"],
}
_CUST_ALIAS = {
    "관광객": "tourist", "여행객": "tourist", "관광": "tourist",
    "도민": "local", "주민": "local", "지역민": "local",
}


def _extract_ages(text: str) -> list[str]:
    ages: set[str] = set()
    for key, vals in _AGE_NAMED.items():
        if key in text:
            ages.update(vals)
    for m in _AGE_PAT.finditer(text):
        ages.add(f"{m.group(1)}대")
    return sorted(ages)


def _extract_customer(text: str) -> str | None:
    for key, val in _CUST_ALIAS.items():
        if key in text:
            return val
    return None


def parse_intent(text: str) -> dict[str, Any]:
    """자유 발화 → 의도 + 힌트 + 제약.

    반환: {intent, hints: {dong, category}, constraints: {ages, customer},
           confidence, note, source}
    intent: diagnose | place_recommend | category_recommend | clarify
    """
    t = (text or "").strip()
    if not t:
        return {"intent": "clarify", "hints": {}, "constraints": {},
                "confidence": 0.0, "note": "빈 입력", "source": "intent"}

    hints: dict[str, str | None] = {}
    low = t.lower()
    PARTICLES = ("은", "는", "이", "가", "을", "를", "의", "로", "에", "에서", "도")
    for raw in t.replace("?", " ").split():
        for suf in [""] + list(PARTICLES):
            cand = raw[: -len(suf)] if suf and raw.endswith(suf) and len(raw) > len(suf) else raw
            if not hints.get("dong"):
                r = resolve_place(cand)
                if r.get("dong"):
                    hints["dong"] = r["dong"]
                    break
    for raw in t.replace("?", " ").split():
        if not hints.get("category"):
            r = resolve_category(raw)
            if r.get("app_category"):
                hints["category"] = r["app_category"]

    constraints: dict[str, Any] = {}
    ages = _extract_ages(t)
    if ages:
        constraints["ages"] = ages
    cust = _extract_customer(t)
    if cust:
        constraints["customer"] = cust

    has_place = bool(hints.get("dong"))
    has_cat = bool(hints.get("category"))
    is_reco = any(k in low for k in _RECO_TOKENS)
    wants_place = any(k in low for k in _PLACE_HINT)
    wants_cat = any(k in low for k in _CAT_HINT)

    if has_place and has_cat:
        intent = "diagnose"
    elif has_cat and (wants_place or is_reco or not has_place):
        intent = "place_recommend"
    elif has_place and (wants_cat or not has_cat):
        intent = "category_recommend"
    elif is_reco:
        intent = "clarify"
    else:
        intent = "clarify"

    return {"intent": intent, "hints": hints, "constraints": constraints,
            "confidence": 0.8 if intent != "clarify" else 0.3,
            "note": f"hints={hints} constraints={constraints}", "source": "intent"}


# ---------- resolve ----------

def resolve_place(text: str) -> dict[str, Any]:
    """'애월', '노형' → 표준 행정동명.

    - 매칭이 명확하지 않으면 dong=None + not_found=True.
    - 입력 자체가 자연어/구어체이면 dong=None 유지.
    """
    meta = store.table("dong_meta")
    dongs = meta["행정동명"].tolist()
    q = (text or "").strip()
    if not q:
        return {"dong": None, "candidates": [], "not_found": True,
                "source": "D4", "period": "2025-09", "as_of": _as_of("D4"),
                "note": "빈 입력"}
    if q in dongs:
        return {"dong": q, "candidates": [q], "not_found": False, "source": "D4",
                "period": "2025-09", "as_of": _as_of("D4"), "note": "완전일치"}
    # 자연어 토큰은 제외: 한글이 아니거나, 지역 키워드로 전혀 못쓸 짧은 조각
    if len(q) > 15 or not re.match(r"[가-힣]", q):
        return {"dong": None, "candidates": [], "not_found": True, "source": "D4",
                "period": "2025-09", "as_of": _as_of("D4"), "note": "지역명 형식 아님"}

    hits = [d for d in dongs if q in d or d.startswith(q)
            or d.replace("읍", "").replace("면", "") == q]
    for suf in ("읍", "면", "동"):
        cand = q + suf
        if cand in dongs and cand not in hits:
            hits.append(cand)
    hits = list(dict.fromkeys(hits))
    if len(hits) == 1:
        return {"dong": hits[0], "candidates": hits, "not_found": False, "source": "D4",
                "period": "2025-09", "as_of": _as_of("D4"), "note": "부분일치 1건"}
    if hits:
        return {"dong": None, "candidates": hits, "not_found": False, "source": "D4",
                "period": "2025-09", "as_of": _as_of("D4"), "note": f"후보 {len(hits)}건"}
    return {"dong": None, "candidates": [], "not_found": True, "source": "D4",
            "period": "2025-09", "as_of": _as_of("D4"), "note": "매칭 지역 없음"}


_ALIASES = {
    "커피": "카페", "커피숍": "카페", "카페테리아": "카페",
    "한식": "한식당", "밥집": "한식당",
    "일식": "일식당", "초밥": "일식당", "스시": "일식당",
    "중식": "중식당", "짜장": "중식당",
    "양식": "양식당", "파스타": "양식당",
    "빵집": "베이커리", "제과": "베이커리",
    "술집": "술집", "바": "술집", "호프": "술집",
    "민박": "소형숙박", "게스트하우스": "소형숙박", "모텔": "소형숙박", "숙박": "소형숙박",
    "햄버거": "패스트푸드", "피자": "패스트푸드",
    "기념품": "기념품점", "선물": "기념품점",
    "피씨방": "PC방", "PC방": "PC방", "pc방": "PC방", "pcbang": "PC방",
    "미용": "미용실", "헤어샵": "미용실", "이발": "미용실", "이용": "미용실",
    "네일아트": "네일샵", "네일케어": "네일샵", "네일": "네일샵",
    "헬스": "헬스장", "짐": "헬스장", "체육관": "헬스장",
    "노래": "노래방", "코인노래방": "노래방",
}


def resolve_place_via_landmark(text: str) -> dict[str, Any]:
    """문자열 유사도 실패 시 LLM에게 '랜드마크·생활 지명이 속한 행정동'을 43개 중에서 고르게 한다.

    LLM 미설정이거나 LLM이 모르면 not_found=True, 호출자는 clarify로 넘어가야 한다.
    """
    from . import llm as _llm

    q = (text or "").strip()
    meta = store.table("dong_meta")
    dong_list = meta["행정동명"].tolist()
    if not q:
        return {"dong": None, "candidates": [], "not_found": True,
                "method": "none", "source": "LLM", "period": "", "as_of": "",
                "note": "빈 입력"}
    if _llm.provider() == "none":
        return {"dong": None, "candidates": dong_list, "not_found": True,
                "method": "none", "source": "LLM", "period": "", "as_of": "",
                "note": "LLM 미설정 — clarify 필요"}

    system = ("제주 행정동 43개 중에서만 선택하세요. "
              "사용자 표현이 가리키는 랜드마크/생활 지명이 속한 행정동을 정확히 하나 고르거나, "
              "모르면 UNKNOWN을 반환하세요. "
              "반드시 JSON 한 줄만 반환: {\"dong\": \"<행정동명 or UNKNOWN>\"}")
    user = f"사용자 표현: {q}\n행정동 목록: {', '.join(dong_list)}"
    try:
        resp = _llm.chat_with_tools(
            [{"role": "system", "content": system},
             {"role": "user", "content": user}],
            tools=[],
        )
    except Exception as e:  # noqa: BLE001
        return {"dong": None, "candidates": [], "not_found": True,
                "method": "llm_error", "source": "LLM", "period": "", "as_of": "",
                "note": f"LLM 호출 실패: {type(e).__name__}"}

    out = (resp.get("text") or "").strip()
    m = re.search(r"\{[^{}]*\}", out)
    dong = None
    if m:
        try:
            obj = json.loads(m.group(0))
            cand = obj.get("dong")
            if cand and cand in set(dong_list) and cand != "UNKNOWN":
                dong = cand
        except json.JSONDecodeError:
            pass
    if dong:
        return {"dong": dong, "candidates": [dong], "not_found": False,
                "method": "llm", "source": "LLM", "period": "", "as_of": "",
                "note": "랜드마크→행정동 LLM 추론"}
    return {"dong": None, "candidates": [], "not_found": True,
            "method": "llm", "source": "LLM", "period": "", "as_of": "",
            "note": "LLM이 매칭 실패"}


def resolve_category(text: str) -> dict[str, Any]:
    """자연어 업종 표현 → app_category. 지원 업종 매핑 외는 None."""
    supply = store.table("supply")
    cats = sorted(supply["app_category"].unique().tolist())
    q = (text or "").strip()
    if not q:
        return {"app_category": None, "candidates": cats, "not_found": True,
                "source": "mapping", "period": BASE_PERIOD, "as_of": "",
                "note": "빈 입력"}
    if q in cats:
        return {"app_category": q, "candidates": [q], "not_found": False,
                "source": "mapping", "period": BASE_PERIOD, "as_of": "", "note": "완전일치"}
    if q in _ALIASES:
        c = _ALIASES[q]
        return {"app_category": c, "candidates": [c], "not_found": False,
                "source": "mapping", "period": BASE_PERIOD, "as_of": "",
                "note": f"동의어 '{q}'→'{c}'"}
    hits = [c for c in cats if q in c]
    if len(hits) == 1:
        return {"app_category": hits[0], "candidates": hits, "not_found": False,
                "source": "mapping", "period": BASE_PERIOD, "as_of": "", "note": "부분일치"}
    if hits:
        return {"app_category": None, "candidates": hits, "not_found": False,
                "source": "mapping", "period": BASE_PERIOD, "as_of": "",
                "note": f"후보 {len(hits)}건"}
    return {"app_category": None, "candidates": cats, "not_found": True,
            "source": "mapping", "period": BASE_PERIOD, "as_of": "",
            "note": "매칭 업종 없음"}


# ---------- 수요·공급·생존 ----------

def _demand_for(dong: str, category: str) -> pd.DataFrame:
    d = store.table("demand_monthly")
    base = _base_slice(d)
    return base[(base["dong"] == dong) & (base["app_category"] == category)].copy()


def get_demand(dong: str, category: str) -> dict[str, Any]:
    """월평균 매출, 관광 비중, 12개월 패턴, 연령대 비중. source=D1."""
    sub = _demand_for(dong, category)
    if sub.empty:
        return {"dong": dong, "category": category, "available": False,
                "source": "D1", "period": BASE_PERIOD, "as_of": _as_of("D1"),
                "note": "기준 기간에 해당 지역·업종 카드 데이터 없음"}
    total = float(sub["이용금액_합계"].sum())
    months = sub["년월"].nunique()
    monthly_avg = total / max(months, 1)
    tourism = float(sub["이용금액_관광개별"].sum() + sub["이용금액_관광단체"].sum())
    local = float(sub["이용금액_도민"].sum())
    tourism_ratio = tourism / total if total else 0.0
    local_ratio = local / total if total else 0.0
    sub = sub.assign(month=sub["년월"].str[5:7].astype(int))
    pattern = (sub.groupby("month")["이용금액_합계"].mean().reindex(range(1, 13)))
    season_ratio = (float(pattern.max() / pattern.min())
                    if pattern.notna().any() and pattern.min() > 0 else None)
    age_df = store.table("demand_age")
    age_sub = age_df[(age_df["dong"] == dong) & (age_df["app_category"] == category)]
    age_total = float(age_sub["이용금액"].sum())
    age_breakdown = ({r["연령대"]: round(r["이용금액"] / age_total, 3)
                      for _, r in age_sub.iterrows()} if age_total else {})
    return {
        "dong": dong, "category": category, "available": True,
        "monthly_avg_krw": round(monthly_avg), "months": int(months),
        "tourism_ratio": round(tourism_ratio, 4),
        "local_ratio": round(local_ratio, 4),
        "peak_month": int(pattern.idxmax()) if pattern.notna().any() else None,
        "low_month": int(pattern.idxmin()) if pattern.notna().any() else None,
        "season_ratio": round(season_ratio, 3) if season_ratio else None,
        "monthly_pattern": {int(k): round(float(v)) for k, v in pattern.dropna().items()},
        "age_breakdown": age_breakdown,
        "source": "D1", "period": BASE_PERIOD, "as_of": _as_of("D1"),
        "note": "카드사 표본 — 비중·배율 중심 해석 권장",
    }


def get_supply(dong: str, category: str) -> dict[str, Any]:
    """점포 수와 업종 내 순위. source=D4."""
    sup = store.table("supply")
    cat_slice = sup[sup["app_category"] == category]
    if cat_slice.empty:
        return {"dong": dong, "category": category, "available": False,
                "source": "D4", "period": "2025-09", "as_of": _as_of("D4"),
                "note": "해당 업종이 D4에 매핑되지 않음"}
    row = cat_slice[cat_slice["dong"] == dong]
    n_stores = int(row["n_stores"].iat[0]) if not row.empty else 0
    rank, total_dongs = _rank_in_category(cat_slice["n_stores"], n_stores)
    return {
        "dong": dong, "category": category, "available": True,
        "n_stores": n_stores, "rank": rank, "of": total_dongs,
        "source": "D4", "period": "2025-09", "as_of": _as_of("D4"),
        "note": "D4 상가 정보 기준 점포 수",
    }


def get_survival(dong: str, category: str) -> dict[str, Any]:
    """1년·3년 생존율과 업종 내 백분위. source=D5."""
    if not store.has_optional("survival"):
        return {"dong": dong, "category": category, "available": False,
                "source": "D5", "period": "", "as_of": _as_of("D5"),
                "note": "D5 미빌드"}
    sv = store.table("survival")
    cat = sv[sv["app_category"] == category]
    row = cat[cat["dong"] == dong]
    if row.empty:
        return {"dong": dong, "category": category, "available": False,
                "source": "D5", "period": "1960-01~" + _as_of("D5"),
                "as_of": _as_of("D5"),
                "note": "해당 지역·업종에 음식점 이력 없음"}
    r = row.iloc[0]
    y1 = r["survival_1y"] if pd.notna(r["survival_1y"]) else None
    y3 = r["survival_3y"] if pd.notna(r["survival_3y"]) else None
    overall_3y = float(cat["survival_3y"].mean()) if cat["survival_3y"].notna().any() else None
    overall_1y = float(cat["survival_1y"].mean()) if cat["survival_1y"].notna().any() else None
    pct_3y = _percentile(y3, cat["survival_3y"]) if y3 is not None else 0.5
    return {
        "dong": dong, "category": category, "available": True,
        "survival_1y": None if y1 is None else round(float(y1), 4),
        "survival_3y": None if y3 is None else round(float(y3), 4),
        "n_1y": int(r["n_1y"]), "n_3y": int(r["n_3y"]),
        "overall_1y": None if overall_1y is None else round(overall_1y, 4),
        "overall_3y": None if overall_3y is None else round(overall_3y, 4),
        "diff_from_overall_3y": (None if y3 is None or overall_3y is None
                                 else round(float(y3) - overall_3y, 4)),
        "percentile_3y": round(pct_3y, 3),
        "fallback": r["fallback"] if pd.notna(r["fallback"]) else None,
        "source": "D5", "period": "1960-01~" + _as_of("D5"), "as_of": _as_of("D5"),
        "note": "인허가·폐업일 기준 생존율 (중도절단 처리)",
    }


def get_recent_openings(dong: str, category: str, months: int = 24) -> dict[str, Any]:
    """최근 N개월 개업·폐업 수, 순증, 직전 동기 대비. source=D5."""
    if not store.has_optional("openings_closings_monthly"):
        return {"dong": dong, "category": category, "available": False,
                "source": "D5", "period": "", "as_of": _as_of("D5"),
                "note": "D5 미빌드"}
    oc = store.table("openings_closings_monthly")
    as_of = _as_of("D5") or "2025-09-02"
    end_ym = as_of[:7]
    end_ts = pd.Timestamp(end_ym + "-01")
    start_ts = (end_ts - pd.DateOffset(months=months - 1)).strftime("%Y-%m")
    prev_start = (end_ts - pd.DateOffset(months=months * 2 - 1)).strftime("%Y-%m")
    prev_end = (end_ts - pd.DateOffset(months=months)).strftime("%Y-%m")
    sub = oc[(oc["dong"] == dong) & (oc["app_category"] == category)]
    recent = sub[(sub["년월"] >= start_ts) & (sub["년월"] <= end_ym)]
    prev = sub[(sub["년월"] >= prev_start) & (sub["년월"] <= prev_end)]
    if len(recent) == 0 and len(prev) == 0:
        return {"dong": dong, "category": category, "months": months,
                "available": False,
                "source": "D5", "period": f"{start_ts}~{end_ym}",
                "as_of": _as_of("D5"),
                "note": "해당 지역·업종에 음식점 이력 없음"}
    opens = int(recent["개업수"].sum())
    closes = int(recent["폐업수"].sum())
    net = opens - closes
    churn = closes / opens if opens else None
    prev_opens = int(prev["개업수"].sum())
    prev_closes = int(prev["폐업수"].sum())
    prev_net = prev_opens - prev_closes
    return {
        "dong": dong, "category": category, "months": months,
        "window": f"{start_ts}~{end_ym}", "available": True,
        "opens": opens, "closes": closes, "net": net,
        "close_ratio": round(churn, 3) if churn is not None else None,
        "prev_window": f"{prev_start}~{prev_end}",
        "prev_net": prev_net, "delta_vs_prev": net - prev_net,
        "source": "D5", "period": f"{start_ts}~{end_ym}",
        "as_of": _as_of("D5"),
        "note": "인허가·폐업일 기준 월별 집계",
    }


def get_dong_vitality(dong: str) -> dict[str, Any]:
    """연도별 신생률·소멸률·순증 (D6)."""
    if not store.has_optional("dong_lifecycle"):
        return {"dong": dong, "available": False, "source": "D6",
                "period": "", "as_of": _as_of("D6"), "note": "D6 미빌드"}
    life = store.table("dong_lifecycle")
    sub = life[life["dong"] == dong].sort_values("year")
    if sub.empty:
        return {"dong": dong, "available": False, "source": "D6",
                "period": "", "as_of": _as_of("D6"), "note": "해당 행정동 레코드 없음"}
    yrs = sub["year"].tolist()
    return {
        "dong": dong, "available": True,
        "years": yrs, "records": sub.to_dict("records"),
        "source": "D6", "period": f"{min(yrs)}~{max(yrs)}",
        "as_of": _as_of("D6"),
        "note": "KOSIS 사업체 생멸 — 5 이하 비공개(*)",
    }


def get_tourism_trend() -> dict[str, Any]:
    """최근 12개월 vs 직전 12개월 증감률 + 성수·비수 배율. source=D9."""
    if not store.has_optional("visitors_monthly"):
        return {"available": False, "source": "D9", "period": "",
                "as_of": _as_of("D9"), "note": "D9 미빌드"}
    v = store.table("visitors_monthly")
    monthly = v.groupby("년월")["방문자수"].sum().sort_index()
    if len(monthly) < 24:
        return {"available": False, "source": "D9", "as_of": _as_of("D9"),
                "period": f"{monthly.index.min()}~{monthly.index.max()}" if len(monthly) else "",
                "note": "데이터 24개월 미만"}
    last12 = monthly.iloc[-12:]
    prev12 = monthly.iloc[-24:-12]
    yoy = (last12.sum() - prev12.sum()) / prev12.sum() if prev12.sum() else None
    recent = monthly.iloc[-36:] if len(monthly) >= 36 else monthly
    rdf = recent.rename_axis("ym").reset_index(name="cnt")
    rdf["m"] = rdf["ym"].str[5:7].astype(int)
    mo = rdf.groupby("m")["cnt"].mean()
    season = float(mo.max() / mo.min()) if mo.min() > 0 else None
    purpose = None
    if "방문목적" in v.columns:
        latest_ym, start_ym = monthly.index[-1], monthly.index[-12]
        r = v[(v["년월"] >= start_ym) & (v["년월"] <= latest_ym)]
        total = float(r["방문자수"].sum())
        if total:
            purpose = (r.groupby("방문목적")["방문자수"].sum() / total).round(3).to_dict()
    return {
        "available": True,
        "yoy_12m": None if yoy is None else round(float(yoy), 4),
        "season_ratio_36m": None if season is None else round(season, 3),
        "purpose_share": purpose,
        "window": f"{last12.index.min()}~{last12.index.max()}",
        "prev_window": f"{prev12.index.min()}~{prev12.index.max()}",
        "source": "D9", "period": f"{monthly.index.min()}~{monthly.index.max()}",
        "as_of": _as_of("D9"), "note": "제주 전체 입도객 수",
    }


# ---------- score_risk (signals.py 레지스트리 기반) ----------

# 신뢰도 임계: 가용 신호 수가 이 값 미만이면 score=null, confidence="low"
MIN_SIGNALS_FOR_SCORE = 3


def _active_signals(signals: list[dict]) -> list[dict]:
    return [s for s in signals if s.get("level") != "unavailable"]


def score_risk(dong: str, category: str,
               weights: dict[str, float] | None = None,
               context: dict | None = None) -> dict[str, Any]:
    """signals.py 레지스트리로 모든 신호를 compute 하고 점수·신뢰도를 산출.

    규칙
    - 가용 신호 수가 MIN_SIGNALS_FOR_SCORE 미만 → score=null, confidence="low"
    - 수요 계열(signals_mod.demand_family) 신호가 하나도 가용하지 않으면
      → score=null, confidence="low" (경쟁 밀도만으로 점수 금지)
    - 그 외: 가용 신호의 가중치만 재정규화해 점수 산출
    """
    w_default = {sp.key: 15.0 for sp in signals_mod.SIGNAL_SPECS}
    w_default.update({"tour": 20.0, "survival": 20.0})  # 기본 가중치 (조정 가능)
    w = {**w_default, **(weights or {})}
    context = dict(context or {})

    # 모든 신호 compute (signals.py 레지스트리)
    raw = signals_mod.compute_all(dong, category, context)

    # UI용 signals (spec 제거)
    signals: list[dict] = [{k: v for k, v in s.items() if k != "spec"} for s in raw]
    unavail_count = sum(1 for s in signals if s["level"] == "unavailable")
    mode = "full" if unavail_count == 0 else "partial"

    # 가용 신호와 수요 계열 가용 여부
    active = _active_signals(signals)
    active_demand = any(s["name"] in signals_mod.demand_family() for s in active)

    # 데이터 ID 사용 집합 (evidence·limitations 재료)
    data_ids_used: set[str] = set()
    data_ids_missing: dict[str, str] = {}
    for s in raw:
        spec = s.get("spec")
        if spec is None:
            continue
        if s.get("level") == "unavailable":
            for d in spec.requires:
                data_ids_missing.setdefault(d, s.get("reason", "데이터 없음"))
        else:
            for d in spec.requires:
                data_ids_used.add(d)

    # 신뢰도 규칙
    low_confidence_reason = None
    if len(active) < MIN_SIGNALS_FOR_SCORE:
        low_confidence_reason = f"가용 신호 {len(active)}/{len(signals)} < {MIN_SIGNALS_FOR_SCORE}"
    elif not active_demand:
        low_confidence_reason = "수요 계열(수요 규모·유동 수요) 신호 없음 — 경쟁 밀도만으로 추천 금지"

    if low_confidence_reason:
        return {
            "dong": dong, "category": category, "available": True,
            "mode": mode,
            "signals": signals, "score": None, "confidence": "low",
            "confidence_reason": low_confidence_reason,
            "active_signals": len(active), "total_signals": len(signals),
            "weights": w, "active_weights": {},
            "data_ids_used": sorted(data_ids_used),
            "data_ids_missing": data_ids_missing,
            "source": "+".join(sorted(data_ids_used)) or "unknown",
            "period": BASE_PERIOD,
            "as_of": "",
            "note": f"신뢰도 낮음 ({low_confidence_reason})",
        }

    # 가용 신호만 가중치 재정규화
    active_w = {}
    for s in raw:
        if s.get("level") == "unavailable":
            continue
        spec = s.get("spec")
        if spec is None:
            continue
        active_w[spec.key] = w.get(spec.key, 15.0)
    wsum = sum(active_w.values()) or 1.0
    norm = {k: v / wsum for k, v in active_w.items()}

    # 점수 집계: direction=low_red 신호는 (1 - pct)를 패널티에 사용
    neg = 0.0
    for s in raw:
        if s.get("level") == "unavailable":
            continue
        spec = s.get("spec")
        p = s.get("percentile")
        if p is None or spec is None:
            continue
        risk_pct = (1 - p) if spec.direction == "low_red" else p
        neg += norm.get(spec.key, 0.0) * risk_pct
    score = max(0.0, min(100.0, 100.0 * (1.0 - neg)))

    return {
        "dong": dong, "category": category, "available": True,
        "mode": mode,
        "signals": signals, "score": round(score),
        "confidence": "normal",
        "active_signals": len(active), "total_signals": len(signals),
        "weights": w, "active_weights": active_w,
        "data_ids_used": sorted(data_ids_used),
        "data_ids_missing": data_ids_missing,
        "source": "+".join(sorted(data_ids_used)) or "unknown",
        "period": BASE_PERIOD,
        "as_of": _as_of("D5") or _as_of("D4"),
        "note": f"백분위 기반 신호등 ({len(active)}/{len(signals)} 신호 가용)",
    }


# ---------- compare / render ----------

def compare_places(category: str, dongs: list[str] | None = None, top_k: int = 3,
                   weights: dict[str, float] | None = None,
                   exclude: list[str] | None = None,
                   context: dict | None = None) -> dict[str, Any]:
    sup = store.table("supply")
    cat_dongs = sup[sup["app_category"] == category]["dong"].unique()
    if len(cat_dongs) == 0:
        return {"category": category, "available": False,
                "source": "D1+D4+D5", "period": BASE_PERIOD, "as_of": _as_of("D5"),
                "note": "해당 업종 매핑 없음"}
    candidates = sorted(set(dongs) if dongs else set(cat_dongs))
    excl = set(exclude or [])
    rows: list[dict[str, Any]] = []
    for name in candidates:
        if name in excl:
            continue
        r = score_risk(name, category, weights, context=context)
        if r.get("available"):
            rows.append({"dong": name,
                         "score": r.get("score"),               # None 가능
                         "confidence": r.get("confidence", "normal"),
                         "confidence_reason": r.get("confidence_reason"),
                         "active_signals": r.get("active_signals"),
                         "total_signals": r.get("total_signals"),
                         "signals": {s["name"]: s["level"] for s in r["signals"]},
                         "mode": r.get("mode", "full")})
    # 점수 있는 것 우선 + 내림차순, 점수 없는 것은 뒤로
    rows.sort(key=lambda r: (r.get("score") is None, -(r.get("score") or 0)))
    return {"category": category, "available": True,
            "ranking": rows[:top_k],
            "source": "D1+D4+D5", "period": BASE_PERIOD, "as_of": _as_of("D5"),
            "note": "종합 점수 내림차순 Top-K (신뢰도 낮은 항목은 score=null)"}


def find_gap_category(dong: str, top_k: int = 5) -> dict[str, Any]:
    """수요 백분위는 높고 점포 백분위는 낮은 업종. 카드 매출이 있는 업종만."""
    demand = _base_slice(store.table("demand_monthly"))
    supply = store.table("supply")
    gaps: list[dict[str, Any]] = []
    for cat in sorted(demand["app_category"].unique()):
        cat_d = demand[demand["app_category"] == cat]
        grouped = cat_d.groupby("dong")
        monthly = grouped["이용금액_합계"].sum() / grouped["년월"].nunique()
        if dong not in monthly.index:
            continue
        stores = supply[supply["app_category"] == cat].set_index("dong")["n_stores"]
        store_series = stores.reindex(monthly.index).fillna(0)
        n_stores = float(store_series.loc[dong])
        demand_pct = signals_mod._percentile(float(monthly.loc[dong]), monthly)
        supply_pct = signals_mod._percentile(n_stores, store_series)
        gap = demand_pct - supply_pct
        if gap <= 0:
            continue
        gaps.append({
            "category": cat,
            "gap": round(gap, 3),
            "demand_rank": int((monthly > monthly.loc[dong]).sum() + 1),
            "demand_n": int(len(monthly)),
            "n_stores": int(n_stores),
            "store_rank": int((store_series > n_stores).sum() + 1),
            "store_n": int(len(store_series)),
        })
    gaps.sort(key=lambda r: -r["gap"])
    return {"dong": dong, "available": bool(gaps), "gaps": gaps[:top_k],
            "source": "D1+D4", "period": BASE_PERIOD, "as_of": _as_of("D4"),
            "note": "수요 백분위 − 점포 백분위. 양수만 업종 후보"}


def get_trend(category: str) -> dict[str, Any]:
    """D3 업종 전체. 2018년 대비 최근 연도 이용금액 증감. 지역 점수에는 넣지 않는다."""
    if not store.has_optional("trend_yearly"):
        return {"category": category, "available": False, "source": "D3",
                "period": "", "as_of": _as_of("D3"), "note": "D3 미빌드"}
    tr = store.table("trend_yearly")
    sub = tr[tr["app_category"] == category].sort_values("year")
    if sub.empty:
        return {"category": category, "available": False, "source": "D3",
                "period": "", "as_of": _as_of("D3"), "note": "해당 업종 연도 자료 없음"}
    latest = sub.iloc[-1]
    year = int(latest["year"])
    base_rows = sub[sub["year"] == 2018]
    text = f"{category} 업종 전체 {year}년 자료가 있다. 제주 전체라 지역 점수는 바꾸지 않는다."
    delta = None
    if len(base_rows) and float(base_rows.iloc[0]["이용금액_합계"]) > 0:
        base = float(base_rows.iloc[0]["이용금액_합계"])
        delta = (float(latest["이용금액_합계"]) - base) / base
        text = (f"{category} 업종 전체 이용금액은 2018년 대비 {year}년 {delta*100:+.1f}%."
                " 제주 전체라 지역 점수는 바꾸지 않는다.")
    return {"category": category, "available": True, "text": text, "year": year,
            "delta": None if delta is None else round(delta, 4),
            "source": "D3", "period": f"2018~{year}", "as_of": str(year),
            "note": "지역 구분 없는 업종 합계"}


def get_footfall(dong: str, ages: list[str] | None = None) -> dict[str, Any]:
    """D2 유동인구. 업종 무관. 연령 필터는 D2에 연령 컬럼이 있을 때만."""
    if not store.has_optional("footfall_monthly"):
        return {"dong": dong, "available": False, "source": "D2",
                "period": "", "as_of": _as_of("D2"), "note": "D2 미빌드"}
    foot = store.table("footfall_monthly")
    if ages and "연령대" in foot.columns:
        foot = foot[foot["연령대"].isin(ages)]
    means = foot.groupby("dong")["방문인구"].mean()
    if dong not in means.index:
        return {"dong": dong, "available": False, "source": "D2",
                "period": "", "as_of": _as_of("D2"),
                "note": "해당 행정동 유동인구 없음"}
    visit = float(means.loc[dong])
    rank = int((means > visit).sum() + 1)
    age_applied = bool(ages and "연령대" in foot.columns)
    return {"dong": dong, "available": True,
            "방문인구_월평균": round(visit),
            "거주인구_월평균": round(float(foot[foot["dong"] == dong]["거주인구"].mean())),
            "근무인구_월평균": round(float(foot[foot["dong"] == dong]["근무인구"].mean())),
            "rank": rank, "of": int(len(means)),
            "source": "D2", "period": "2017-01~2021-05",
            "as_of": _as_of("D2"),
            "note": ("D2 월평균 · 연령 적용" if age_applied
                     else "D2 월평균 · 연령 미적용" if ages
                     else "D2 월평균 · 업종 무관")}


def render_map(layer: str, category: str | None = None,
               highlight: list[str] | None = None) -> dict[str, Any]:
    return {"layer": layer, "category": category, "highlight": highlight or []}


REGISTRY = {
    f.__name__: f
    for f in [
        parse_intent,
        resolve_place, resolve_place_via_landmark, resolve_category,
        get_demand, get_supply, get_survival, get_recent_openings,
        get_dong_vitality, get_tourism_trend, get_footfall,
        score_risk, compare_places, find_gap_category, get_trend, render_map,
    ]
}
