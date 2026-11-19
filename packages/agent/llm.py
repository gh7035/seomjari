"""LLM 공급자 어댑터.

- `LLM_PROVIDER` 환경변수로 교체 (none | gemini | …)
- 운영: 타임아웃, 재시도(backoff), 자원 누수 방지, PI 격리 책임은 loop.py
"""
from __future__ import annotations

import time
from typing import Any

from .config import settings
from .log import get_logger, log_event

log = get_logger("agent.llm")


def provider() -> str:
    return settings().llm_provider


def chat_with_tools(messages: list[dict], tools: list[dict]) -> dict:
    """Function calling 1회 호출.

    OpenAI 호환 messages/tools.
    반환: {"text": str|None, "tool_calls": [{"name","arguments"}], "_raw_content"?}
    """
    s = settings()
    if s.llm_provider == "none":
        raise RuntimeError("LLM_PROVIDER=none: loop가 fallback 경로를 사용해야 함")
    if s.llm_provider == "gemini":
        return _with_retry(_gemini_chat, messages, tools)
    raise NotImplementedError(f"provider '{s.llm_provider}' 미구현")


# ---------- 재시도 래퍼 ----------

def _with_retry(fn, messages, tools):
    s = settings()
    last_exc: Exception | None = None
    for attempt in range(1, s.llm_retries + 2):
        try:
            return fn(messages, tools)
        except Exception as e:  # noqa: BLE001
            last_exc = e
            status = _status_code(e)
            retriable = status in {429, 500, 502, 503, 504, None} and attempt <= s.llm_retries
            log_event(log, 30 if retriable else 40, "llm_call_failed",
                      provider=s.llm_provider, model=s.llm_model, attempt=attempt,
                      status=status, error=type(e).__name__, retriable=retriable)
            if not retriable:
                raise
            time.sleep(min(2 ** attempt * 0.3, 2.0))
    assert last_exc is not None
    raise last_exc


def _status_code(e: Exception) -> int | None:
    try:
        from google.genai import errors as g_errors
        if isinstance(e, (g_errors.ServerError, g_errors.ClientError)):
            return int(getattr(e, "code", 0)) or None
    except Exception:  # noqa: BLE001
        pass
    for attr in ("status_code", "code"):
        v = getattr(e, attr, None)
        if isinstance(v, int):
            return v
    return None


# ---------- Gemini ----------

def _openai_tools_to_gemini(tools: list[dict]) -> list[dict]:
    decls = []
    for t in tools:
        f = t.get("function", t)
        decls.append({
            "name": f["name"],
            "description": f.get("description", ""),
            "parameters": f.get("parameters", {"type": "object", "properties": {}}),
        })
    return [{"function_declarations": decls}]


def _messages_to_gemini(messages: list[dict]) -> tuple[str, list[Any]]:
    """OpenAI messages → (system_instruction, Gemini contents).

    assistant 메시지의 `_raw_content`가 있으면 thought_signature 포함 원본 그대로 사용.
    """
    from google.genai import types as gtypes

    system_bits: list[str] = []
    contents: list[Any] = []
    for m in messages:
        role = m.get("role")
        if role == "system":
            system_bits.append(m.get("content", ""))
            continue
        if role == "tool":
            contents.append(gtypes.Content(
                role="user",
                parts=[gtypes.Part.from_function_response(
                    name=m.get("name", "tool"),
                    response={"content": m.get("content", "")},
                )],
            ))
            continue
        if role == "assistant":
            raw = m.get("_raw_content")
            if raw is not None:
                contents.append(raw)
                continue
            if m.get("content"):
                contents.append(gtypes.Content(
                    role="model", parts=[gtypes.Part(text=m["content"])],
                ))
            continue
        contents.append(gtypes.Content(
            role="user", parts=[gtypes.Part(text=m.get("content", ""))],
        ))
    return "\n\n".join(system_bits).strip(), contents


def _gemini_chat(messages: list[dict], tools: list[dict]) -> dict:
    from google import genai
    from google.genai import types as gtypes

    s = settings()
    if not s.llm_api_key:
        raise RuntimeError("LLM_API_KEY가 비어 있습니다 (.env 확인)")

    http_options = gtypes.HttpOptions(timeout=int(s.llm_timeout_s * 1000))
    client = genai.Client(api_key=s.llm_api_key, http_options=http_options)
    model = s.llm_model or "gemini-3.5-flash-lite"

    system_text, contents = _messages_to_gemini(messages)
    gtools = _openai_tools_to_gemini(tools) if tools else None

    cfg: dict[str, Any] = {"temperature": 0.2}
    if system_text:
        cfg["system_instruction"] = system_text
    if gtools:
        cfg["tools"] = gtools

    resp = client.models.generate_content(
        model=model, contents=contents,
        config=gtypes.GenerateContentConfig(**cfg),
    )

    text_parts: list[str] = []
    tool_calls: list[dict] = []
    raw_content = None
    for cand in getattr(resp, "candidates", []) or []:
        content = getattr(cand, "content", None)
        if content is not None:
            raw_content = content
        for part in getattr(content, "parts", []) or []:
            fn = getattr(part, "function_call", None)
            if fn is not None and getattr(fn, "name", None):
                tool_calls.append({
                    "name": fn.name,
                    "arguments": dict(getattr(fn, "args", {}) or {}),
                })
                continue
            txt = getattr(part, "text", None)
            if txt:
                text_parts.append(txt)

    log_event(log, 20, "llm_call_ok", provider=s.llm_provider, model=model,
              text_len=sum(len(t) for t in text_parts),
              tool_calls=len(tool_calls))
    return {
        "text": "\n".join(text_parts).strip() or None,
        "tool_calls": tool_calls,
        "_raw_content": raw_content,
    }
