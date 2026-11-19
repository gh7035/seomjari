# FE_CHANGES

프론트 적용 변경 로그. 각 항목은 `docs/FE_REQUESTS.md` 와 백엔드 계약 변동에 맞춰 반영한 내용이다.

## 2026-11-19 — SSE/리포트 스키마 확장

### 1) `clarify` 이벤트 처리
- `types.ts`: `AgentEvent` 유니온에 `{ type: 'clarify', question, field, options }` 추가.
  - `field`: `keyof DiagnoseForm` (예: `category`, `dong`, `customer`, `risk`, `ages`).
  - `options`: `{ label, value }[]`.
- `api.ts`: SSE 리스너에 `'clarify'` 이벤트 등록. clarify 수신 시 EventSource 종료.
- `components/ChatPane.tsx`: 해당 turn 에 report 가 없고 clarify 가 있으면 `ReportCard` 대신 `ClarifyCard` 렌더.
  - 칩 클릭 → `assignField(form, field, value)` 로 직전 폼과 병합 → `startDiagnose` 재호출 → 새 run_id 로 스트림 체인.
  - 사용자 메시지 라벨은 "업종: 카페" 식으로 표시.

### 2) 부분 진단 표시
- `types.ts`: `Report.mode?: 'llm' | 'fallback' | 'partial'` 추가. `Level` 에 `'unavailable'` 추가.
- `components/ReportCard.tsx`:
  - `mode === 'partial'` 시 제목 옆 **부분 진단** 배지 + summary 첫 문장을 강조 문단으로 분리.
  - `level === 'unavailable'` 신호: 회색 테마(`.signal-unavailable`), value 자리에 **"데이터 없음"**, reason 유지.
  - DOT/라벨 맵에 `unavailable` 추가 (`⚪`, "데이터 없음").

### 3) 고정 문구 제거 / 점수 숨김 규칙
- `components/ReportCard.tsx`:
  - 종합 점수 설명을 **동적**으로: `signals.filter(s => s.level !== 'unavailable').length` 가 있으면 `"{N}개 신호를 가중 평균한 종합 점수…"`, 0 이면 "신호 데이터가 없어 점수 산출에 한계가 있습니다." 로 교체.
  - `score` 가 `number` 가 아니거나 `signals.length === 0` 이면 **점수 섹션 자체를 렌더링하지 않음** (0/100 표시 금지).
  - `Report.score` 를 `number | null | undefined` 로 완화 (`types.ts`).
- `signals.length === 0` 이면 신호 그리드 자체도 숨김. `evidence/limitations` 도 비어있으면 해당 섹션 제목+리스트 숨김.

### 4) 도구 로그 정제
- `components/ChatPane.tsx` `TurnBlock`:
  - `tool` 이벤트 집계 시 `name.trim()` 또는 `summary.trim()` 이 비면 **해당 항목 제외**.
  - 포맷을 `"도구명 · 요약"` 으로 통일 (` — ` → ` · `).

## 영향 없음
- 기존 `fallback` / `llm` 모드 리포트는 그대로 동작 (시그널이 4개 유효하면 이전과 동일 렌더).
- 지도·Context·Month·Entry 컴포넌트는 변경 없음.
- 타입/빌드 통과(`tsc -b` + `vite build`).

## 2026-11-20 — D5/D6/D9 반영 (당시 신호 6개 + 시점 배지 + 신규 레이어)

이 절의 신호 enum 6개는 같은 날 저녁 아래 "유동 수요" 절로 7개가 되었다. 생존 레이어 색은 빨강이 아니라 `tourismColor`의 주황(t=1일 때 RGB 255,120,50)이다. `llm_fallback` 각주는 `report.mode`가 그 값일 때만 나온다. 현재 루프는 리포트 `mode`를 `full`/`partial`로 두고, SSE 이벤트 `mode`만 `llm_fallback`으로 보낸다.

### 1) 신호 2개 추가
- `signals[].name` enum: `'관광 의존도' | '계절 변동성' | '경쟁 밀도' | '수요 규모' | '생존 리스크' | '최근 개폐업'`
- 카드 그리드 기본 2×3 레이아웃(6 신호) 가정. `unavailable` 는 회색 음영.

