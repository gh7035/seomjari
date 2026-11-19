# 섬자리 데이터 활용 명세

## 1. 사용 데이터 (모두 제주데이터허브)

| ID | 데이터셋 | 파일 | 기간 | 지역 단위 | 인코딩 |
|---|---|---|---|---|---|
| D1 | 주제1: 제주 예비창업자를 위한 업종별 카드 매출과 매장수 데이터 활용 매쉬업결과 | `data/raw/d1_card_{18,19,21}.csv` | 2018-01~2019-12, 2021-01~2021-05 | 법정동 73개 | CP949 |
| D2 | 주제3: 상권분석을 위한 유동인구에 따른 카드 매출액 변화 데이터 활용 매쉬업결과 | `data/raw/d2_footfall_{17,18,19,20,21}.csv` | 2017-01~2021-05 | 행정동 43개 | CP949 |
| D3 | 업종별 성별 카드 이용 정보 | `data/raw/d3_industry_gender.csv` | 2018-01~2025-06 | 제주 전체 | UTF-8 BOM |
| D4 | 제주특별자치도 상가(상권) 정보 | `data/raw/d4_stores.csv` | 2025-09 | 행정동+법정동+좌표 | CP949 |
| **D5** | **제주특별자치도 음식점 목록(통합) · LOCALDATA 원천** | `data/raw/d5_restaurants.csv` | **1960~2025-08-29 (AS_OF 2025-09-02)** | **점포 (주소)** | CP949 |
| D5s | 같은 데이터의 영업·폐업 요약 | `data/raw/d5_restaurants_summary.csv` | | | CP949 |
| **D6** | **읍면동 사업체 생멸 (KOSIS 원천, 허브 830)** | `data/raw/d6_dong_biz_lifecycle.csv` | 2018~2023 | 읍면동 | — |
| **D9** | **방문목적별 입도객 현황 (허브 580, API)** | `data/raw/d9_visitors_purpose.csv` 캐시 | 2018-01~ 최근 | 제주 전체 월 | UTF-8 BOM |

- **D6·D9는 원본이 없으면 그 단계만 건너뛰고 경고 로그 후 다음 단계 진행.** 다른 데이터로 리포트는 정상 생성.
- **D5 파일명 영문화**: 원본 제공 파일명("제주특별자치도음식점목록(통합).csv")을 `d5_restaurants.csv`로 리네이밍. 내용 바이트는 변경 없음.

**이용 조건**: 제주데이터허브 공공데이터 이용 약관에 따름(상업·비상업 활용 가능, 출처 표기). 본 프로젝트는 비상업 데모 용도.

## 2. 데이터 품질 검증 사실

전처리 코드(`packages/pipeline/build_data.py`)와 매핑표(`packages/pipeline/category_map.csv`)는 아래 실측에 따라 작성됨.

- D1의 `매장수`는 **시 단위 값**(제주시 전 동 동일, 서귀포시 전 동 동일) → **사용 금지**. 점포 수는 D4에서 계산.
- D1 법정동 **73개** ⊂ D4 `법정동명`에 100% 존재.
- D2 행정동 **43개** ⊂ D4 `행정동명`에 100% 존재.
- `app_category`는 **16개**다. D1 업종명이 있는 **11개**만 카드 수요 신호가 나오고, PC방·미용실·네일샵·헬스장·노래방 5개는 D4 점포만 매핑된다(아래 §3).
- D1 업종 42개 중 **40개**가 D3 `biz_nm`과 문자열 일치한다. `trend_yearly.parquet`은 만들 수 있다. 리포트 도구 `get_trend`는 미구현이다.
- D2 `년월` 표기가 파일마다 다름: `YYYY-MM-DD`(_17~_20) vs `YY-MMM` (예: `21-Apr`, _21). 파이프라인에서 `YYYY-MM`로 정규화.
- D1의 `연령대`, `성별`에 결측 및 `알수없음` 존재(법인 이용 등). 연령 통계에서 `알수없음` 제외.
- 이용금액은 특정 카드사 기준 표본일 가능성 → UI는 **비중·배율·순위** 위주로 표시.
- D4 `표준산업분류명` 값 자체에 `;`가 포함(예: `피자; 햄버거; 샌드위치…`) → 매핑표의 복수 D4 구분자는 `|` 사용.

