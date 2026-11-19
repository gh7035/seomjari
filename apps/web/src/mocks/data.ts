import type { AgentEvent, Meta, Report, MapLayer, MapLayerResponse, MapPoint } from '../types'
import { DONGS } from './dongs'

export const CATEGORIES = [
  '카페', '한식당', '양식당', '일식당', '중식당',
  '술집', '베이커리', '편의점', '기념품점', '소형숙박', '패스트푸드', '피자/햄버거',
]

export const META: Meta = {
  categories: CATEGORIES,
  dongs: DONGS,
  period: { base: '2018-01~2019-12', recent: '2021-01~2021-05' },
}

// 핵심 기준값: 애월읍 카페 관광 비중 74.9%, 성수/비수 1.75배(🔴)
//             이도2동 카페 관광 30.9%, 성수/비수 1.25배(🟢)
// 그 외 41개 행정동은 두 극단 사이의 그럴듯한 분포로 결정론적으로 생성한다.
function hash(s: string): number {
  let h = 2166136261
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 16777619) }
  return (h >>> 0) / 0xffffffff
}

interface DongStat {
  dong: string
  value: number       // 월평균 매출 (임의 단위, 비교용)
  tourism: number     // 관광 의존도 0~1
  seasonality: number // 성수/비수 배율
  stores: number      // 점포수
  monthly: number[]   // 12개월 패턴
}

function monthlyFrom(base: number, tourism: number, seasonality: number, salt: number): number[] {
  // 관광 의존도가 높을수록 7~9월에 피크. 월평균이 base가 되도록 스케일.
  const raw: number[] = []
  for (let m = 1; m <= 12; m++) {
    const summer = Math.exp(-Math.pow((m - 8) / 2.2, 2)) // 8월 피크
    const winter = Math.exp(-Math.pow(((m + 5) % 12 - 5.5) / 3, 2)) * 0.6
    const amp = seasonality - 1
    const season = 1 + amp * (0.75 * summer + 0.25 * winter - 0.35)
    const noise = 0.92 + 0.16 * hash(`n${salt}${m}`)
    raw.push(Math.max(0.2, season * tourism + 0.9 * (1 - tourism)) * noise)
  }
  const mean = raw.reduce((a, b) => a + b, 0) / 12
  return raw.map((v) => Math.round((v / mean) * base))
}

export function dongStats(category: string): DongStat[] {
  return DONGS.map((d) => {
    let tourism: number, seasonality: number, value: number, stores: number
    if (d.name === '애월읍' && category === '카페') {
      tourism = 0.749; seasonality = 1.75; value = 41_800_000; stores = 52
    } else if (d.name === '이도2동' && category === '카페') {
      tourism = 0.309; seasonality = 1.25; value = 36_400_000; stores = 44
    } else {
      // 결정론적 랜덤: 동명 + 업종.
      const r1 = hash(`${d.name}|${category}|tour`)
      const r2 = hash(`${d.name}|${category}|seas`)
      const r3 = hash(`${d.name}|${category}|val`)
      const r4 = hash(`${d.name}|${category}|sup`)
      const touristy = /읍|면|성산|중문|한림|애월|구좌|우도|추자|표선|안덕/.test(d.name) ? 0.35 : 0.0
      tourism = Math.min(0.85, Math.max(0.12, 0.28 + touristy + r1 * 0.35))
      seasonality = 1.08 + tourism * 0.9 + (r2 - 0.5) * 0.25
      value = Math.round(8_000_000 + r3 * 55_000_000)
      stores = Math.round(8 + r4 * 70)
    }
    const salt = hash(`${d.name}${category}`) * 1000
    return {
      dong: d.name, value, tourism, seasonality, stores,
      monthly: monthlyFrom(value, tourism, seasonality, salt),
    }
  })
}

function pct(arr: number[], v: number): number {
  const sorted = [...arr].sort((a, b) => a - b)
  const idx = sorted.findIndex((x) => x >= v)
  return idx < 0 ? 1 : idx / (sorted.length - 1)
}