### 2) `signals[].as_of` 시점 배지 (필수 노출)
- 예: `"2018~2019"` (카드 매출), `"2025-09-02"` (음식점 D5), `"2025-09"` (상가 D4).
- 신호 카드 우상단 또는 신호명 옆에 작은 배지(`<span class="as-of">`). 데이터 공백 투명성.

### 3) `evidence[].source` enum 확장
- `'D1' | 'D2' | 'D3' | 'D4' | 'D5' | 'D6' | 'D9' | 'D10'`

### 4) `/api/meta.registry` 노출
```ts
interface RegistryEntry { id: string; name: string; source: string;
  period_start: string; period_end: string; as_of: string;
  refresh: 'daily'|'monthly'|'quarterly'|'yearly'|'none'; api: boolean }
```
- 폼 상단에 "데이터 시점" 축약 표시(이미 `period` 사용), 상세 테이블은 선택.

### 5) 지도 신규 레이어 `survival`
- `/api/map/survival?category=카페` 호출.
- `value` = 점포 수 (높이), **`tourism` 필드는 `(1 − 3년 생존율)`**: 0 파랑(안전) → 1 빨강(위험).
- 레이어 토글에 "생존" 버튼 추가, 툴팁 "생존 리스크" 라벨.

### 6) `report.mode` enum 확장
- 추가: `'partial'` (부분 진단), `'llm_fallback'`.
- `partial`: 상단 **"제한 분석"** 배지(황색) + summary 첫 문장 ("카드 매출 데이터가 없어 수요는…") 강조.
- `llm_fallback`: 리포트 하단 각주 "LLM 오류로 규칙 기반 재생성".

### 7) 지원 업종 확대 (11 → 16)
- 신규: `PC방`, `미용실`, `네일샵`, `헬스장`, `노래방` (D4-only → partial 모드).
- 기존 하드코딩 리스트 제거하고 `/api/meta.categories` 사용.

### 8) 의도 파악 강화 (프론트 쪽 기대 동작)
- 입력 폼이 전부 비어 있어도 자연어 질문(`question`)만으로 `/api/diagnose` 호출 가능.
- 백엔드가 `parse_intent` → clarify or place_recommend 로 분기.

## 2026-11-20 (저녁) — FE_REQUESTS 3·4·6 백엔드 반영

프론트가 `docs/FE_REQUESTS.md`에 올린 6개 요청 중 백엔드가 구현해야 할 3개 반영.

### 3) `/api/map/{layer}` 포인트별 `monthly` 배열
- `?category=` 지정 + `layer ∈ {demand, tourism, supply}` 일 때 각 포인트에 `monthly: number[12]` 추가.
- 카테고리 미지정 또는 `survival`/`footfall` 레이어는 `monthly` 생략.
- `month=N` (1~12) 쿼리는 그대로 유효 (해당 월만 slice해서 `value` 계산).

### 4) `report.monthly_pattern`
- target이 (dong, category)로 결정된 full 진단 경우에 자동 포함:
  ```json
  "monthly_pattern": {
    "labels": ["1월", ..., "12월"],
    "values": [57971730, ..., 50306575]
  }
  ```
- fallback·llm 모드 모두 서버에서 주입 (LLM이 안 채워도 됨).
- 없으면 프론트는 `/api/map/{layer}?category=...`의 `monthly`로 대체.

### 6) `GET /api/stores` 신규 엔드포인트
- 지도 기둥 클릭 시 상세 패널용.
- 쿼리: `dong` (필수), `category` (선택), `limit` (1~200, 기본 20), `near="lon,lat"` (선택).
- 응답:
  ```json
  {
    "dong": "애월읍", "category": "카페",
    "total": 225, "limit": 20,
    "items": [
      {"name": "...", "address": "...",
       "lon": 126.33, "lat": 33.46,
       "category": "커피 전문점",
       "distance_m": 410}
    ],
    "source": "D4", "as_of": "2025-09"
  }
  ```
