"""Agent 루프. 진행 이벤트를 비동기 제너레이터로 내보낸다.

이벤트 형식: {"type": "step" | "tool" | "report" | "error", ...}
API는 이 이벤트를 그대로 SSE로 전달한다.
"""
from __future__ import annotations

import asyncio
from typing import Any, AsyncIterator

from . import llm

STEPS = ["의도 파악", "분석 계획", "도구 실행", "결과 검증", "리포트 작성"]


async def run(form: dict[str, Any]) -> AsyncIterator[dict[str, Any]]:
    """TODO: LLM function calling 루프 + 검증·재계획. 현재는 뼈대용 더미 흐름."""
    for i, name in enumerate(STEPS):
        yield {"type": "step", "index": i, "name": name, "status": "running"}
        await asyncio.sleep(0.3)
        yield {"type": "step", "index": i, "name": name, "status": "done"}

    yield {
        "type": "report",
        "report": {
            "summary": f"[뼈대] {form.get('dong') or '전체'} / {form.get('category')} 진단 예정",
            "target": {"dong": form.get("dong"), "category": form.get("category")},
            "signals": [],
            "score": 0,
            "alternatives": [],
            "trend": None,
            "evidence": [],
            "limitations": ["뼈대 단계: 도구 미구현"],
            "map": {"layer": "demand", "highlight": [form["dong"]] if form.get("dong") else []},
        },
        "mode": "fallback" if llm.provider() == "none" else "llm",
    }
