import type { AgentEvent } from '../types'

export default function ProgressSteps({ events }: { events: AgentEvent[] }) {
  const steps = new Map<number, { name: string; status: string }>()
  const tools: string[] = []
  for (const e of events) {
    if (e.type === 'step') steps.set(e.index, { name: e.name, status: e.status })
    if (e.type === 'tool') tools.push(`${e.name}: ${e.summary}`)
  }
  if (steps.size === 0) return <span style={{ color: '#8c959f' }}>조건을 입력하고 진단을 시작하세요.</span>

  return (
    <div>
      <div className="steps">
        {[...steps.entries()].sort(([a], [b]) => a - b).map(([i, s]) => (
          <span key={i} className={`step ${s.status}`}>{s.status === 'done' ? '✓' : '⟳'} {s.name}</span>
        ))}
      </div>
      {tools.length > 0 && (
        <ul style={{ fontSize: 12, color: '#57606a', marginBottom: 0 }}>
          {tools.map((t, i) => <li key={i}>{t}</li>)}
        </ul>
      )}
    </div>
  )
}
