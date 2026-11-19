import { useState } from 'react'
import { askChat } from '../api'

export default function Chat({ disabled, runId, onNewRun }: {
  disabled: boolean
  runId: string | null
  onNewRun: (newRunId: string, parsed: { dong: string | null; category: string | null }) => void
}) {
  const [q, setQ] = useState('')
  const [busy, setBusy] = useState(false)
  const [err, setErr] = useState<string | null>(null)

  async function submit(e: React.FormEvent) {
    e.preventDefault()
    if (!q.trim() || disabled || busy) return
    setBusy(true); setErr(null)
    try {
      const { run_id, parsed } = await askChat(runId, q.trim())
      onNewRun(run_id, parsed)
      setQ('')
    } catch (e) {
      setErr(String(e))
    } finally {
      setBusy(false)
    }
  }

  return (
    <form onSubmit={submit} style={{ display: 'flex', gap: 8 }}>
      <input
        value={q}
        onChange={(e) => setQ(e.target.value)}
        disabled={disabled || busy}
        placeholder={disabled ? '진단 후 후속 질문을 할 수 있어요' : '예: 그럼 한림읍은 어때?'}
        style={{ flex: 1 }}
      />
      <button type="submit" disabled={disabled || busy || !q.trim()} style={{ width: 'auto', marginTop: 0, padding: '8px 16px' }}>
        {busy ? '…' : '보내기'}
      </button>
      {err && <div style={{ color: '#b42318', fontSize: 12, width: '100%' }}>{err}</div>}
    </form>
  )
}