## 3. 업종 매핑 (`packages/pipeline/category_map.csv`)

앱 업종 16개. 표의 앞 11개는 D1 업종명이 있다. 뒤 5개는 D1·D5가 비어 있고 D4만 있다. 이 5개는 진단 시 점수를 보류한다.

| app_category | d1_업종명 | d4_표준산업분류명 (`|` 구분) |
|---|---|---|
| 카페 | 비알콜 음료점업 | 커피 전문점 / 기타 비알코올 음료점업 |
| 한식당 | 한식 음식점업 | 한식 일반/면/육류/해산물 요리 전문점 4종 |
| 양식당 | 서양식 음식점업 | 서양식 음식점업 |
| 일식당 | 일식 음식점업 | 일식 음식점업 |
| 중식당 | 중식 음식점업 | 중식 음식점업 |
| 술집 | 기타 주점업 | 기타 주점업 / 생맥주 전문점 |
| 베이커리 | 빵 및 과자류 소매업 | 제과점업 / 빵류·과자류·당류 소매업 |
| 편의점 | 체인화 편의점 | 체인화 편의점 |
| 기념품점 | 관광 민예품 및 선물용품 소매업 | 기념품·관광 민예품·장식용품 소매업 |
| 소형숙박 | 여관업 | 여관업 / 민박업 |
| 패스트푸드 | 피자, 햄버거, 샌드위치 및 유사 음식점업 | 피자·햄버거·샌드위치 유사 음식점업 |
| PC방 | (없음) | 컴퓨터 게임방 운영업 |
| 미용실 | (없음) | 두발 미용업 / 이용업 |
| 네일샵 | (없음) | 피부 미용업 |
| 헬스장 | (없음) | 체력 단련시설 운영업 |
| 노래방 | (없음) | 노래 연습장 운영업 |

## 4. 전처리 흐름 (`make data`)

```
data/raw/ (CSV)
   │
   ├─ build_dong_meta()   D4 → 행정동 43개 메타(시군구, 중심 좌표 중앙값, 도심/읍면)
   ├─ build_supply()      D4 × category_map → 행정동×업종 점포수 + 점포 좌표
   ├─ build_demand()      D1 × category_map × 법정동→행정동 매핑
   │                        → 월별 관광구분(도민/관광개별/관광단체/기타) 이용금액
   │                        + 연령대 비중
   ├─ build_footfall()    D2 년월 정규화 → 행정동×월 거주·근무·방문 인구
   ├─ build_trend()       D3 → 업종×연도 이용자구분(도민/내국인/외국인/기타) 이용금액
   ├─ build_restaurants() D5 → restaurants · survival · openings_closings_monthly
   ├─ build_dong_lifecycle()  D6 → dong_lifecycle (원본 없으면 이 단계만 건너뜀)
   └─ build_visitors()    D9 → visitors_monthly (원본·키가 없으면 건너뜀)
            ↓
data/processed/ (parquet)
   ├─ dong_meta.parquet
   ├─ supply.parquet · stores_points.parquet
   ├─ demand_monthly.parquet · demand_age.parquet
   ├─ footfall_monthly.parquet
   ├─ trend_yearly.parquet
   ├─ restaurants.parquet · survival.parquet · openings_closings_monthly.parquet
   └─ dong_lifecycle.parquet   (제출본에 있음. visitors_monthly.parquet 은 없음)
```

**법정동 → 행정동 매핑**: D4 전체 점포의 `(법정동명, 행정동명)` 쌍에서 법정동별 최빈값 행정동을 사용. 읍/면은 자기 자신.

