"""섬자리 API: Agent 실행, SSE 진행 스트림, 프론트 정적 파일 서빙.

운영 강화
- 세션 저장: SQLite (`agent.sessions`) — 재시작 후에도 run_id 조회 가능
- 요청 추적: X-Request-ID 자동 발급, 구조화 로그
- 안정성: 전역 예외 핸들러, 레이트리밋, CORS (환경변수 제어)
- 헬스체크: /livez(프로세스) vs /readyz(데이터+세션DB 준비)
- 입력 검증: pydantic + Literal + 길이 제한
- 메트릭: /api/metrics (최근 세션 수, 모드별 비율)
"""
from __future__ import annotations

import asyncio
import json
import uuid
from pathlib import Path
from typing import Any, Literal

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException, Response
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, field_validator
from sse_starlette.sse import EventSourceResponse

load_dotenv()  # Settings 초기화 전에

from agent import loop, sessions, store  # noqa: E402
from agent.config import settings  # noqa: E402
from agent.log import get_logger, log_event, setup_logging  # noqa: E402
from agent.tools import BASE_PERIOD  # noqa: E402
from apps.api.middleware import install as install_middleware  # noqa: E402

setup_logging()
log = get_logger("api.main")

app = FastAPI(title="섬자리 API", version="0.2.0")
install_middleware(app)
STATIC = Path(__file__).parent / "static"


# ---------- 요청 스키마 (운영 검증 강화) ----------

Customer = Literal["any", "tourist", "local"]
Risk = Literal["safe", "balanced", "aggressive"]


class DiagnoseForm(BaseModel):
    category: str | None = Field(default=None, max_length=50)
    dong: str | None = Field(default=None, max_length=50)
    customer: Customer = "any"
    ages: list[str] = Field(default_factory=list, max_length=10)
    risk: Risk = "balanced"
    question: str | None = Field(default=None, max_length=500)

    @field_validator("category", "dong", "question", mode="before")
    @classmethod
    def _strip(cls, v):
        if isinstance(v, str):
            v = v.strip()
            return v or None
        return v


class ChatQuery(BaseModel):
    run_id: str | None = Field(default=None, max_length=32)
    question: str = Field(..., min_length=1, max_length=500)


# ---------- 헬스 ----------

@app.get("/livez")
def livez():
    """프로세스 생존."""
    return {"ok": True}


@app.get("/readyz")
def readyz():
    """의존성 준비도. 하나라도 빠지면 503."""
    s = settings()
    checks = {
        "data": store.is_ready(),
        "session_db": s.session_db.parent.exists(),
    }
    if not all(checks.values()):
        raise HTTPException(503, {"ready": False, **checks})
    return {"ready": True, **checks}


@app.get("/api/health")
def health():
    """레거시 호환. UI는 이쪽을 씀."""
    return {"ok": True, "data_ready": store.is_ready()}


# ---------- 메타 ----------

CACHE_60S = {"Cache-Control": "public, max-age=60, stale-while-revalidate=120"}


@app.get("/api/meta")
def meta(response: Response):
    if not store.is_ready():
        raise HTTPException(503, "data not ready — run `make data`")
    sup = store.table("supply")
    dong = store.table("dong_meta")
    reg_path = store.data_dir() / "registry.json"
    registry = []
    if reg_path.exists():
        with reg_path.open(encoding="utf-8") as f:
            registry = json.load(f)
    for k, v in CACHE_60S.items():
        response.headers[k] = v
    return {
        "categories": sorted(sup["app_category"].unique().tolist()),
        "dongs": [
            {"name": r["행정동명"], "city": r["시군구"],
             "lon": float(r["lon"]), "lat": float(r["lat"]),
             "type": r["도심_읍면"]}
            for _, r in dong.iterrows()
        ],
        "period": {"base": BASE_PERIOD, "recent": "2021-01~2021-05"},
        "registry": registry,
    }


# ---------- 진단 ----------

@app.post("/api/diagnose")
def diagnose(form: DiagnoseForm):
    run_id = uuid.uuid4().hex[:12]
    sessions.put_run(run_id, form.model_dump())
    log_event(log, 20, "diagnose_started", run_id=run_id,
              category=form.category, dong=form.dong, risk=form.risk)
    return {"run_id": run_id}


