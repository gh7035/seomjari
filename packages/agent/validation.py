"""리포트 스키마·grounding 런타임 검증.

- LLM이 돌려준 report JSON이 `packages/schema/report.schema.json`과 맞는지
- 리포트 내 수치·지역·업종이 실제로 호출된 도구 결과에 나타났는지
"""
from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

_SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema" / "report.schema.json"
_schema_cache: dict | None = None


def report_schema() -> dict:
    global _schema_cache
    if _schema_cache is None:
        with _SCHEMA_PATH.open(encoding="utf-8") as f:
            _schema_cache = json.load(f)
    return _schema_cache


def _type_ok(value: Any, expected: Any) -> bool:
    if isinstance(expected, list):
        return any(_type_ok(value, t) for t in expected)
    mapping = {
        "string": str, "number": (int, float), "integer": int,
        "boolean": bool, "array": list, "object": dict, "null": type(None),
    }
    py = mapping.get(expected)
    if py is None:
        return True
    return isinstance(value, py)


def validate_report_shape(report: Any) -> list[str]:
    """스키마 핵심 필드만 가볍게 검증 (jsonschema 외부 의존 없이)."""
    errors: list[str] = []
    if not isinstance(report, dict):
        return ["report is not an object"]

    schema = report_schema()
    required = schema.get("required", [])
    for key in required:
        if key not in report:
            errors.append(f"missing required field: {key}")

    # signals
    allowed_names = {"관광 의존도", "계절 변동성", "경쟁 밀도", "수요 규모",
                     "유동 수요", "생존 리스크", "최근 개폐업"}
    allowed_levels = {"green", "yellow", "red", "unavailable"}
    for i, s in enumerate(report.get("signals") or []):
        if not isinstance(s, dict):
            errors.append(f"signals[{i}] not object"); continue
        if s.get("name") not in allowed_names:
            errors.append(f"signals[{i}].name invalid: {s.get('name')}")
        if s.get("level") not in allowed_levels:
            errors.append(f"signals[{i}].level invalid: {s.get('level')}")

    # evidence
    allowed_sources = {"D1", "D2", "D3", "D4", "D5", "D6", "D9", "D10"}
    for i, e in enumerate(report.get("evidence") or []):
        if not isinstance(e, dict):
            errors.append(f"evidence[{i}] not object"); continue
        if e.get("source") not in allowed_sources:
            errors.append(f"evidence[{i}].source invalid: {e.get('source')}")
        # detail 필드 필수 (SPEC 스키마), note로 잘못 보내는 경우 보정 힌트
        if "detail" not in e:
            errors.append(f"evidence[{i}] missing 'detail'")

    # map
    m = report.get("map") or {}
    if m.get("layer") not in {"demand", "tourism", "supply", "footfall", "survival"}:
        errors.append(f"map.layer invalid: {m.get('layer')}")

    score = report.get("score")
    if score is not None:
        if not _type_ok(score, "number") or not (0 <= float(score) <= 100):
            errors.append(f"score out of range or wrong type: {score}")
    # confidence
    conf = report.get("confidence")
    if conf is not None and conf not in {"normal", "low"}:
        errors.append(f"confidence invalid: {conf}")
    if conf == "low" and score is not None:
        errors.append("confidence=low 이면 score 는 null 이어야 함")

    if not isinstance(report.get("summary"), str):
        errors.append("summary must be string")

    return errors


_NUM_PATTERNS = [
    r"\d+\.\d+%", r"\d+%", r"\d+\.\d+배", r"\d+배",
    r"\d+(?:,\d{3})+원", r"\d{4,}원", r"\d+위", r"\d+/\d+",
    r"\d+점",
    r"순증\s*[+-]?\d+",
    r"\d{1,2}월",
]


def extract_numbers(text: str) -> set[str]:
    out: set[str] = set()
    for p in _NUM_PATTERNS:
        out.update(re.findall(p, text))
    return out


def grounding_stray(report: dict, tool_summaries: list[str]) -> set[str]:
    """리포트 텍스트의 수치 중 도구 요약·signals에서 찾을 수 없는 것."""
    haystack = " ".join(tool_summaries)

    report_text = " ".join([
        str(report.get("summary", "")),
        *[str(e.get("detail", e.get("note", ""))) for e in report.get("evidence") or []],
        *[f"{a.get('why','')} {a.get('score','')}" for a in report.get("alternatives") or []],
    ])
    nums = extract_numbers(report_text)
    return {n for n in nums if n not in haystack}


def coerce_evidence_note_to_detail(report: dict) -> None:
    """LLM이 가끔 `detail` 대신 `note`로 채우는 경우 보정."""
    for e in report.get("evidence") or []:
        if isinstance(e, dict) and "detail" not in e and "note" in e:
            e["detail"] = e.pop("note")
