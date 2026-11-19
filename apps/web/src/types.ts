// packages/schema/report.schema.json 과 동기화 유지

export type Level = 'green' | 'yellow' | 'red' | 'unavailable'
export type MapLayer = 'demand' | 'tourism' | 'supply' | 'footfall' | 'survival'
export type ReportMode = 'llm' | 'fallback' | 'partial' | 'llm_fallback'
export type EvidenceSource = 'D1' | 'D2' | 'D3' | 'D4' | 'D5' | 'D6' | 'D9' | 'D10'

export interface Signal {
  name: string
  value: string
  level: Level
  reason: string
  as_of?: string
  percentile?: number
}
export interface Alternative { dong: string; score: number; why: string }
export interface Evidence { source: EvidenceSource; period: string; detail: string }

export interface MonthlyPattern { labels: string[]; values: number[]; tourism_values?: number[] }

export interface Report {
  summary: string
  target: { dong: string | null; category: string | null }
  signals: Signal[]
  score?: number | null
  alternatives?: Alternative[]
  trend?: string | null
  evidence: Evidence[]
  limitations: string[]
  map: { layer: MapLayer; highlight: string[] }
  monthly_pattern?: MonthlyPattern
  mode?: ReportMode
}

export interface DiagnoseForm {
  category: string | null
  dong: string | null
  customer: 'tourist' | 'local' | 'any'
  ages: string[]
  risk: 'safe' | 'balanced' | 'aggressive'
  question?: string
}

export interface ClarifyOption { label: string; value: string }

export type AgentEvent =
  | { type: 'step'; index: number; name: string; status: 'running' | 'done' }
  | { type: 'tool'; name: string; args: unknown; summary: string }
  | { type: 'report'; report: Report; mode?: ReportMode }
  | { type: 'clarify'; question: string; field: keyof DiagnoseForm; options: ClarifyOption[] }
  | { type: 'error'; message: string }

export interface DongMeta { name: string; lon: number; lat: number; city?: string; type?: '도심' | '읍면' }

export interface RegistryEntry {
  id: string
  name: string
  source: string
  period_start: string
  period_end: string
  as_of: string
  refresh: 'daily' | 'monthly' | 'quarterly' | 'yearly' | 'none'
  api: boolean
}

export interface Meta {
  categories: string[]
  dongs: DongMeta[]
  period: { base: string; recent?: string }
  registry?: RegistryEntry[]
}

export interface MapPoint {
  dong: string; lon: number; lat: number; value: number; tourism: number
  monthly?: number[]; stores?: number
}
export interface MapLayerResponse { layer: MapLayer; category?: string | null; points: MapPoint[] }
