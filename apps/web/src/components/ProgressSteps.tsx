import type { AgentEvent } from '../types'

export default function ProgressSteps({ events }: { events: AgentEvent[] }) {
  const stepMap = new Map<number, { name: string; status: 'running' | 'done' }>()
  const tools: { name: string; summary: string }[] = []
  let errorMsg: string | null = null

  for (const e of events) {
    if (e.type === 'step') {
      // 같은 index 는 최신 상태로 덮어쓰기 (running → done)
      stepMap.set(e.index, { name: e.name, status: e.status })
    } else if (e.type === 'tool') {
      tools.push({ name: e.name, summary: e.summary })
    } else if (e.type === 'error') {
      errorMsg = e.message
    }
  }

  if (stepMap.size === 0 && !errorMsg) {
    return <span style={{ color: '#8c959f' }}>조건을 입력하고 진단을 시작하세요.</span>
  }

  const steps = [...stepMap.entries()].sort(([a], [b]) => a - b)

  return (
    <div>
      <div className="steps">
        {steps.map(([i, s]) => (
          <span key={i} className={`step ${s.status}`} title={s.status}>
            {s.status === 'done' ? '✓' : '⟳'} {s.name}
          </span>
        ))}
      </div>
      {tools.length > 0 && (
        <div className="tool-log">
          <div className="tool-log-title">도구 호출 로그</div>
          <ol>
            {tools.map((t, i) => (
              <li key={i}>
                <code>{t.name}</code>
                <span className="tool-summary"> — {t.summary}</span>
              </li>
            ))}
          </ol>
        </div>
      )}
      {errorMsg && <div style={{ color: '#b42318', marginTop: 8 }}>오류: {errorMsg}</div>}
    </div>
  )
}
