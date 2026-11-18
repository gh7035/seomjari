import type { Report } from '../types'

const DOT = { green: '🟢', yellow: '🟡', red: '🔴' } as const

export default function ReportCard({ report }: { report: Report | null }) {
  if (!report) return <span style={{ color: '#8c959f' }}>진단 결과가 여기에 표시됩니다.</span>

  return (
    <div>
      <h3 style={{ marginTop: 0 }}>{report.summary}</h3>
      <p>종합 점수 <b>{report.score}</b> / 100</p>
      <ul style={{ paddingLeft: 0, listStyle: 'none' }}>
        {report.signals.map((s) => (
          <li key={s.name} style={{ marginBottom: 8 }}>
            {DOT[s.level]} <b>{s.name}</b> {s.value}
            <div style={{ fontSize: 12, color: '#57606a' }}>{s.reason}</div>
          </li>
        ))}
      </ul>
      {report.alternatives && report.alternatives.length > 0 && (
        <>
          <h4>대안 지역</h4>
          <ol>{report.alternatives.map((a) => <li key={a.dong}>{a.dong} ({a.score}점): {a.why}</li>)}</ol>
        </>
      )}
      <details>
        <summary>근거와 한계</summary>
        <ul>{report.evidence.map((e, i) => <li key={i}>[{e.source} · {e.period}] {e.detail}</li>)}</ul>
        <ul>{report.limitations.map((l, i) => <li key={i}>{l}</li>)}</ul>
      </details>
    </div>
  )
}
