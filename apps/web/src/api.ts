import type { AgentEvent, DiagnoseForm } from './types'

export async function startDiagnose(form: DiagnoseForm): Promise<string> {
  const r = await fetch('/api/diagnose', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(form),
  })
  if (!r.ok) throw new Error(`diagnose ${r.status}`)
  return (await r.json()).run_id
}

export function streamEvents(runId: string, onEvent: (e: AgentEvent) => void): () => void {
  const es = new EventSource(`/api/diagnose/${runId}/events`)
  const handle = (msg: MessageEvent) => {
    const ev = JSON.parse(msg.data) as AgentEvent
    onEvent(ev)
    if (ev.type === 'report' || ev.type === 'error') es.close()
  }
  for (const t of ['step', 'tool', 'report', 'error']) es.addEventListener(t, handle as EventListener)
  return () => es.close()
}
