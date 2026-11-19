"""전처리된 parquet을 한 번 읽어 메모리에 들고 있는 저장소.

운영 고려
- 7개 테이블 모두 수 MB 수준이라 전부 메모리에 둬도 안전.
- `lru_cache`는 TABLES 개수만큼만 캐싱하도록 명시 (누수 방지).
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import pandas as pd

from .config import settings

TABLES = [
    "demand_monthly",
    "demand_age",
    "footfall_monthly",
    "supply",
    "stores_points",
    "trend_yearly",
    "dong_meta",
    # 신규 (D5/D6/D9) — 있을 때만 로드된다
    "restaurants",
    "openings_closings_monthly",
    "survival",
    "dong_lifecycle",
    "visitors_monthly",
]

# is_ready는 필수 테이블만 확인한다 (D5/D6/D9는 선택).
REQUIRED = {
    "demand_monthly", "demand_age", "footfall_monthly",
    "supply", "stores_points", "trend_yearly", "dong_meta",
}


def data_dir() -> Path:
    return settings().data_dir


@lru_cache(maxsize=len(TABLES))
def table(name: str) -> pd.DataFrame:
    if name not in TABLES:
        raise KeyError(f"unknown table: {name}")
    path = data_dir() / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음. `make data`를 먼저 실행하세요.")
    return pd.read_parquet(path)


def is_ready() -> bool:
    return all((data_dir() / f"{t}.parquet").exists() for t in REQUIRED)


def has_optional(name: str) -> bool:
    """D5/D6/D9 등 선택 테이블이 빌드돼 있는지."""
    return (data_dir() / f"{name}.parquet").exists()


def reload() -> None:
    """데이터 교체 시 캐시 비우기."""
    table.cache_clear()