- `near` 있을 때만 `distance_m` 포함, items를 거리 오름차순 정렬.
- 알 수 없는 `dong`은 `total: 0, items: []` (오류 아님).
- 입력 검증: `dong`/`category` 최대 50자, `limit` 1~200, `near` 는 `"lon,lat"` 형식.

## 2026-11-20 (저녁) — 신뢰도·유동수요·랜드마크·form_applied·동적 한계

### 1) `score`가 `number | null` + `confidence` 필드
- `signals.py` 레지스트리 기반으로 재구성. 가용 신호 수 < 3 이거나 수요 계열(수요 규모·유동 수요) 신호가 하나도 없으면:
  - `report.score = null`
  - `report.confidence = "low"`
  - `report.confidence_reason`(옵션)
- 프론트: `score === null` 이면 점수 자리에 **"판단 보류 · 참고용(신호 n/7)"** 표시. `report.active_signals`/`total_signals` 노출.
- `alternatives[].score` 도 동일 규칙으로 `null` 가능. `confidence`, `active_signals`, `total_signals` 포함.

### 2) 신호 7개로 확대 — "유동 수요" 추가
- `signals[].name` enum: `"관광 의존도" | "계절 변동성" | "경쟁 밀도" | "수요 규모" | "유동 수요" | "생존 리스크" | "최근 개폐업"`
- 유동 수요는 **D2 방문인구 기반**, **업종 무관**. 카드 매출이 없는 업종(PC방·미용실 등)의 수요 대리 지표.
- 폼의 `ages`가 있고 D2가 연령 컬럼을 지원하면 해당 연령으로 필터(현재 D2에 연령 컬럼 없음 → 전체 사용).

### 3) 지역 해석에 랜드마크 LLM 보조
- 백엔드 `resolve_place`가 fuzzy 매칭 실패 시 자동으로 `resolve_place_via_landmark`를 호출(LLM이 43개 행정동 목록 안에서만 선택). 실패 시 clarify.
- 프론트 UI 변경 없음(스트림에 tool 이벤트로 노출됨). 다만 `tool.name === "resolve_place_via_landmark"` 항목이 Progress 리스트에 등장할 수 있음.

### 4) `report.form_applied` 로 왼쪽 폼 자동 반영
- 백엔드는 `parse_intent`에서 추출한 `constraints`(ages·customer)를 폼과 병합해 실제로 사용한 값을 `report.form_applied` 로 돌려줌.
- 프론트: 리포트 수신 시 폼 상태를 `form_applied` 로 갱신. 사용자가 "20대 도민이 좋아할 애월 카페" 라고 쓰면 폼에 `category=카페, dong=애월읍, customer=local, ages=["20대"]`가 자동 반영.
- `report.constraints`에 원본 추출치도 참고용으로 포함.

### 5) `report.limitations` 는 매번 동적 생성
- 더 이상 고정 문구 두 줄이 아님. 이번 실행에서 실제 사용한 데이터 ID(`D1`, `D2`, `D4`, `D5`, `D9`)에 대한 설명 + unavailable 신호의 사유를 합성.
- 프론트: 단순히 `limitations` 배열을 그대로 bullet 렌더 (파싱 로직 불필요).

### 6) 타입 요약

```ts
interface Report {
  summary: string
  target: { dong: string | null; category: string | null }
  signals: Signal[]
  score: number | null                      // ← CHANGE
  confidence?: 'normal' | 'low'             // ← NEW
  confidence_reason?: string                // ← NEW
  active_signals?: number                   // ← NEW
  total_signals?: number                    // ← NEW
  alternatives?: Alternative[]              // score: number|null
  trend?: string | null
  evidence: Evidence[]
  limitations: string[]
  map: { layer: MapLayer; highlight: string[] }
  mode?: ReportMode
  form_applied?: {                          // ← NEW
    category: string | null; dong: string | null
    customer: string; ages: string[]; risk: string
  }
  constraints?: { ages?: string[]; customer?: string }   // ← NEW
}

type SignalName =
  | '관광 의존도' | '계절 변동성' | '경쟁 밀도' | '수요 규모'
  | '유동 수요'                                // ← NEW
  | '생존 리스크' | '최근 개폐업'
```