**수요 버킷 (D1)**
- `이용금액_도민` = (`관광구분`=도민) OR (`이용자 구분`=제주도민)
- `이용금액_관광개별` = `관광구분`=개별
- `이용금액_관광단체` = `관광구분`=단체
- `이용금액_기타` = 그 외(법인·`관광구분` NaN 등)
- `이용금액_합계` = 네 항목 합

## 5. 지표 정의 (`packages/agent/tools.py`)

**기준 기간**: 2018-01 ~ 2019-12 (코로나 이전 정상 2년). 2021-01~05는 계산에 넣지 않는다. 화면 헤더는 이 기준 기간만 보여 준다.

| 지표 | 키 | 방향 | 계산식 |
|---|---|---|---|
| 관광 의존도 | tour | high_red | (관광개별+관광단체)/합계 |
| 계절 변동성 | season | high_red | 월별 2년 평균 패턴의 max/min |
| 수요 규모 | demand | low_red | 기준 기간 월평균 이용금액의 업종 내 순위 |
| 유동 수요 | footfall | low_red | D2 방문인구 월평균 (업종 무관) |
| 경쟁 밀도 | comp | high_red | 점포수(D4)/월평균 매출(억원). 카드가 없으면 점포수 백분위 |
| 생존 리스크 | survival | low_red | D5 3년 생존율 (중도절단, n<10이면 시군구 대체) |
| 최근 개폐업 | churn | high_red | D5 최근 24개월 폐업/개업 |

D3 연도별 소비는 `trend_yearly.parquet`까지만 있고 위 7개 신호에 들어가지 않는다.

**신호등**: 비교 집단 백분위의 3분위. high_red는 하위 1/3 🟢, 중간 🟡, 상위 1/3 🔴. low_red(수요 규모·유동 수요·생존 리스크)는 백분위를 뒤집어 낮은 값이 🔴다.

**종합 점수 (0~100)** — 가용 신호가 3개 미만이거나 수요 계열(수요 규모·유동 수요)이 하나도 없으면 점수는 null이다. 그 외에는 가용 신호 가중치만 재정규화한다.

```
risk = percentile                  (high_red)
risk = 1 - percentile              (low_red)
score = round(100 × (1 − Σ norm_w × risk))
```

기본 가중치: tour 20, season 15, comp 15, demand 15, footfall 15, survival 20, churn 15.
- 리스크 '안정형' → tour +10, season +5, survival +10
- 리스크 '공격형' → tour −5, season −5, demand +10
- 주 고객 '관광객' → tour = max(5, tour − 15)
- 주 고객 '도민' → tour +10

## 6. 외부 데이터·오픈소스 목록

**데이터** (모두 제주데이터허브)
- D1 https://jejudatahub.net/data/view/data/746
- D2 https://jejudatahub.net/data/view/data/748
- D3 https://jejudatahub.net/data/view/data/1048
- D4 https://jejudatahub.net/data/view/data/793
- D5 https://jejudatahub.net/data/view/data/780
- D6 https://jejudatahub.net/data/view/data/830

**통계 인용** (기획서 근거)
- KOSIS 기업생멸행정통계 — 신생률·생존율
- 한국은행 제주본부 — 청년 창업 폐업률

**오픈소스 라이브러리** (상세 버전은 `pyproject.toml`, `apps/web/package.json`)
- 백엔드: FastAPI, uvicorn, sse-starlette, pandas, pyarrow, pydantic, httpx, python-dotenv
- 프론트: React 18, Vite 5, TypeScript 5, deck.gl 9 (`@deck.gl/core`·`layers`·`aggregation-layers`·`react`), recharts

## 7. D5/D6/D9 전처리 흐름