export function buildReport(form: { category: string | null; dong: string | null; risk: string }): Report {
  const category = form.category ?? '카페'
  const dong = form.dong ?? '애월읍'
  const stats = dongStats(category)
  const self = stats.find((s) => s.dong === dong) ?? stats[0]

  const tourismPct = pct(stats.map((s) => s.tourism), self.tourism)
  const seasonalityPct = pct(stats.map((s) => s.seasonality), self.seasonality)
  const competitionDensity = self.stores / (self.value / 100_000_000)
  const compArr = stats.map((s) => s.stores / (s.value / 100_000_000))
  const compPct = pct(compArr, competitionDensity)
  const demandPct = pct(stats.map((s) => s.value), self.value)
  const demandRank = stats.filter((s) => s.value > self.value).length + 1

  const level = (p: number): 'red' | 'yellow' | 'green' =>
    p >= 2 / 3 ? 'red' : p >= 1 / 3 ? 'yellow' : 'green'
  const demandLevel: 'red' | 'yellow' | 'green' =
    demandPct >= 2 / 3 ? 'green' : demandPct >= 1 / 3 ? 'yellow' : 'red'

  // 가중치: 리스크 성향 반영
  const w = form.risk === 'safe'
    ? { t: 0.4, s: 0.35, c: 0.2, d: 0.25 }
    : form.risk === 'aggressive'
    ? { t: 0.2, s: 0.2, c: 0.3, d: 0.4 }
    : { t: 0.3, s: 0.3, c: 0.25, d: 0.3 }
  const scoreRaw = 100 - (w.t * tourismPct + w.s * seasonalityPct + w.c * compPct) * 100 + w.d * demandPct * 20
  const score = Math.max(0, Math.min(100, Math.round(scoreRaw)))

  // 대안: 자신보다 점수 높은 동 상위 3개 추정 (관광의존도 낮고 수요 적당한 곳)
  const altCand = stats
    .filter((s) => s.dong !== dong)
    .map((s) => {
      const tp = pct(stats.map((x) => x.tourism), s.tourism)
      const sp = pct(stats.map((x) => x.seasonality), s.seasonality)
      const cd = s.stores / (s.value / 100_000_000)
      const cp = pct(compArr, cd)
      const dp = pct(stats.map((x) => x.value), s.value)
      const sc = 100 - (w.t * tp + w.s * sp + w.c * cp) * 100 + w.d * dp * 20
      return { dong: s.dong, score: Math.round(Math.max(0, Math.min(100, sc))), tourism: s.tourism }
    })
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)

  const redCount = [level(tourismPct), level(seasonalityPct), level(compPct)].filter((l) => l === 'red').length

  const report: Report = {
    summary: redCount >= 2
      ? `${dong} ${category}은 관광 의존도와 계절 변동성이 커 비수기 리스크가 큽니다. 도민형 지역을 함께 보세요.`
      : `${dong} ${category}은 데이터상 균형 잡힌 조건입니다.`,
    target: { dong, category },
    signals: [
      {
        name: '관광 의존도',
        value: `${(self.tourism * 100).toFixed(1)}%`,
        level: level(tourismPct),
        reason: `업종 내 상위 ${Math.round((1 - tourismPct) * 100)}% 위치. 관광객 매출 비중이 ${(self.tourism * 100).toFixed(1)}%.`,
      },
      {
        name: '계절 변동성',
        value: `${self.seasonality.toFixed(2)}배`,
        level: level(seasonalityPct),
        reason: `성수월/비수월 매출 배율. 1에 가까울수록 평탄.`,
      },
      {
        name: '경쟁 밀도',
        value: `${competitionDensity.toFixed(1)} 점포/억원`,
        level: level(compPct),
        reason: `점포수 ${self.stores}개 / 월평균 매출 ${(self.value / 100_000_000).toFixed(2)}억원 기준.`,
      },
      {
        name: '수요 규모',
        value: `업종 내 ${demandRank}위`,
        level: demandLevel,
        reason: `43개 행정동 중 ${demandRank}위. 월평균 ${(self.value / 10_000).toLocaleString()}만원.`,
      },
    ],
    score,
    alternatives: altCand.map((a) => ({
      dong: a.dong,
      score: a.score,
      why: a.tourism < self.tourism
        ? `관광 의존도 ${(a.tourism * 100).toFixed(1)}% 로 더 낮아 비수기 리스크가 작습니다.`
        : `종합 점수가 높아 균형이 잡혔습니다.`,
    })),
    trend: `${category} 업종 전체 소비는 2023년 정점 이후 완만히 감소 중입니다.`,
    evidence: [
      { source: 'D1', period: '2018-01~2019-12', detail: `${dong}·${category} 월평균 매출과 관광객/도민 구분 사용.` },
      { source: 'D4', period: '2025-09', detail: `${dong} 내 ${category} 점포 ${self.stores}개 기준 경쟁 밀도 산출.` },
      { source: 'D3', period: '2018-01~2025-06', detail: `${category} 업종 전체 트렌드 보조 지표.` },
    ],
    limitations: [
      '카드사 표본 데이터이므로 절대 금액이 아닌 비중·배율·순위 중심으로 해석해야 합니다.',
      '2021년 6월 이후 지역·업종 교차 데이터가 없어 코로나 이전(2018~2019) 기준을 사용했습니다.',
      '매장수는 D4(2025-09) 기준으로 과거 시점과 어긋날 수 있습니다.',
    ],
    map: { layer: 'tourism', highlight: [dong, ...altCand.map((a) => a.dong).slice(0, 1)] },
    monthly_pattern: {
      labels: ['1월','2월','3월','4월','5월','6월','7월','8월','9월','10월','11월','12월'],
      values: self.monthly,
      tourism_values: self.monthly.map((v) => Math.round(v * self.tourism)),
    },
  }
  return report
}

