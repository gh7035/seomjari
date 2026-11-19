import { useCallback, useEffect, useState } from 'react'
import ContextPanel from './components/ContextPanel'
import ChatPane from './components/ChatPane'
import MonthTimeline from './components/MonthTimeline'
import Map3D from './components/Map3D'
import Entry from './components/Entry'
import DetailPanel from './components/DetailPanel'
import Gutter from './components/Gutter'
import Tour from './components/Tour'
import { TOUR_A, TOUR_B } from './tour/steps'
import { askChat, getHealth, getMeta, startDiagnose, streamEvents } from './api'
import type { AgentEvent, DiagnoseForm, Meta, Report } from './types'

const TOUR_A_KEY = 'seomjari_tour_v1'
const TOUR_B_KEY = 'seomjari_tour_report_v1'
function hasSeen(key: string): boolean {
  try { return localStorage.getItem(key) === '1' } catch { return false }
}
function markSeen(key: string): void {
  try { localStorage.setItem(key, '1') } catch {}
}

type View = 'landing' | 'dashboard'

// 컬럼 폭 제약 (px) — 윈도우 폭에 따라 상한 재계산됨
const LEFT_MIN = 220, LEFT_MAX = 480
const RIGHT_MIN = 320, RIGHT_MAX = 520
const CENTER_MIN = 360
const DEFAULT_LEFT = 280
const DEFAULT_RIGHT = 380

function clamp(v: number, lo: number, hi: number) { return Math.max(lo, Math.min(hi, v)) }
function readStored(key: string, fallback: number): number {
  try {
    const v = Number(localStorage.getItem(key))
    return Number.isFinite(v) && v > 0 ? v : fallback
  } catch { return fallback }
}

