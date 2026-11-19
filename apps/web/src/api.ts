import type { AgentEvent, DiagnoseForm, MapLayer, MapLayerResponse, Meta } from './types'
import { META, buildEvents, buildMapLayer } from './mocks/data'

// 기본은 실 API. `VITE_USE_MOCK=true`일 때만 목 데이터로 UI 단독 확인.
const USE_MOCK = (import.meta.env.VITE_USE_MOCK ?? 'false') === 'true'

// 진행 중인 run의 form을 메모리에 보관 (목 전용)
const mockRuns = new Map<string, DiagnoseForm>()

export async function getMeta(): Promise<Meta> {
  if (USE_MOCK) return META
  const r = await fetch('/api/meta')
  if (!r.ok) throw new Error(`meta ${r.status}`)
  return r.json()
}

// 지도 레이어 캐시 (TTL 60s) + 동시 요청 dedupe + 429 자동 재시도
interface MapCacheEntry { ts: number; data: MapLayerResponse }
const _mapCache = new Map<string, MapCacheEntry>()
const _mapInflight = new Map<string, Promise<MapLayerResponse>>()
const MAP_TTL_MS = 60_000

async function _fetchMapOnce(layer: MapLayer, category: string, month?: number): Promise<MapLayerResponse> {
  const qs = new URLSearchParams()
  if (category) qs.set('category', category)
  if (month) qs.set('month', String(month))
  const url = `/api/map/${layer}?${qs}`
  for (let attempt = 0; attempt < 3; attempt++) {
    const r = await fetch(url)
    if (r.ok) return r.json()
    // 429 / 503 는 지수 백오프 재시도
    if (r.status === 429 || r.status === 503) {
      await new Promise((res) => setTimeout(res, 250 * (attempt + 1) + Math.random() * 100))
      continue
    }
    throw new Error(`map ${r.status}`)
  }
  throw new Error('map 429 (재시도 실패)')
}

export async function getMapLayer(layer: MapLayer, category: string, month?: number): Promise<MapLayerResponse> {
  if (USE_MOCK) return buildMapLayer(layer, category, month)
  const key = `${layer}|${category}|${month ?? 0}`
  const now = Date.now()
  const hit = _mapCache.get(key)
  if (hit && now - hit.ts < MAP_TTL_MS) return hit.data
  const pending = _mapInflight.get(key)
  if (pending) return pending
  const p = _fetchMapOnce(layer, category, month)
    .then((data) => { _mapCache.set(key, { ts: Date.now(), data }); return data })
    .finally(() => { _mapInflight.delete(key) })
  _mapInflight.set(key, p)
  return p
}

export async function startDiagnose(form: DiagnoseForm): Promise<string> {
  if (USE_MOCK) {
    const id = `mock-${Date.now()}`
    mockRuns.set(id, form)
    return id
  }
  const r = await fetch('/api/diagnose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form),
  })
  if (!r.ok) throw new Error(`diagnose ${r.status}`)
  return (await r.json()).run_id
}

export function streamEvents(runId: string, onEvent: (e: AgentEvent) => void): () => void {
  if (USE_MOCK) {
    const form = mockRuns.get(runId) ?? { category: '카페', dong: '애월읍', customer: 'any', ages: [], risk: 'balanced' }
    const events = buildEvents(form)
    let cancelled = false
    let i = 0
    const tick = () => {
      if (cancelled || i >= events.length) return
      onEvent(events[i++])
      setTimeout(tick, 220)
    }
    setTimeout(tick, 200)
    return () => { cancelled = true }
  }
  const es = new EventSource(`/api/diagnose/${runId}/events`)
  const handle = (msg: MessageEvent) => {
    const ev = JSON.parse(msg.data) as AgentEvent
    onEvent(ev)
    if (ev.type === 'report' || ev.type === 'error' || ev.type === 'clarify') es.close()
  }
  for (const t of ['step', 'tool', 'clarify', 'report', 'error']) es.addEventListener(t, handle as EventListener)
  return () => es.close()
}

export interface ChatResult { run_id: string; parsed: { dong: string | null; category: string | null } }

export async function askChat(runId: string | null, question: string): Promise<ChatResult> {
  if (USE_MOCK) {
    // 목 모드: 질문에서 동 이름을 찾아보고 직전 form 유지
    const base = (runId && mockRuns.get(runId)) || { category: '카페', dong: null, customer: 'any', ages: [], risk: 'balanced' } as DiagnoseForm
    const { DONGS } = await import('./mocks/dongs')
    const hitDong = DONGS.find((d) => question.includes(d.name))?.name ?? null
    const { CATEGORIES } = await import('./mocks/data')
    const hitCat = CATEGORIES.find((c) => question.includes(c)) ?? null
    const next: DiagnoseForm = { ...base, dong: hitDong ?? base.dong, category: hitCat ?? base.category, question }
    const id = `mock-${Date.now()}`
    mockRuns.set(id, next)
    return { run_id: id, parsed: { dong: hitDong, category: hitCat } }
  }
  const r = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ run_id: runId, question }),
  })
  if (!r.ok) throw new Error(`chat ${r.status}`)
  return r.json()
}

export interface StoreItem {
  name: string
  address: string
  lon: number
  lat: number
  category?: string
  distance_m?: number
}
export interface StoresResponse { dong: string; category: string | null; total: number; items: StoreItem[] }

export async function getStores(dong: string, category?: string, limit = 20): Promise<StoresResponse> {
  if (USE_MOCK) {
    // 목: 백엔드 미구현 상태 모방 (빈 응답)
    return { dong, category: category ?? null, total: 0, items: [] }
  }
  const qs = new URLSearchParams({ dong })
  if (category) qs.set('category', category)
  qs.set('limit', String(limit))
  const r = await fetch(`/api/stores?${qs}`)
  if (!r.ok) throw new Error(`stores ${r.status}`)
  return r.json()
}

export async function getHealth(): Promise<{ ok: boolean; data_ready: boolean }> {
  if (USE_MOCK) return { ok: true, data_ready: true }
  const r = await fetch('/api/health')
  if (!r.ok) throw new Error(`health ${r.status}`)
  return r.json()
}
