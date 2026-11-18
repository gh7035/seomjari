"""전처리된 parquet을 한 번만 읽어 메모리에 들고 있는 저장소."""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import pandas as pd

TABLES = [
    "demand_monthly",
    "demand_age",
    "footfall_monthly",
    "supply",
    "stores_points",
    "trend_yearly",
    "dong_meta",
]


def data_dir() -> Path:
    return Path(os.getenv("DATA_DIR", "data/processed"))


@lru_cache(maxsize=None)
def table(name: str) -> pd.DataFrame:
    if name not in TABLES:
        raise KeyError(f"unknown table: {name}")
    path = data_dir() / f"{name}.parquet"
    if not path.exists():
        raise FileNotFoundError(f"{path} 없음. `make data`를 먼저 실행하세요.")
    return pd.read_parquet(path)


def is_ready() -> bool:
    return all((data_dir() / f"{t}.parquet").exists() for t in TABLES)
