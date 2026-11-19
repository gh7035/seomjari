"""data/raw CSV → data/processed parquet.

검증된 사실 (SPEC §5.2):
- D1, D2, D4, D5 인코딩 CP949 / D3 UTF-8 BOM
- D1 '매장수'는 시 단위 값 → 사용 금지, 점포 수는 D4로 계산
- D1 법정동 73개 ⊂ D4 법정동명, D2 행정동 43개 ⊂ D4 행정동명
- D2 '년월' 표기가 파일마다 다름: 2019-01-01 / 21-Apr
- D4 '표준산업분류명' 값에 `;`가 포함되어 있어 매핑표 d4 구분자는 `|` 사용
- D5(음식점) 51,111행, 인허가 1960~2025-08-29, AS_OF=2025-09, 주소 법정동 추출 99.8%

실행: python -m pipeline.build_data
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw"
OUT = ROOT / "data" / "processed"
MAPPING = Path(__file__).resolve().parent / "category_map.csv"


# ---------- 공용 ----------

def _category_map() -> pd.DataFrame:
    return pd.read_csv(MAPPING).fillna("")


def _col_map(col: str) -> dict[str, str]:
    """매핑표의 한 컬럼(`d1_업종명` 등) → app_category 사전."""
    m = _category_map()
    out: dict[str, str] = {}
    for _, row in m.iterrows():
        raw = str(row[col])
        for name in raw.split("|"):
            name = name.strip()
            if name:
                out[name] = row["app_category"]
    return out


def _load_d4() -> pd.DataFrame:
    df = pd.read_csv(RAW / "d4_stores.csv", encoding="cp949", dtype=str)
    df["경도"] = pd.to_numeric(df["경도"], errors="coerce")
    df["위도"] = pd.to_numeric(df["위도"], errors="coerce")
    return df


def _beopjeong_to_haengjeong(d4: pd.DataFrame) -> dict[str, str]:
    """D4의 (법정동명 → 행정동명) 최빈값. 읍/면은 자기 자신."""
    pairs = d4[["법정동명", "행정동명"]].dropna()
    return pairs.groupby("법정동명")["행정동명"].agg(lambda s: s.mode().iat[0]).to_dict()


# ---------- 산출물 빌더: 기존 ----------

def build_dong_meta():
    d4 = _load_d4()
    g = d4.dropna(subset=["행정동명", "경도", "위도"]).groupby("행정동명")
    meta = g.agg(시군구=("시군구명", lambda s: s.mode().iat[0]),
                 lon=("경도", "median"),
                 lat=("위도", "median"),
                 n_stores=("상호명", "count")).reset_index()
    meta["도심_읍면"] = meta["행정동명"].str.contains(r"[읍면]$", regex=True).map({True: "읍면", False: "도심"})
    meta.to_parquet(OUT / "dong_meta.parquet", index=False)


def build_supply():
    d4 = _load_d4()
    d4["app_category"] = d4["표준산업분류명"].map(_col_map("d4_표준산업분류명"))
    cols = ["app_category", "행정동명", "경도", "위도", "상호명",
            "지번주소", "도로명주소", "표준산업분류명"]
    present = [c for c in cols if c in d4.columns]
    points = d4.dropna(subset=["app_category", "경도", "위도", "행정동명"])[present].copy()
    points = points.rename(columns={
        "행정동명": "dong", "경도": "lon", "위도": "lat", "상호명": "name",
        "지번주소": "address", "도로명주소": "road_address",
        "표준산업분류명": "sub_category",
    })
    if "address" not in points.columns:
        points["address"] = ""
    # 지번주소가 없으면 도로명주소 사용, 둘 다 없으면 빈 문자열
    road = points["road_address"] if "road_address" in points.columns else pd.Series("", index=points.index)
    points["address"] = points["address"].fillna(road).fillna("")
    if "road_address" in points.columns:
        points = points.drop(columns=["road_address"])
    supply = points.groupby(["dong", "app_category"]).size().reset_index(name="n_stores")
    points.to_parquet(OUT / "stores_points.parquet", index=False)
    supply.to_parquet(OUT / "supply.parquet", index=False)


def _load_d1_concat() -> pd.DataFrame:
    parts = []
    for y in ("18", "19", "21"):
        df = pd.read_csv(RAW / f"d1_card_{y}.csv", encoding="cp949",
                         usecols=["년월", "읍면동명", "업종명", "이용자 구분", "관광구분",
                                  "연령대", "성별", "이용금액"],
                         dtype={"년월": str, "읍면동명": str, "업종명": str,
                                "이용자 구분": str, "관광구분": str,
                                "연령대": str, "성별": str})
        df["이용금액"] = pd.to_numeric(df["이용금액"], errors="coerce").fillna(0)
        parts.append(df)
    d1 = pd.concat(parts, ignore_index=True)
    b2h = _beopjeong_to_haengjeong(_load_d4())
    d1["dong"] = d1["읍면동명"].map(b2h)
    d1["app_category"] = d1["업종명"].map(_col_map("d1_업종명"))
    return d1.dropna(subset=["dong", "app_category"])


def _spend_bucket(row: pd.Series) -> str:
    tour, user = row["관광구분"], row["이용자 구분"]
    if tour == "도민" or user == "제주도민": return "도민"
    if tour == "개별": return "관광개별"
    if tour == "단체": return "관광단체"
    return "기타"


def build_demand():
    d1 = _load_d1_concat()
    d1["bucket"] = d1.apply(_spend_bucket, axis=1)
    pivot = d1.pivot_table(index=["dong", "app_category", "년월"],
                           columns="bucket", values="이용금액", aggfunc="sum", fill_value=0)
    for col in ["도민", "관광개별", "관광단체", "기타"]:
        if col not in pivot.columns: pivot[col] = 0
    pivot = pivot.rename(columns=lambda c: f"이용금액_{c}")
    pivot["이용금액_합계"] = pivot.sum(axis=1)
    pivot.reset_index().to_parquet(OUT / "demand_monthly.parquet", index=False)

    age = (d1.dropna(subset=["연령대"]).query("연령대 != '알수없음'")
             .groupby(["dong", "app_category", "연령대"])["이용금액"]
             .sum().reset_index(name="이용금액"))
    age.to_parquet(OUT / "demand_age.parquet", index=False)


def _normalize_d2_yearmonth(s: pd.Series) -> pd.Series:
    out = pd.to_datetime(s, errors="coerce")
    mask = out.isna()
    if mask.any():
        alt = pd.to_datetime(s[mask], format="%y-%b", errors="coerce")
        out.loc[mask] = alt
    return out.dt.strftime("%Y-%m")


def build_footfall():
    parts = []
    for y in ("17", "18", "19", "20", "21"):
        df = pd.read_csv(RAW / f"d2_footfall_{y}.csv", encoding="cp949",
                         usecols=["년월", "읍면동명", "거주인구", "근무인구", "방문인구"])
        for c in ("거주인구", "근무인구", "방문인구"):
            df[c] = pd.to_numeric(df[c], errors="coerce")
        parts.append(df)
    d2 = pd.concat(parts, ignore_index=True)
    d2["년월"] = _normalize_d2_yearmonth(d2["년월"])
    d2 = d2.dropna(subset=["년월"]).rename(columns={"읍면동명": "dong"})
    foot = (d2.groupby(["dong", "년월"])[["거주인구", "근무인구", "방문인구"]]
              .mean().reset_index())
    foot.to_parquet(OUT / "footfall_monthly.parquet", index=False)


def build_trend():
    d3 = pd.read_csv(RAW / "d3_industry_gender.csv", encoding="utf-8-sig",
                     dtype={"base_year_month": str})
    d3["year"] = d3["base_year_month"].str[:4].astype(int)
    d3["app_category"] = d3["biz_nm"].map(_col_map("d1_업종명"))
    d3 = d3.dropna(subset=["app_category"])

    def bucket(u: str) -> str:
        if u == "제주도민": return "도민"
        if u == "내국인": return "내국인"
        if u in {"법인"}: return "기타"
        return "외국인"

    d3["bucket"] = d3["user_type"].map(bucket).fillna("기타")
    piv = d3.pivot_table(index=["app_category", "year"], columns="bucket",
                        values="use_amount", aggfunc="sum", fill_value=0)
    for col in ("도민", "내국인", "외국인", "기타"):
        if col not in piv.columns: piv[col] = 0
    piv = piv.rename(columns=lambda c: f"이용금액_{c}")
    piv["이용금액_합계"] = piv.sum(axis=1)
    piv.reset_index().to_parquet(OUT / "trend_yearly.parquet", index=False)


# ---------- 산출물 빌더: 신규 (D5 음식점 통합목록) ----------

ADDR_PAT = re.compile(r"(제주시|서귀포시)\s+(\S+?(?:동|읍|면))")


def _extract_beopjeong(addr: object, valid: set[str]) -> str | None:
    if not isinstance(addr, str):
        return None
    m = ADDR_PAT.search(addr)
    if not m:
        return None
    cand = m.group(2)
    return cand if cand in valid else None


def _parse_d5_date(s: object) -> pd.Timestamp | None:
    if not isinstance(s, str) or not s.strip():
        return None
    s = s.strip()
    # 원본에 "20060206.0"처럼 float→str 접미가 붙어 있는 경우 제거
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    # YYYYMMDD / YYYY-MM-DD / YYYY-MM-DD HH:MM:SS
    for fmt in ("%Y%m%d", "%Y-%m-%d", "%Y-%m-%d %H:%M:%S"):
        try:
            return pd.to_datetime(s, format=fmt)
        except (ValueError, TypeError):
            continue
    try:
        return pd.to_datetime(s, errors="coerce")
    except Exception:  # noqa: BLE001
        return None


def build_restaurants() -> dict:
    """D5 음식점 통합목록 → restaurants + openings_closings + survival.

    반환: {as_of: str, n_rows, map_fail_rate, cat_fail_rate}
    """
    f = RAW / "d5_restaurants.csv"
    if not f.exists():
        print(f"  [skip] {f.name} 없음")
        return {"as_of": None}

    df = pd.read_csv(f, encoding="cp949", dtype=str, low_memory=False)
    d4 = _load_d4()
    b2h = _beopjeong_to_haengjeong(d4)
    valid_beop = set(b2h.keys())

    df["인허가일"] = df["인허가일자"].map(_parse_d5_date)
    df["폐업일"] = df["폐업일자"].map(_parse_d5_date)
    df["갱신일"] = df["데이터갱신일자"].map(_parse_d5_date)

    # 지역 매핑
    beop = (df["소재지전체주소"].map(lambda a: _extract_beopjeong(a, valid_beop))
            .combine_first(df["도로명전체주소"].map(lambda a: _extract_beopjeong(a, valid_beop))))
    df["법정동"] = beop
    df["dong"] = beop.map(b2h)

    # 업종 매핑 (D5 소분류 → app_category)
    df["app_category"] = df["업종구분소분류"].map(_col_map("d5_업종소분류"))

    n = len(df)
    map_fail = df["dong"].isna().sum() / n
    cat_fail = df["app_category"].isna().sum() / n
    print(f"  [D5] rows={n}, 지역 매핑 실패 {map_fail*100:.1f}%, 업종 매핑 실패 {cat_fail*100:.1f}%")
    assert map_fail < 0.05, f"지역 매핑 실패율 {map_fail*100:.1f}% > 5%"

    # AS_OF: 인허가일·폐업일·갱신일 최댓값
    as_of = max(filter(pd.notna, [df["인허가일"].max(), df["폐업일"].max(), df["갱신일"].max()]))
    as_of_str = as_of.strftime("%Y-%m-%d")
    print(f"  [D5] AS_OF={as_of_str}")

    # 영업 여부 (영업/정상 → True)
    df["is_open"] = df["영업상태명"] == "영업/정상"
    # 영업 기간 (일 수): 폐업이면 폐업일-인허가일, 영업이면 AS_OF-인허가일
    end = df["폐업일"].where(~df["is_open"], as_of)
    df["영업기간_일"] = (end - df["인허가일"]).dt.days

    # 점포 단위 테이블
    rest = (df.dropna(subset=["app_category", "dong", "인허가일"])
              [["dong", "app_category", "인허가일", "폐업일", "is_open", "영업기간_일"]]
              .copy())
    rest.to_parquet(OUT / "restaurants.parquet", index=False)

    # 월별 개폐업: 2018-01 ~ AS_OF
    start_floor = pd.Timestamp("2018-01-01")
    opens = rest[rest["인허가일"] >= start_floor].copy()
    opens["년월"] = opens["인허가일"].dt.strftime("%Y-%m")
    open_cnt = opens.groupby(["dong", "app_category", "년월"]).size().reset_index(name="개업수")

    closes = rest[rest["폐업일"].notna() & (rest["폐업일"] >= start_floor)].copy()
    closes["년월"] = closes["폐업일"].dt.strftime("%Y-%m")
    close_cnt = closes.groupby(["dong", "app_category", "년월"]).size().reset_index(name="폐업수")

    oc = pd.merge(open_cnt, close_cnt, on=["dong", "app_category", "년월"], how="outer").fillna(0)
    oc["개업수"] = oc["개업수"].astype(int)
    oc["폐업수"] = oc["폐업수"].astype(int)
    oc["순증"] = oc["개업수"] - oc["폐업수"]
    oc.to_parquet(OUT / "openings_closings_monthly.parquet", index=False)

    # 생존율
    survival_rows = _build_survival(rest, as_of)
    survival = pd.DataFrame(survival_rows)
    survival.to_parquet(OUT / "survival.parquet", index=False)

    return {"as_of": as_of_str, "n_rows": n,
            "map_fail_rate": float(map_fail),
            "cat_fail_rate": float(cat_fail)}


def _survival_rate(group: pd.DataFrame, years: int, as_of: pd.Timestamp) -> tuple[float, int]:
    """년수 생존율 = {인허가일+years <= as_of} 중 (폐업일 없음 or 폐업일 >= 인허가일+years) 비율."""
    yd = pd.Timedelta(days=365.25 * years)
    eligible = group[group["인허가일"] + yd <= as_of]
    n = len(eligible)
    if n == 0:
        return (float("nan"), 0)
    survived = ((eligible["폐업일"].isna()) | (eligible["폐업일"] >= eligible["인허가일"] + yd)).sum()
    return (float(survived / n), int(n))


def _build_survival(rest: pd.DataFrame, as_of: pd.Timestamp) -> list[dict]:
    """행정동 × app_category 1년·3년 생존율. n<10이면 시군구로 fallback."""
    dong_meta = pd.read_parquet(OUT / "dong_meta.parquet")[["행정동명", "시군구"]].rename(
        columns={"행정동명": "dong"})
    rest2 = rest.merge(dong_meta, on="dong", how="left")

    # 시군구·업종 별 fallback 값
    city_rates: dict[tuple, tuple] = {}
    for (city, cat), grp in rest2.dropna(subset=["시군구"]).groupby(["시군구", "app_category"]):
        y1, n1 = _survival_rate(grp, 1, as_of)
        y3, n3 = _survival_rate(grp, 3, as_of)
        city_rates[(city, cat)] = (y1, n1, y3, n3)

    rows = []
    for (dong, cat), grp in rest2.groupby(["dong", "app_category"]):
        y1, n1 = _survival_rate(grp, 1, as_of)
        y3, n3 = _survival_rate(grp, 3, as_of)
        fallback = None
        if n3 < 10 or pd.isna(y3):
            city = grp["시군구"].iloc[0] if not grp["시군구"].isna().all() else None
            if city and (city, cat) in city_rates:
                y1b, n1b, y3b, n3b = city_rates[(city, cat)]
                y1, n1 = y1b, n1b
                y3, n3 = y3b, n3b
                fallback = f"시군구:{city}"
        rows.append({
            "dong": dong, "app_category": cat,
            "survival_1y": None if pd.isna(y1) else round(y1, 4),
            "survival_3y": None if pd.isna(y3) else round(y3, 4),
            "n_1y": n1, "n_3y": n3,
            "fallback": fallback,
        })
    return rows


# ---------- D6 읍면동 사업체 생멸 ----------

def build_dong_lifecycle() -> dict:
    """D6 KOSIS 읍면동 사업체 생멸.

    원본 구조: (기준연도, 시구분, 읍면동, 사업체구분, 생멸구분, 사업체수)
    - 사업체구분: 활동사업체 / 신생사업체 / 소멸사업체
    - 생멸구분: 소계 / 신규 / 사업장확장 / 폐업 / 사업장축소
    - 연도별 제공 항목 상이 (2018: 활동+소멸, 2019: 전부, 2020~: 활동+신생)

    집계 규칙
    - 활동 = 활동사업체 (생멸구분=소계)
    - 신생 = 신생사업체 전체 (신규 + 사업장확장)
    - 소멸 = 소멸사업체 전체 (폐업 + 사업장축소)
    """
    f = RAW / "d6_dong_biz_lifecycle.csv"
    if not f.exists():
        print(f"  [skip] {f.name} 없음 (D6)")
        return {"available": False}

    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            df = pd.read_csv(f, encoding=enc, dtype=str)
            break
        except UnicodeDecodeError:
            continue
    else:
        print(f"  [D6] 인코딩 실패 → 건너뜀")
        return {"available": False}

    df = df[df["시구분"].isin(["제주시", "서귀포시"])].copy()
    df = df[df["읍면동"] != "소계"]  # 시 합계 행 제거
    # 5 이하 비공개(*) · 누락(-) 처리
    df["flag_5이하"] = df["사업체수"] == "*"
    df["사업체수"] = pd.to_numeric(
        df["사업체수"].replace({"*": None, "-": None}), errors="coerce")
    df["기준연도"] = pd.to_numeric(df["기준연도"], errors="coerce").astype("Int64")

    # 사업체구분 → bucket (하위 생멸구분은 합산)
    bucket_map = {"활동사업체": "활동", "신생사업체": "신생", "소멸사업체": "소멸"}
    df["bucket"] = df["사업체구분"].map(bucket_map)
    df = df.dropna(subset=["bucket", "기준연도"])

    pivot = (df.pivot_table(index=["읍면동", "기준연도"], columns="bucket",
                            values="사업체수", aggfunc="sum")
               .reset_index()
               .rename(columns={"읍면동": "dong", "기준연도": "year"}))
    pivot["year"] = pivot["year"].astype(int)
    for col in ("활동", "신생", "소멸"):
        if col not in pivot.columns:
            pivot[col] = pd.NA

    # 신생률·소멸률 = 신생/소멸 / 전년도 활동
    pivot = pivot.sort_values(["dong", "year"])
    pivot["prev_active"] = pivot.groupby("dong")["활동"].shift(1)
    pivot["신생률"] = pd.to_numeric(pivot["신생"], errors="coerce") / pivot["prev_active"]
    pivot["소멸률"] = pd.to_numeric(pivot["소멸"], errors="coerce") / pivot["prev_active"]
    pivot["순증"] = pd.to_numeric(pivot["신생"], errors="coerce") - pd.to_numeric(pivot["소멸"], errors="coerce")

    # D4 행정동명과 매칭 — 매칭 안 되는 동명은 보존하되 리포트에 로그
    d4_dongs = set(pd.read_parquet(OUT / "dong_meta.parquet")["행정동명"].tolist())
    d6_dongs = set(pivot["dong"].unique())
    unmatched = sorted(d6_dongs - d4_dongs)
    if unmatched:
        print(f"  [D6] D4 행정동과 불일치 {len(unmatched)}개: {unmatched[:5]}...")

    pivot.to_parquet(OUT / "dong_lifecycle.parquet", index=False)
    return {"available": True,
            "rows": int(len(pivot)),
            "period_start": int(pivot["year"].min()),
            "period_end": int(pivot["year"].max()),
            "unmatched": len(unmatched)}


# ---------- D9 방문목적별 입도객 ----------

HUB_URL = "https://open.jejudatahub.net/api/proxy/DtaDa0555D801Da508DbDtt5t1bat1ta/{key}"


def _fetch_visitors_from_hub(key: str, start: str, end: str) -> pd.DataFrame | None:
    import httpx
    try:
        r = httpx.get(HUB_URL.format(key=key),
                      params={"startDate": start, "endDate": end},
                      timeout=30.0)
        r.raise_for_status()
        obj = r.json()
    except Exception as e:  # noqa: BLE001
        print(f"  [D9] 허브 API 실패: {type(e).__name__}: {str(e)[:120]}")
        return None
    # 응답 구조는 허브 표준: {totCnt, data: [...]}
    data = obj.get("data") or obj.get("result", {}).get("data") or []
    if not data:
        print(f"  [D9] 응답이 비어 있음")
        return None
    return pd.DataFrame(data)


def build_visitors() -> dict:
    """D9: 방문목적별 입도객. API 키가 있으면 호출→캐시 저장, 없으면 캐시만 사용."""
    cache = RAW / "d9_visitors_purpose.csv"
    key = os.getenv("JEJU_HUB_PROJECT_KEY", "").strip()
    df: pd.DataFrame | None = None

    if key:
        now = datetime.now().strftime("%Y%m")
        df = _fetch_visitors_from_hub(key, "201801", now)
        if df is not None and not df.empty:
            df.to_csv(cache, index=False, encoding="utf-8-sig")
            print(f"  [D9] 허브에서 {len(df)}행 수집 → {cache.name}")

    if df is None and cache.exists():
        df = pd.read_csv(cache)
        print(f"  [D9] 캐시 사용 ({len(df)}행)")

    if df is None or df.empty:
        print(f"  [skip] D9 (키·캐시 모두 없음)")
        return {"available": False}

    # 컬럼 표준화
    rename = {"dtYearMonth": "년월", "visitorCnt": "방문자수", "visitPurpose": "방문목적"}
    df = df.rename(columns={k: v for k, v in rename.items() if k in df.columns})
    if "년월" not in df.columns or "방문자수" not in df.columns:
        print(f"  [D9] 컬럼 매핑 실패: {list(df.columns)}")
        return {"available": False}

    df["년월"] = df["년월"].astype(str).str.replace("-", "").str[:6]
    df["년월"] = df["년월"].str[:4] + "-" + df["년월"].str[4:6]
    df["방문자수"] = pd.to_numeric(df["방문자수"], errors="coerce").fillna(0).astype(int)
    if "방문목적" not in df.columns:
        df["방문목적"] = "전체"
    df.to_parquet(OUT / "visitors_monthly.parquet", index=False)
    return {"available": True,
            "period_start": df["년월"].min(),
            "period_end": df["년월"].max()}


# ---------- 레지스트리 ----------

def build_registry(info: dict) -> None:
    """data/processed/registry.json — 데이터 시점·갱신 주기 메타."""
    reg = [
        {"id": "D1", "name": "업종별 카드 매출 (제주데이터허브 주제1)",
         "source": "jejudatahub.net/data/746",
         "period_start": "2018-01", "period_end": "2021-05",
         "as_of": "2021-05", "refresh": "none", "api": False},
        {"id": "D2", "name": "유동인구+카드 매출 (제주데이터허브 주제3)",
         "source": "jejudatahub.net/data/748",
         "period_start": "2017-01", "period_end": "2021-05",
         "as_of": "2021-05", "refresh": "none", "api": False},
        {"id": "D3", "name": "업종별 성별 카드 이용",
         "source": "jejudatahub.net/data/1048",
         "period_start": "2018-01", "period_end": "2025-06",
         "as_of": "2025-06", "refresh": "quarterly", "api": False},
        {"id": "D4", "name": "제주 상가(상권) 정보",
         "source": "jejudatahub.net/data/793",
         "period_start": "2025-09", "period_end": "2025-09",
         "as_of": "2025-09", "refresh": "monthly", "api": False},
    ]
    d5 = info.get("D5", {})
    if d5.get("as_of"):
        reg.append({"id": "D5", "name": "제주 음식점 목록(통합)",
                    "source": "jejudatahub.net/data/780 (LOCALDATA)",
                    "period_start": "1960-01", "period_end": d5["as_of"][:7],
                    "as_of": d5["as_of"], "refresh": "daily", "api": False})
    d6 = info.get("D6", {})
    if d6.get("available"):
        reg.append({"id": "D6", "name": "읍면동 사업체 생멸",
                    "source": "jejudatahub.net/data/830 (KOSIS)",
                    "period_start": f"{d6['period_start']}",
                    "period_end": f"{d6['period_end']}",
                    "as_of": f"{d6['period_end']}", "refresh": "yearly", "api": False})
    d9 = info.get("D9", {})
    if d9.get("available"):
        reg.append({"id": "D9", "name": "방문목적별 입도객",
                    "source": "jejudatahub.net/data/580",
                    "period_start": d9["period_start"], "period_end": d9["period_end"],
                    "as_of": d9["period_end"], "refresh": "monthly", "api": True})

    with (OUT / "registry.json").open("w", encoding="utf-8") as f:
        json.dump(reg, f, ensure_ascii=False, indent=2)


# ---------- 품질 게이트 ----------

def quality_gate() -> None:
    checks: list[tuple[str, bool, str]] = []
    dong = pd.read_parquet(OUT / "dong_meta.parquet")
    checks.append(("dong_meta rows == 43", len(dong) == 43, f"{len(dong)}"))
    sup = pd.read_parquet(OUT / "supply.parquet")
    cat_n = sup["app_category"].nunique()
    checks.append(("supply categories >= 10", cat_n >= 10, f"{cat_n}"))
    demand = pd.read_parquet(OUT / "demand_monthly.parquet")
    checks.append(("demand months in base period",
                   ((demand["년월"] >= "2018-01") & (demand["년월"] <= "2019-12")).any(),
                   f"min={demand['년월'].min()} max={demand['년월'].max()}"))
    base = demand[(demand["년월"] >= "2018-01") & (demand["년월"] <= "2019-12")]
    ac = base[(base["dong"] == "애월읍") & (base["app_category"] == "카페")]
    if len(ac) > 0:
        tour = (ac["이용금액_관광개별"].sum() + ac["이용금액_관광단체"].sum()) \
               / ac["이용금액_합계"].sum()
        checks.append(("애월읍·카페 관광 비중 0.70~0.80",
                       0.70 <= tour <= 0.80, f"{tour:.3f}"))
    foot = pd.read_parquet(OUT / "footfall_monthly.parquet")
    checks.append(("footfall dongs >= 40",
                   foot["dong"].nunique() >= 40, f"{foot['dong'].nunique()}"))
    trend = pd.read_parquet(OUT / "trend_yearly.parquet")
    checks.append(("trend years >= 5", trend["year"].nunique() >= 5, f"{trend['year'].nunique()}"))

    if (OUT / "survival.parquet").exists():
        sv = pd.read_parquet(OUT / "survival.parquet")
        y3 = sv["survival_3y"].dropna()
        checks.append(("survival_3y 0~1", y3.between(0, 1).all(), f"min={y3.min():.3f} max={y3.max():.3f}"))
    if (OUT / "openings_closings_monthly.parquet").exists():
        oc = pd.read_parquet(OUT / "openings_closings_monthly.parquet")
        checks.append(("openings≥0 폐업≥0", (oc["개업수"] >= 0).all() and (oc["폐업수"] >= 0).all(),
                       f"opens total {oc['개업수'].sum()}, closes {oc['폐업수'].sum()}"))

    failed = [c for c in checks if not c[1]]
    for name, ok, val in checks:
        print(f"  [{'OK' if ok else 'FAIL'}] {name} → {val}")
    if failed:
        raise SystemExit(f"[gate] {len(failed)}건 실패")


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    info: dict = {}
    print("[build] dong_meta");                build_dong_meta()
    print("[build] supply");                   build_supply()
    print("[build] demand");                   build_demand()
    print("[build] footfall");                 build_footfall()
    print("[build] trend");                    build_trend()
    print("[build] restaurants (D5)");         info["D5"] = build_restaurants()
    print("[build] dong_lifecycle (D6)");      info["D6"] = build_dong_lifecycle()
    print("[build] visitors (D9)");            info["D9"] = build_visitors()
    print("[build] registry.json");            build_registry(info)
    print("[gate] 품질 게이트");              quality_gate()
    print("[build] 완료 →", OUT)


if __name__ == "__main__":
    main()