export default function App() {
  const [view, setView] = useState<View>('landing')
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [mapReport, setMapReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)
  const [meta, setMeta] = useState<Meta | null>(null)
  const [runId, setRunId] = useState<string | null>(null)
  const [health, setHealth] = useState<{ ok: boolean; data_ready: boolean } | null>(null)
  const [initialForm, setInitialForm] = useState<DiagnoseForm | null>(null)
  const [initialQuestion, setInitialQuestion] = useState<string | null>(null)
  const [month, setMonth] = useState<number>(0)
  const [detail, setDetail] = useState<{ dong: string; lon: number; lat: number } | null>(null)
  const [leftW, setLeftW] = useState<number>(() => readStored('dash.leftW', DEFAULT_LEFT))
  const [rightW, setRightW] = useState<number>(() => readStored('dash.rightW', DEFAULT_RIGHT))
  const [winW, setWinW] = useState<number>(() => (typeof window !== 'undefined' ? window.innerWidth : 1400))
  const [tourA, setTourA] = useState<boolean>(false)
  const [tourB, setTourB] = useState<boolean>(false)

  // 첫 방문 시 자동 투어 A (랜딩 진입 직후)
  useEffect(() => {
    if (view === 'landing' && !hasSeen(TOUR_A_KEY)) {
      const t = setTimeout(() => setTourA(true), 400)
      return () => clearTimeout(t)
    }
  }, [view])

  // 첫 리포트 완성 직후 자동 투어 B (한 번만)
  useEffect(() => {
    if (view === 'dashboard' && report && !hasSeen(TOUR_B_KEY)) {
      const t = setTimeout(() => setTourB(true), 500)
      return () => clearTimeout(t)
    }
  }, [view, report])

  useEffect(() => {
    const onResize = () => setWinW(window.innerWidth)
    window.addEventListener('resize', onResize)
    return () => window.removeEventListener('resize', onResize)
  }, [])

  // 창 폭에 따라 상한을 더 좁혀서 중앙이 CENTER_MIN 이하로 짜부라지지 않게
  const maxLeft = Math.min(LEFT_MAX, Math.max(LEFT_MIN, winW - rightW - CENTER_MIN - 48))
  const maxRight = Math.min(RIGHT_MAX, Math.max(RIGHT_MIN, winW - leftW - CENTER_MIN - 48))
  const actualLeft = clamp(leftW, LEFT_MIN, maxLeft)
  const actualRight = clamp(rightW, RIGHT_MIN, maxRight)

  const onDragLeft = useCallback((dx: number) => {
    setLeftW((w) => {
      const next = clamp(w + dx, LEFT_MIN, LEFT_MAX)
      try { localStorage.setItem('dash.leftW', String(next)) } catch {}
      return next
    })
  }, [])
  const onDragRight = useCallback((dx: number) => {
    setRightW((w) => {
      const next = clamp(w + dx, RIGHT_MIN, RIGHT_MAX)
      try { localStorage.setItem('dash.rightW', String(next)) } catch {}
      return next
    })
  }, [])

  useEffect(() => { getMeta().then(setMeta).catch(() => setMeta(null)) }, [])
  useEffect(() => { getHealth().then(setHealth).catch(() => setHealth({ ok: false, data_ready: false })) }, [])

  function startStream(id: string) {
    setBusy(true); setEvents([]); setReport(null); setRunId(id)
    streamEvents(id, (ev) => {
      setEvents((prev) => [...prev, ev])
      if (ev.type === 'report') { setReport(ev.report); setMapReport(ev.report); setBusy(false) }
      if (ev.type === 'error') setBusy(false)
    })
  }

  async function onEntrySubmit(question: string) {
    setBusy(true)
    try {
      const { run_id, parsed } = await askChat(null, question)
      setInitialForm({
        category: parsed.category,
        dong: parsed.dong,
        customer: 'any', ages: [], risk: 'balanced',
        question,
      })
      setInitialQuestion(question)
      setView('dashboard')
      startStream(run_id)
    } catch (e) {
      setBusy(false)
      alert(`진단 요청 실패: ${e}`)
    }
  }

  async function onApply(form: DiagnoseForm) {
    const id = await startDiagnose(form)
    setInitialForm(form)
    setInitialQuestion(form.question ?? initialQuestion ?? '값 변경 후 재진단')
    startStream(id)
  }

  function onChatNewRun(newRunId: string) {
    // 후속 질문 스트리밍
    startStream(newRunId)
  }

  function backToLanding() {
    setView('landing'); setReport(null); setMapReport(null); setEvents([]); setRunId(null); setBusy(false)
    setInitialForm(null); setInitialQuestion(null)
  }

  if (view === 'landing') return (
    <>
      <Entry meta={meta} onSubmit={onEntrySubmit} busy={busy} onHelp={() => setTourA(true)} />
      <Tour steps={TOUR_A} open={tourA} onClose={() => { setTourA(false); markSeen(TOUR_A_KEY) }} />
    </>
  )

  return (
    <div className="dash">
      <div className="dash-top">
        <button className="back-btn" onClick={backToLanding}>← 처음으로</button>
        <div className="dash-brand"><span className="brand-dot" /> 섬자리</div>
        {meta && (
          <div className="dash-meta">
            기준 {meta.period.base} · 행정동 {meta.dongs.length}개 · 업종 {meta.categories.length}종
            {health && !health.data_ready && <span className="side-warn"> · ⚠ 데이터 미준비</span>}
          </div>
        )}
        <button className="help-btn" title="사용법 다시 보기" aria-label="사용법" onClick={() => setTourB(true)}>?</button>
      </div>

      <div
        className="dash-grid"
        style={{ gridTemplateColumns: `${actualLeft}px 6px minmax(${CENTER_MIN}px, 1fr) 6px ${actualRight}px` }}
      >
        <aside className="col-left">
          <ContextPanel meta={meta} form={initialForm} disabled={busy} onApply={onApply} />
        </aside>

        <Gutter side="left" onDrag={onDragLeft} />

        <section className="col-center">
          <div className="map-stack">
            <div className="map-wrap">
              <Map3D
                layer={mapReport?.map.layer ?? 'demand'}
                category={mapReport?.focus === 'gap'
                  ? (mapReport.alternatives?.[0]?.dong ?? null)
                  : (mapReport?.target.category ?? null)}
                highlight={mapReport?.map.highlight ?? []}
                month={month}
                onSelectDong={setDetail}
              />
              {detail && (
                <DetailPanel
                  dong={detail.dong}
                  lon={detail.lon}
                  lat={detail.lat}
                  category={report?.target.category ?? null}
                  onClose={() => setDetail(null)}
                />
              )}
            </div>
            <MonthTimeline
              month={month}
              onChange={setMonth}
              layer={report?.map.layer ?? 'demand'}
              category={report?.target.category ?? null}
              highlightDong={report?.map.highlight?.[0] ?? null}
            />
          </div>
        </section>

        <Gutter side="right" onDrag={onDragRight} />

        <aside className="col-right">
          <ChatPane
            initialQuestion={initialQuestion}
            events={events}
            report={report}
            busy={busy}
            runId={runId}
            form={initialForm}
            onNewRun={onChatNewRun}
          />
        </aside>
      </div>
      <Tour steps={TOUR_B} open={tourB} onClose={() => { setTourB(false); markSeen(TOUR_B_KEY) }} />
    </div>
  )
}
