# 섬자리 API 계약

> 백엔드·프론트 담당이 공동으로 보는 계약서. 변경은 이 문서 커밋으로 승인.

## HTTP

| Method | Path | 비고 |
|---|---|---|
| GET | `/livez` | 프로세스 생존 |
| GET | `/readyz` | 데이터+세션DB 준비 |
| GET | `/api/health` | 레거시 호환 |
| GET | `/api/meta` | 업종·행정동·기간·**registry(제출본은 D1~D6)** |
| POST | `/api/diagnose` | 입력 폼 → `{ run_id }` |
| GET | `/api/diagnose/{run_id}/events` | **SSE 스트림** |
| POST | `/api/chat` | 후속 질문 → 새 `run_id` |
| GET | `/api/map/{layer}` | layer ∈ {demand, tourism, supply, footfall, **survival**} |
| GET | `/api/metrics` | 최근 세션 카운트·provider/model |

## SSE 이벤트

```ts
type AgentEvent =
  | { type: 'step'; index: number; name: string; status: 'running' | 'done' }
  | { type: 'tool'; name: string; args: unknown; summary: string }    // summary는 사람 읽는 한 줄
  | { type: 'clarify'; question: string;                                // NEW
      field: 'category' | 'dong';
      options: { label: string; value: string }[] }
  | { type: 'report'; report: Report; mode: ReportMode }
  | { type: 'error'; message: string }
```

- `clarify` 이벤트가 발행되면 **그 뒤로 report 는 오지 않는다**. 프론트는 해당 field에 대한 선택 UI를 띄우고 `/api/chat` 또는 `/api/diagnose`로 다시 보낸다.
- `tool.summary`는 "애월읍 카페 3년 생존율 66.3% (n=261), 업종 평균 대비 -4.8%p"처럼 사람이 읽는 한 줄.

## Report 스키마 (요약)

```ts
interface Signal {
  name: '관광 의존도' | '계절 변동성' | '수요 규모' | '유동 수요' | '경쟁 밀도' | '생존 리스크' | '최근 개폐업'
  value: string                                     // 예: '74.5%', '업종 내 6위 / 41'
  level: 'green' | 'yellow' | 'red' | 'unavailable' // NEW: unavailable
  reason: string
  as_of?: string                                    // NEW: '2018~2019', '2025-09-02' 등
}

type ReportMode = 'full' | 'partial' | 'llm' | 'fallback' | 'llm_fallback'

interface Report {
  summary: string
  target: { dong: string | null; category: string | null }
  signals: Signal[]
  score: number | null                              // 가용 신호 < 3 이거나 수요 계열 없으면 null
  alternatives?: { dong: string; score: number; why: string }[]
  trend: string | null
  evidence: { source: 'D1'|'D2'|'D3'|'D4'|'D5'|'D6'|'D9'|'D10'; period: string; detail: string }[]
  limitations: string[]
  map: { layer: 'demand'|'tourism'|'supply'|'footfall'|'survival'; highlight: string[] }
  mode?: ReportMode
}
```

### Signal 처리 규칙
- `level === 'unavailable'` 이면 UI는 신호 카드를 회색으로, `value='N/A'`로 표시.
- `report.mode === 'partial'` 이면 상단에 "제한 분석" 배지. `summary` 첫 문장에 이유 포함 ("카드 매출 데이터가 없어 수요는 판단하지 못했어요").
- SSE 이벤트의 `mode`와 `report.mode`는 다를 수 있다. Gemini가 실패하면 이벤트 `mode`는 `llm_fallback`이고 `report.mode`는 `full` 또는 `partial`이다. 각주는 `report.mode === 'llm_fallback'`일 때만 그린다.
- 각 signal의 `as_of` 는 신호 옆 "시점 배지"로 노출.

## /api/meta 응답 (추가 필드)

```ts
interface Meta {
  categories: string[]
  dongs: DongMeta[]
  period: { base: string; recent?: string }
  registry: {                          // NEW
    id: 'D1'|'D2'|'D3'|'D4'|'D5'|'D6'|'D9'|'D10'
    name: string
    source: string
    period_start: string
    period_end: string
    as_of: string
    refresh: 'daily'|'monthly'|'quarterly'|'yearly'|'none'
    api: boolean
  }[]
}
```

## 지도 레이어

| layer | value (높이) | tourism (색상) | 비고 |
|---|---|---|---|
| demand | 업종 월평균 매출 | 관광 의존도 | 기본 |
| tourism | 관광 의존도 | 관광 의존도 | |
| supply | 점포 수 | 관광 의존도 | |
| footfall | 방문인구 평균 | 관광 의존도 | |
| **survival** | 점포 수 | **(1 − 3년 생존율)**: 0 파랑, 1 주황(RGB 255,120,50) | NEW |

## 변경 이력
- 2026-11-20: `clarify` 이벤트 추가, `signals[].level` 에 `'unavailable'` 추가, `report.mode` 노출, `/api/meta.registry` 추가, map layer `survival` 추가.
- 2026-11-19: SSE 포맷 최초 정의.