export function buildMapLayer(layer: MapLayer, category: string, month?: number): MapLayerResponse {
  const stats = dongStats(category)
  const points: MapPoint[] = stats.map((s) => {
    const value = (() => {
      const m = typeof month === 'number' && month >= 1 && month <= 12 ? s.monthly[month - 1] : s.value
      if (layer === 'demand') return m
      if (layer === 'tourism') return Math.round(m * s.tourism)
      if (layer === 'supply') return s.stores
      // footfall: 임의 추정 (방문인구 월평균)
      return Math.round((s.value / 100_000) * (0.5 + s.tourism))
    })()
    return {
      dong: s.dong,
      lon: DONGS.find((d) => d.name === s.dong)!.lon,
      lat: DONGS.find((d) => d.name === s.dong)!.lat,
      value,
      tourism: s.tourism,
      monthly: s.monthly,
      stores: s.stores,
    }
  })
  return { layer, points }
}

// SSE 이벤트 시퀀스 (실제 Agent 흐름 모사)
export function buildEvents(form: { category: string | null; dong: string | null; risk: string }): AgentEvent[] {
  const category = form.category ?? '카페'
  const dong = form.dong ?? '애월읍'
  const report = buildReport(form)
  return [
    { type: 'step', index: 0, name: '의도 파악', status: 'running' },
    { type: 'tool', name: 'resolve_category', args: { text: category }, summary: `업종 "${category}" 매칭 완료` },
    { type: 'tool', name: 'resolve_place', args: { text: dong }, summary: `지역 "${dong}" 매칭 완료 (행정동)` },
    { type: 'step', index: 0, name: '의도 파악', status: 'done' },
    { type: 'step', index: 1, name: '계획', status: 'running' },
    { type: 'tool', name: 'plan', args: {}, summary: 'get_demand → get_supply → score_risk → compare_places' },
    { type: 'step', index: 1, name: '계획', status: 'done' },
    { type: 'step', index: 2, name: '수요 조회', status: 'running' },
    { type: 'tool', name: 'get_demand', args: { dong, category }, summary: `월평균 ${(report.signals[3].value)} · 관광 ${(report.signals[0].value)}` },
    { type: 'step', index: 2, name: '수요 조회', status: 'done' },
    { type: 'step', index: 3, name: '공급 조회', status: 'running' },
    { type: 'tool', name: 'get_supply', args: { dong, category }, summary: report.signals[2].value },
    { type: 'step', index: 3, name: '공급 조회', status: 'done' },
    { type: 'step', index: 4, name: '리스크 점수', status: 'running' },
    { type: 'tool', name: 'score_risk', args: { dong, category, risk: form.risk }, summary: `종합 점수 ${report.score}` },
    { type: 'step', index: 4, name: '리스크 점수', status: 'done' },
    { type: 'step', index: 5, name: '대안 탐색', status: 'running' },
    { type: 'tool', name: 'compare_places', args: { category }, summary: `대안 Top ${report.alternatives?.length ?? 0} 선정` },
    { type: 'step', index: 5, name: '대안 탐색', status: 'done' },
    { type: 'step', index: 6, name: '리포트 생성', status: 'running' },
    { type: 'step', index: 6, name: '리포트 생성', status: 'done' },
    { type: 'report', report, mode: 'fallback' },
  ]
}