@app.get("/api/diagnose/{run_id}/events")
async def diagnose_events(run_id: str):
    sess = sessions.get_run(run_id)
    if sess is None:
        raise HTTPException(404, "run not found")
    form = sess["form"]

    async def gen():
        try:
            async for ev in loop.run(form):
                if ev["type"] == "report":
                    sessions.set_report(run_id, ev["report"], ev.get("mode", "fallback"))
                yield {"event": ev["type"],
                       "data": json.dumps(ev, ensure_ascii=False, default=str)}
        except asyncio.CancelledError:  # 클라이언트 연결 종료
            log_event(log, 20, "sse_client_disconnect", run_id=run_id)
            raise
        except Exception as e:  # noqa: BLE001
            log_event(log, 40, "sse_stream_error", run_id=run_id, error=str(e))
            yield {"event": "error",
                   "data": json.dumps({"type": "error", "message": str(e)},
                                       ensure_ascii=False)}

    return EventSourceResponse(gen())


# ---------- 후속 채팅 ----------

@app.post("/api/chat")
def chat(q: ChatQuery):
    from agent.tools import resolve_category, resolve_place

    PARTICLES = ("은", "는", "이", "가", "을", "를", "의", "로", "에", "에서", "도")

    def _trim(tok: str) -> list[str]:
        out = [tok]
        for p in PARTICLES:
            if tok.endswith(p) and len(tok) > len(p):
                out.append(tok[:-len(p)])
        return out

    prev = sessions.get_run(q.run_id or "")
    prev_form = (prev or {}).get("form") or {}

    place_hint = None
    cat_hint = None
    for raw in q.question.replace("?", " ").split():
        for token in _trim(raw):
            if not place_hint:
                r = resolve_place(token)
                if r.get("dong"):
                    place_hint = r["dong"]
            if not cat_hint:
                r = resolve_category(token)
                if r.get("app_category"):
                    cat_hint = r["app_category"]
            if place_hint and cat_hint:
                break

    new_form = {
        "category": cat_hint or prev_form.get("category"),
        "dong": place_hint or prev_form.get("dong"),
        "customer": prev_form.get("customer", "any"),
        "ages": [], "risk": prev_form.get("risk", "balanced"),
        "question": q.question,
    }
    run_id = uuid.uuid4().hex[:12]
    sessions.put_run(run_id, new_form, parent=q.run_id)
    log_event(log, 20, "chat_follow_up", run_id=run_id, parent=q.run_id,
              parsed_dong=place_hint, parsed_category=cat_hint)
    return {"run_id": run_id, "parsed": {
        "dong": new_form["dong"], "category": new_form["category"]}}


# ---------- 지도 ----------