### D5 음식점 통합목록
- 51,111행, 인허가 1960~2025-08-29. `AS_OF = 2025-09-02` (`데이터갱신일자`·`인허가일자`·`폐업일자` 중 최댓값).
- **지역 매핑**: `소재지전체주소`에서 `(제주시|서귀포시) <법정동/읍/면>` 패턴을 뽑아 D4의 법정동→행정동 최빈값 매핑으로 행정동 부여. 실패 시 `도로명전체주소`로 보조 추출. 실측 실패율 **0.2%** (목표 ≤5%).
- **업종 매핑**: `category_map.csv`의 `d5_업종소분류` 컬럼 사용. 매핑 실패 22.5% (한식에 세부 소분류가 섞여 있어 분석 대상 외는 그대로 제외).
- **날짜 파싱**: 원본이 `20060206.0` 형태(float→str 흔적)로 와서 `.0` 접미 제거 후 `YYYYMMDD` 파싱.
- **산출물**
  - `restaurants.parquet`: 점포 단위 (dong, app_category, 인허가일, 폐업일, is_open, 영업기간_일)
  - `openings_closings_monthly.parquet`: 행정동×업종×년월 개업·폐업·순증
  - `survival.parquet`: 행정동×업종 1년·3년 생존율, n, fallback (n<10이면 시군구값으로 대체)

### D5 생존 지표 (중도절단 처리)
```
3년 생존율 = {인허가일 + 3년 ≤ AS_OF} 중 (폐업일 없음 OR 폐업일 ≥ 인허가일 + 3년) 비율
```
- 인허가 후 3년이 되지 않은 점포는 분모에서 **제외** (아직 알 수 없음).
- 영업 중 점포의 영업기간 = `AS_OF − 인허가일`.
- 표본 수 `n_3y < 10` 이면 **시군구 단위 값**으로 대체, `fallback="시군구:제주시"` 등으로 표기.

### D6 읍면동 사업체 생멸 (원본 CSV가 없으면 빌드만 건너뜀)
- 2018년은 활동·소멸만, 2019년은 활동·신생만 제공 (연도별 제공 항목 상이).
- `*` (값 5 이하) → NaN + `flag_5이하` 플래그, `-` → NaN.
- `시구분 == 소계` 합계 행 제거.
- 산출물: `dong_lifecycle.parquet` (행정동 × 연도, 신생률·소멸률·순증).

### D9 방문목적별 입도객 (API·원본 없음·현재 건너뜀)
- `JEJU_HUB_PROJECT_KEY` 환경변수 설정 시 허브 `DtaDa0555D801Da508DbDtt5t1bat1ta` 엔드포인트 호출.
- `GET …/{projectKey}?startDate=201801&endDate={YYYYMM}` 단일 요청. 실패 시 연 단위 재시도.
- 응답을 `data/raw/d9_visitors_purpose.csv`에 저장 → 다음 실행부터 키 없이도 동일 재현.
- 산출물: `visitors_monthly.parquet` (년월, 방문목적, 방문자수).

## 8. 데이터 한계 요약 (리포트 `limitations` 필드로 노출)

1. 지역별 카드 데이터(D1·D2)는 2021-05까지 제공 → 기준 기간을 2018-2019로 설정.
2. 카드 데이터는 특정 카드사 표본일 수 있어 절대 금액보다 **비중·배율·순위** 해석 권장.
3. D1 법정동(73) → D4 행정동(43) 집계로 1:N 매핑, 법정동→행정동 최빈값 변환.
4. 업종 매핑은 16개다. 매핑 밖은 `clarify(category)`로 되묻는다. D1·D5가 없는 5개(PC방·미용실·네일샵·헬스장·노래방)는 되묻지 않고 점수만 보류한다.
5. D5 한계: **인허가 기준**이라 실제 영업 상태와 차이 가능. 좌표는 허브에서 제공 안 됨 → 주소 기반 매핑.
6. D6 한계: 값 5 이하는 비공개(`*`), 연도별 제공 항목 상이.
7. D9 한계: 제주 전체 단위, 지역 구분 없음.

## 9. 데이터 레지스트리 (`data/processed/registry.json`)

- 각 데이터의 `id, name, source, period_start, period_end, as_of, refresh, api` 메타.
- 제출된 `registry.json`은 **D1~D6**이다. D9는 `build_visitors()`가 성공할 때만 붙는다.
- `/api/meta` 응답의 `registry` 필드로 노출되며, 신호별 `as_of` 배지의 시점 기준이다.
