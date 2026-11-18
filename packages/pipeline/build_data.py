"""data/raw CSV → data/processed parquet.

검증된 사실 (SPEC 5.2):
- D1, D2, D4 인코딩 CP949 / D3 UTF-8 BOM
- D1 '매장수'는 시 단위 값 → 사용 금지, 점포 수는 D4로 계산
- D1 법정동 72개 ⊂ D4 법정동명, D2 행정동 43개 ⊂ D4 행정동명
- D2 '년월' 표기가 파일마다 다름 (2019-01-01 / 21-Apr)

실행: python -m pipeline.build_data
"""
from __future__ import annotations

from pathlib import Path

RAW = Path("data/raw")
OUT = Path("data/processed")


def build_dong_meta():
    """D4 → 법정동→행정동 매핑, 행정동 중심 좌표, 시군구."""
    raise NotImplementedError


def build_supply():
    """D4 + category_map → 행정동 × app_category 점포 수, 점포 좌표."""
    raise NotImplementedError


def build_demand():
    """D1(_18, _19, _21) → 행정동 × app_category × 년월, 관광구분별 이용금액. 연령대 테이블 포함."""
    raise NotImplementedError


def build_footfall():
    """D2(_17~_21) → 행정동 × 년월 거주·근무·방문 인구 (년월 정규화)."""
    raise NotImplementedError


def build_trend():
    """D3 → app_category × 연도, 이용자구분별 이용금액."""
    raise NotImplementedError


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for step in (build_dong_meta, build_supply, build_demand, build_footfall, build_trend):
        print(f"[build] {step.__name__}")
        step()


if __name__ == "__main__":
    main()