@app.get("/api/map/{layer}")
def map_layer(layer: str, response: Response,
              category: str | None = None, month: int | None = None):
    if layer not in {"demand", "tourism", "supply", "footfall", "survival"}:
        raise HTTPException(400, "unknown layer")
    if not store.is_ready():
        raise HTTPException(503, "data not ready")
    if month is not None and not (0 <= month <= 12):
        raise HTTPException(400, "month must be 0..12")
    if category is not None and len(category) > 50:
        raise HTTPException(400, "category too long")

    meta_df = store.table("dong_meta").set_index("행정동명")
    demand = store.table("demand_monthly")
    base = demand[(demand["년월"] >= "2018-01") & (demand["년월"] <= "2019-12")].copy()

    cat = base[base["app_category"] == category] if category else base
    if month and 1 <= month <= 12:
        mm = f"{month:02d}"
        cat = cat[cat["년월"].str[5:7] == mm]

    g = cat.groupby("dong")
    tourism_num = g["이용금액_관광개별"].sum() + g["이용금액_관광단체"].sum()
    tourism_den = g["이용금액_합계"].sum().replace(0, pd.NA)
    tourism_ratio = (tourism_num / tourism_den).fillna(0)
    months_count = g["년월"].nunique().replace(0, 1)
    monthly_avg = g["이용금액_합계"].sum() / months_count

    sup = store.table("supply")
    if category:
        sup = sup[sup["app_category"] == category]
    n_stores = sup.groupby("dong")["n_stores"].sum()

    if layer == "supply":
        value_series = n_stores
    elif layer == "footfall":
        foot = store.table("footfall_monthly")
        value_series = foot.groupby("dong")["방문인구"].mean()
    elif layer == "tourism":
        value_series = tourism_ratio
    elif layer == "survival":
        # 높이 = 점포 수, 색 = 3년 생존율 (낮을수록 빨강)
        if store.has_optional("survival"):
            sv = store.table("survival")
            if category:
                sv = sv[sv["app_category"] == category]
            value_series = n_stores
            # tourism_ratio 대신 (1 - survival_3y)를 색상용으로 반환
            sv_rate = sv.groupby("dong")["survival_3y"].mean()
            tourism_ratio = (1 - sv_rate).clip(lower=0, upper=1).fillna(0.5)
        else:
            value_series = n_stores
    else:
        value_series = monthly_avg

    # 월별 패턴(길이 12) — demand/tourism 레이어에서만 의미 있음. 카테고리 미지정은 생략.
    monthly_map: dict[str, list[float]] = {}
    if category and layer in {"demand", "tourism", "supply"}:
        c2 = cat.assign(m=cat["년월"].str[5:7].astype(int))
        mo = c2.groupby(["dong", "m"])["이용금액_합계"].mean().unstack("m")
        for d_ in mo.index:
            vals = [float(mo.loc[d_, m]) if m in mo.columns and pd.notna(mo.loc[d_, m]) else 0.0
                    for m in range(1, 13)]
            monthly_map[d_] = vals

    points = []
    for name, row in meta_df.iterrows():
        pt = {
            "dong": name,
            "lon": float(row["lon"]), "lat": float(row["lat"]),
            "value": float(value_series.get(name, 0) or 0),
            "tourism": float(tourism_ratio.get(name, 0) or 0),
            "stores": int(n_stores.get(name, 0) or 0),
        }
        if name in monthly_map:
            pt["monthly"] = monthly_map[name]
        points.append(pt)
    for k, v in CACHE_60S.items():
        response.headers[k] = v
    return {"layer": layer, "category": category, "month": month, "points": points}


# ---------- 가게 상세 ----------

import math


def _haversine_m(lon1, lat1, lon2, lat2):
    R = 6_371_000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlam = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return 2 * R * math.asin(math.sqrt(a))


@app.get("/api/stores")
def stores(response: Response, dong: str, category: str | None = None,
           limit: int = 20, near: str | None = None):
    """행정동 내 실 가게 상세 (D4, 2025-09)."""
    if not store.is_ready():
        raise HTTPException(503, "data not ready")
    if len(dong) > 50 or (category and len(category) > 50):
        raise HTTPException(400, "dong/category too long")
    if not (1 <= limit <= 200):
        raise HTTPException(400, "limit out of range (1..200)")

    pts = store.table("stores_points")
    sub = pts[pts["dong"] == dong]
    if category:
        sub = sub[sub["app_category"] == category]
    total = int(len(sub))

    near_lon = near_lat = None
    if near:
        try:
            near_lon, near_lat = map(float, near.split(","))
        except (ValueError, TypeError):
            raise HTTPException(400, "near must be 'lon,lat'")
        sub = sub.copy()
        sub["distance_m"] = sub.apply(
            lambda r: _haversine_m(float(r["lon"]), float(r["lat"]), near_lon, near_lat),
            axis=1,
        )
        sub = sub.sort_values("distance_m")

    items = []
    for _, r in sub.head(limit).iterrows():
        item = {
            "name": r.get("name", ""),
            "address": r.get("address", ""),
            "lon": float(r["lon"]), "lat": float(r["lat"]),
            "category": r.get("sub_category", r.get("app_category", "")),
        }
        if near:
            item["distance_m"] = int(round(r["distance_m"]))
        items.append(item)
    for k, v in CACHE_60S.items():
        response.headers[k] = v
    return {
        "dong": dong, "category": category, "total": total,
        "limit": limit, "items": items,
        "source": "D4", "as_of": "2025-09",
    }


# ---------- 메트릭 ----------

@app.get("/api/metrics")
def metrics():
    """최근 세션 카운트. 운영에서는 Prometheus endpoint로 대체 권장."""
    return {
        "sessions_last_1h": sessions.count_recent(3600),
        "sessions_last_10m": sessions.count_recent(600),
        "provider": settings().llm_provider,
        "model": settings().llm_model,
    }


# ---------- 정적 서빙 ----------

if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if f.is_file() else STATIC / "index.html")
