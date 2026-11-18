"""섬자리 API: Agent 실행, SSE 진행 스트림, 프론트 정적 파일 서빙."""
from __future__ import annotations

import json
import uuid
from pathlib import Path
from typing import Any

from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse

from agent import loop, store

load_dotenv()

app = FastAPI(title="섬자리 API", version="0.1.0")
STATIC = Path(__file__).parent / "static"
RUNS: dict[str, dict[str, Any]] = {}


class DiagnoseForm(BaseModel):
    category: str | None = None
    dong: str | None = None              # None = 상관없음 (지역 추천 모드)
    customer: str = "any"                # tourist | local | any
    ages: list[str] = []
    risk: str = "balanced"               # safe | balanced | aggressive
    question: str | None = None          # 자연어 입력 (선택)


@app.get("/api/health")
def health():
    return {"ok": True, "data_ready": store.is_ready()}


@app.get("/api/meta")
def meta():
    """TODO: 업종 목록, 행정동 목록(좌표), 데이터 기간."""
    return {"categories": [], "dongs": [], "period": "2018-01~2019-12"}


@app.post("/api/diagnose")
def diagnose(form: DiagnoseForm):
    run_id = uuid.uuid4().hex[:12]
    RUNS[run_id] = {"form": form.model_dump()}
    return {"run_id": run_id}


@app.get("/api/diagnose/{run_id}/events")
async def diagnose_events(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(404, "run not found")
    form = RUNS[run_id]["form"]

    async def gen():
        try:
            async for ev in loop.run(form):
                if ev["type"] == "report":
                    RUNS[run_id]["report"] = ev["report"]
                yield {"event": ev["type"], "data": json.dumps(ev, ensure_ascii=False)}
        except Exception as e:  # noqa: BLE001
            yield {"event": "error", "data": json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)}

    return EventSourceResponse(gen())


@app.get("/api/map/{layer}")
def map_layer(layer: str, category: str | None = None):
    """TODO: demand / tourism / supply / footfall 레이어 데이터."""
    if layer not in {"demand", "tourism", "supply", "footfall"}:
        raise HTTPException(400, "unknown layer")
    return {"layer": layer, "category": category, "points": []}


# 프론트 빌드 결과가 있으면 함께 서빙 (평가 환경: Python만으로 실행)
if (STATIC / "index.html").exists():
    app.mount("/assets", StaticFiles(directory=STATIC / "assets"), name="assets")

    @app.get("/{path:path}", include_in_schema=False)
    def spa(path: str):
        f = STATIC / path
        return FileResponse(f if f.is_file() else STATIC / "index.html")
