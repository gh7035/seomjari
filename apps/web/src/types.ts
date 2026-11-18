// packages/schema/report.schema.json 과 동기화 유지

export type Level = 'green' | 'yellow' | 'red'
export type MapLayer = 'demand' | 'tourism' | 'supply' | 'footfall'

export interface Signal { name: string; value: string; level: Level; reason: string }
export interface Alternative { dong: string; score: number; why: string }
export interface Evidence { source: 'D1' | 'D2' | 'D3' | 'D4'; period: string; detail: string }

export interface Report {
  summary: string
  target: { dong: string | null; category: string | null }
  signals: Signal[]
  score: number
  alternatives?: Alternative[]
  trend?: string | null
  evidence: Evidence[]
  limitations: string[]
  map: { layer: MapLayer; highlight: string[] }
}

export interface DiagnoseForm {
  category: string | null
  dong: string | null
  customer: 'tourist' | 'local' | 'any'
  ages: string[]
  risk: 'safe' | 'balanced' | 'aggressive'
  question?: string
}

export type AgentEvent =
  | { type: 'step'; index: number; name: string; status: 'running' | 'done' }
  | { type: 'tool'; name: string; args: unknown; summary: string }
  | { type: 'report'; report: Report; mode: 'llm' | 'fallback' }
  | { type: 'error'; message: string }
