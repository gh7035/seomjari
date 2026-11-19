import { useEffect, useRef, useState } from 'react'
import type { AgentEvent, ClarifyOption, DiagnoseForm, Report } from '../types'
import ReportCard from './ReportCard'
import { askChat, startDiagnose } from '../api'

interface Turn {
  id: string
  question: string
  events: AgentEvent[]
  report: Report | null
  busy: boolean
}

interface ClarifyState {
  question: string
  field: keyof DiagnoseForm
  options: ClarifyOption[]
}

export default function ChatPane({
  initialQuestion, events, report, busy, runId, form, onNewRun,
}: {
  initialQuestion: string | null
  events: AgentEvent[]
  report: Report | null
  busy: boolean
  runId: string | null
  form: DiagnoseForm | null
  onNewRun: (newRunId: string) => void
}) {
  const [turns, setTurns] = useState<Turn[]>([])
  const [q, setQ] = useState('')
  const [sending, setSending] = useState(false)
  const [err, setErr] = useState<string | null>(null)
  const scrollRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    if (!runId) return
    setTurns((prev) => {
      const existing = prev.find((t) => t.id === runId)
      if (existing) {
        return prev.map((t) => t.id === runId ? { ...t, events, report, busy } : t)
      }
      return [...prev, { id: runId, question: initialQuestion ?? '', events, report, busy }]
    })
  }, [runId, events, report, busy, initialQuestion])

  useEffect(() => {
    scrollRef.current?.scrollTo({ top: scrollRef.current.scrollHeight, behavior: 'smooth' })
  }, [turns])

  async function send(e: React.FormEvent) {
    e.preventDefault()
    const text = q.trim()
    if (!text || sending || busy) return
    setSending(true); setErr(null)
    try {
      const { run_id } = await askChat(runId, text)
      setTurns((prev) => [...prev, { id: run_id, question: text, events: [], report: null, busy: true }])
      setQ('')
      onNewRun(run_id)
    } catch (e2) {
      setErr(String(e2))
    } finally {
      setSending(false)
    }
  }

  async function onClarifyPick(c: ClarifyState, opt: ClarifyOption) {
    if (!form || sending || busy) return
    setSending(true); setErr(null)
    try {
      const merged: DiagnoseForm = assignField(form, c.field, opt.value)
      const id = await startDiagnose(merged)
      const label = `${fieldLabel(c.field)}: ${opt.label}`
      setTurns((prev) => [...prev, { id, question: label, events: [], report: null, busy: true }])
      onNewRun(id)
    } catch (e2) {
      setErr(String(e2))
    } finally {
      setSending(false)
    }
  }

  return (
    <div className="chat-pane">
      <div className="chat-head">
        <span className="chat-title">세션 대화</span>
        <span className="chat-sub">{turns.length ? `${turns.length}회 진단` : '대화 없음'}</span>
      </div>

      <div className="chat-scroll" ref={scrollRef}>
        {turns.length === 0 && <div className="chat-empty">진단이 시작되면 대화가 여기에 쌓입니다.</div>}
        {turns.map((t) => (
          <TurnBlock key={t.id} turn={t} onClarifyPick={onClarifyPick} />
        ))}
      </div>

      <form className="chat-input" data-tour="chat-input" onSubmit={send}>
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder={busy ? '분석 중…' : '예: 그럼 한림읍은 어때?'}
          disabled={busy || sending}
          autoComplete="off"
        />
        <button type="submit" disabled={busy || sending || !q.trim()}>전송</button>
        {err && <div className="chat-err">{err}</div>}
      </form>
    </div>
  )
}

function TurnBlock({ turn, onClarifyPick }: {
  turn: Turn
  onClarifyPick: (c: ClarifyState, opt: ClarifyOption) => void
}) {
  const steps = new Map<number, { name: string; status: 'running' | 'done' }>()
  const tools: { name: string; summary: string }[] = []
  let clarify: ClarifyState | null = null

  for (const e of turn.events) {
    if (e.type === 'step') steps.set(e.index, { name: e.name, status: e.status })
    else if (e.type === 'tool') {
      const name = (e.name ?? '').trim()
      const summary = (e.summary ?? '').trim()
      if (name && summary) tools.push({ name, summary })
    } else if (e.type === 'clarify') {
      clarify = { question: e.question, field: e.field, options: e.options ?? [] }
    }
  }
  const stepsArr = [...steps.entries()].sort(([a], [b]) => a - b)

  return (
    <div className="turn">
      {turn.question && (
        <div className="msg msg-user">
          <div className="msg-avatar">나</div>
          <div className="msg-bubble">{turn.question}</div>
        </div>
      )}
      <div className="msg msg-agent">
        <div className="msg-avatar">AI</div>
        <div className="msg-agent-body">
          {stepsArr.length > 0 && (
            <div className="turn-steps" data-tour="agent-progress">
              {stepsArr.map(([i, s]) => (
                <span key={i} className={`step ${s.status}`}>{s.status === 'done' ? '✓' : '⟳'} {s.name}</span>
              ))}
            </div>
          )}
          {tools.length > 0 && (
            <details className="turn-tools">
              <summary>도구 호출 {tools.length}회</summary>
              <ol>
                {tools.map((t, i) => (
                  <li key={i}><code>{t.name}</code> · {t.summary}</li>
                ))}
              </ol>
            </details>
          )}
          {clarify && !turn.report && (
            <ClarifyCard clarify={clarify} onPick={(opt) => onClarifyPick(clarify!, opt)} />
          )}
          {turn.report && !clarify && (
            <div className="turn-report">
              <ReportCard report={turn.report} />
            </div>
          )}
          {!turn.report && !clarify && turn.busy && <div className="turn-pending">분석 중…</div>}
        </div>
      </div>
    </div>
  )
}

function ClarifyCard({ clarify, onPick }: { clarify: ClarifyState; onPick: (opt: ClarifyOption) => void }) {
  return (
    <div className="clarify-card">
      <div className="clarify-head">
        <span className="clarify-tag">추가 정보 필요</span>
        <span className="clarify-field">{fieldLabel(clarify.field)}</span>
      </div>
      <div className="clarify-q">{clarify.question}</div>
      {clarify.options.length > 0 && (
        <div className="clarify-opts">
          {clarify.options.map((o) => (
            <button key={o.value} type="button" className="clarify-opt" onClick={() => onPick(o)}>{o.label}</button>
          ))}
        </div>
      )}
    </div>
  )
}

function assignField(form: DiagnoseForm, field: keyof DiagnoseForm, value: string): DiagnoseForm {
  if (field === 'ages') return { ...form, ages: value.split(',').map((v) => v.trim()).filter(Boolean) }
  if (field === 'customer') return { ...form, customer: value as DiagnoseForm['customer'] }
  if (field === 'risk') return { ...form, risk: value as DiagnoseForm['risk'] }
  if (field === 'category') return { ...form, category: value || null }
  if (field === 'dong') return { ...form, dong: value || null }
  if (field === 'question') return { ...form, question: value }
  return form
}

function fieldLabel(f: keyof DiagnoseForm): string {
  return {
    category: '업종', dong: '지역', customer: '주 고객', ages: '연령대',
    risk: '리스크 성향', question: '질문',
  }[f]
}
