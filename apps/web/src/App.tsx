import { useState } from 'react'
import DiagnoseFormPanel from './components/DiagnoseForm'
import ProgressSteps from './components/ProgressSteps'
import ReportCard from './components/ReportCard'
import Map3D from './components/Map3D'
import Chat from './components/Chat'
import { startDiagnose, streamEvents } from './api'
import type { AgentEvent, DiagnoseForm, Report } from './types'

export default function App() {
  const [events, setEvents] = useState<AgentEvent[]>([])
  const [report, setReport] = useState<Report | null>(null)
  const [busy, setBusy] = useState(false)

  async function onSubmit(form: DiagnoseForm) {
    setBusy(true); setEvents([]); setReport(null)
    const runId = await startDiagnose(form)
    streamEvents(runId, (ev) => {
      setEvents((prev) => [...prev, ev])
      if (ev.type === 'report') { setReport(ev.report); setBusy(false) }
      if (ev.type === 'error') setBusy(false)
    })
  }

  return (
    <div className="layout">
      <aside className="sidebar">
        <h2>섬자리</h2>
        <p style={{ fontSize: 13, color: '#57606a' }}>성수기 착시를 걷어내는 제주 창업 입지 Agent</p>
        <DiagnoseFormPanel disabled={busy} onSubmit={onSubmit} />
      </aside>
      <main className="main">
        <div className="panel"><ProgressSteps events={events} /></div>
        <div className="grid-2">
          <div className="map-box"><Map3D layer={report?.map.layer ?? 'demand'} highlight={report?.map.highlight ?? []} /></div>
          <div className="panel"><ReportCard report={report} /></div>
        </div>
        <div className="panel"><Chat disabled={!report} /></div>
      </main>
    </div>
  )
}
