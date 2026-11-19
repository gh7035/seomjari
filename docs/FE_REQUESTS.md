# FE_REQUESTS

프론트엔드가 개발 중 발견한, 계약(SPEC §7.5 / §8 / CONTRACT) 보완이 필요한 사항을 기록한다.

## 2026-11-19

### 1. docs/CONTRACT.md 부재
- 지시받은 `docs/CONTRACT.md` 파일이 레포에 없음. 현재는 `docs/SPEC.md §7.5(리포트 스키마)` 및 `§8(API 계약)` 을 계약으로 간주하여 작업했다.
- 요청: `docs/CONTRACT.md` 를 공식화해 주면 프론트에서 import 가능한 JSON 스키마(또는 OpenAPI) 로도 반영하겠다.

### 2. GET /api/meta 응답 형식
- 프론트 기대 형식:
  ```json
  {
    "categories": ["카페", "한식당", ...],
    "dongs": [{ "name": "애월읍", "lon": 126.33, "lat": 33.46 }, ...],
    "period": { "base": "2018-01~2019-12", "recent": "2021-01~2021-05" }
  }
  ```
- `dongs` 길이 43, 좌표는 D4 점포 중앙값.

### 3. GET /api/map/{layer} 응답 형식
- 쿼리: `?category=카페&month=1..12`(선택).
- 응답:
  ```json
  {
    "layer": "demand",
    "points": [
      { "dong": "애월읍", "lon": 126.33, "lat": 33.46,
        "value": 123456, "tourism": 0.749,
        "monthly": [v1..v12] }
    ]
  }
  ```
- 프론트는 `month` 미지정시 월평균 `value` 를, 지정시 `monthly[month-1]` 을 기둥 높이에 사용.

### 4. Report 스키마 확장 요청
- SPEC §7.5 의 `signals` 외에, 근거 패널의 "월별 패턴 차트" 를 그리기 위해 다음 필드를 요청한다.
  ```json
  "monthly_pattern": {
    "labels": ["1월", ..., "12월"],
    "values": [v1..v12],
    "tourism_values": [t1..t12]   // optional
  }
  ```
- 없으면 프론트가 `/api/map/{layer}?category=...` 의 `monthly` 로 대체한다.

### 5. SSE 이벤트 확정
- `step.status`: `running | done`. `index` 는 0-based 순서 보장.
- `tool`: `{ name, args, summary }`. `summary` 는 한국어 1줄 (UI 로그에 그대로 노출).
- `report`: 최종 1회. `error` 는 발생 시 1회.

### 6. GET /api/stores 신규 엔드포인트 요청
- 지도 기둥 클릭 시 "해당 행정동 내 실 가게" 리스트를 상세 패널에 보여주기 위함.
- 데이터 소스: `data/processed/stores_points.parquet` (D4, 2025-09 기준).
- 쿼리 파라미터
  - `dong` (필수): 행정동명
  - `category` (선택): 지정 시 해당 업종만. 생략 시 전체.
  - `limit` (선택, 기본 20): 최대 반환 개수.
  - `near` (선택, `lon,lat`): 지정 좌표 기준 가까운 순으로 정렬.
- 응답
  ```json
  {
    "dong": "애월읍",
    "category": "카페",
    "total": 225,
    "items": [
      {
        "name": "○○카페",
        "address": "제주시 애월읍 ...",
        "lon": 126.33, "lat": 33.46,
        "category": "커피 전문점",
        "distance_m": 420
      }
    ]
  }
  ```
- `name`, `address` 는 D4 원본 컬럼에서 매핑.
- 가게가 전혀 없으면 `items: []`, `total: 0`.
- 프론트는 백엔드 미구현 상태에서는 "데이터 준비 중" 안내만 노출함.
