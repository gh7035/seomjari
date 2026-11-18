"""LLM 공급자 어댑터. LLM_PROVIDER 환경변수로 교체한다.

none: LLM 없이 규칙 기반 fallback (평가 중 API 장애 대비)
"""
from __future__ import annotations

import os


def provider() -> str:
    return os.getenv("LLM_PROVIDER", "none").lower()


def chat_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    """function calling 1회 호출. 공급자별 구현은 공급자 확정 후 작성."""
    p = provider()
    if p == "none":
        raise RuntimeError("LLM_PROVIDER=none: loop가 fallback 경로를 사용해야 함")
    raise NotImplementedError(f"provider '{p}' 미구현")
