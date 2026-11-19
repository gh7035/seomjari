import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, CartesianGrid, Legend } from 'recharts'
import type { Report, Level } from '../types'

const DOT: Record<Level, string> = { green: '🟢', yellow: '🟡', red: '🔴', unavailable: '⚪' }
const LEVEL_LABEL: Record<Level, string> = { green: '유리', yellow: '보통', red: '불리', unavailable: '데이터 없음' }

function scoreColor(score: number): string {
  if (score >= 70) return '#0b6e4f'
  if (score >= 45) return '#b58105'
  return '#b42318'
}

function firstSentence(s: string): string {
  const m = s.match(/^[^.?!。\n]+[.?!。]?/)
  return m ? m[0] : s
}

export default function ReportCard({ report }: { report: Report | null }) {
  if (!report) return <span style={{ color: '#8c959f' }}>진단 결과가 여기에 표시됩니다.</span>

  const isPartial = report.mode === 'partial'
  const signals = report.signals ?? []
  const availableCount = signals.filter((s) => s.level !== 'unavailable').length
  const hasScore = typeof report.score === 'number' && signals.length > 0

  const chartData = report.monthly_pattern
    ? report.monthly_pattern.labels.map((l, i) => ({
        month: l,
        매출: report.monthly_pattern!.values[i],
        관광: report.monthly_pattern!.tourism_values?.[i] ?? 0,
      }))
    : []

  const summaryHead = isPartial ? firstSentence(report.summary) : null
  const summaryRest = isPartial ? report.summary.slice(summaryHead?.length ?? 0).trimStart() : report.summary

  return (
    <div>
      <h3 style={{ marginTop: 0, marginBottom: 6, display: 'flex', alignItems: 'center', gap: 8 }}>
        {isPartial && <span className="partial-badge">부분 진단</span>}
        <span>{report.target.dong ?? '—'} · {report.target.category ?? '—'}</span>
      </h3>
      {isPartial && summaryHead && (
        <p className="summary-head" style={{ margin: '0 0 6px' }}>{summaryHead}</p>
      )}
      {summaryRest && (
        <p style={{ marginTop: 0, color: isPartial ? 'var(--text-dim)' : undefined }}>{summaryRest}</p>
      )}

      {hasScore && (
        <div className="score-row" data-tour="score">
          <div className="score-badge" style={{ color: scoreColor(report.score as number) }}>
            <div className="score-value">{report.score}</div>
            <div className="score-label">/ 100</div>
          </div>
          <div style={{ fontSize: 13, color: 'var(--text-mute)' }}>
            {availableCount > 0
              ? `${availableCount}개 신호를 가중 평균한 종합 점수. 높을수록 데이터상 유리.`
              : '신호 데이터가 없어 점수 산출에 한계가 있습니다.'}
          </div>
        </div>
      )}

      {signals.length > 0 && (
        <div className="signals" data-tour="signals">
          {signals.map((s) => {
            const unavail = s.level === 'unavailable'
            return (
              <div key={s.name} className={`signal signal-${s.level}`}>
                <div className="signal-head">
                  <span className="signal-dot">{DOT[s.level]}</span>
                  <span className="signal-name" title={s.name}>{s.name}</span>
                  <span className="signal-tag">{LEVEL_LABEL[s.level]}</span>
                </div>
                <div className="signal-value" title={unavail ? '데이터 없음' : s.value}>{unavail ? '데이터 없음' : s.value}</div>
                <div className="signal-reason" title={s.reason}>{s.reason}</div>
                {s.as_of && <div className="signal-asof" title={`데이터 시점 ${s.as_of}`}>as of {s.as_of}</div>}
              </div>
            )
          })}
        </div>
      )}

      {report.evidence?.some((e) => e.source === 'D6') && (
        <p className="trend-line">
          지역 생멸 · {report.evidence.find((e) => e.source === 'D6')?.detail}
        </p>
      )}

      {report.alternatives && report.alternatives.length > 0 && (
        <div className="alts" data-tour="alts">
          <h4>{report.focus === 'gap' ? '빈틈 업종' : `대안 지역 Top ${report.alternatives.length}`}</h4>
          <ul>
            {report.alternatives.map((a) => (
              <li key={a.dong}>
                <b>{a.dong}</b> <span className="alt-score">{a.score}점</span>
                <div className="alt-why">{a.why}</div>
              </li>
            ))}
          </ul>
        </div>
      )}

      {report.trend && (
        <div className="trend-line">업종 트렌드 · {report.trend}</div>
      )}

      {report.mode === 'llm_fallback' && (
        <p className="llm-fallback-note">※ LLM 오류로 규칙 기반으로 재생성된 리포트입니다.</p>
      )}

      <details className="evidence" data-tour="evidence">
        <summary>근거와 한계 펼치기</summary>

        {chartData.length > 0 && (
          <div style={{ height: 200, marginTop: 12 }}>
            <div style={{ fontSize: 12, color: '#57606a', marginBottom: 4 }}>
              월별 매출 패턴 (전체 vs 관광객)
            </div>
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={chartData} margin={{ top: 4, right: 16, bottom: 4, left: 0 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#e3e6ea" />
                <XAxis dataKey="month" fontSize={11} />
                <YAxis fontSize={11} tickFormatter={(v) => `${Math.round(v / 10000)}만`} />
                <Tooltip formatter={(v: number) => `${Math.round(v / 10000).toLocaleString()}만원`} />
                <Legend wrapperStyle={{ fontSize: 11 }} />
                <Line type="monotone" dataKey="매출" stroke="#0b6e4f" strokeWidth={2} dot={false} />
                <Line type="monotone" dataKey="관광" stroke="#b42318" strokeWidth={2} dot={false} />
              </LineChart>
            </ResponsiveContainer>
          </div>
        )}

        {report.evidence.length > 0 && (
          <>
            <h5>데이터 근거</h5>
            <ul>
              {report.evidence.map((e, i) => (
                <li key={i}><b>[{e.source} · {e.period}]</b> {e.detail}</li>
              ))}
            </ul>
          </>
        )}

        {report.limitations.length > 0 && (
          <>
            <h5>한계</h5>
            <ul>
              {report.limitations.map((l, i) => <li key={i}>{l}</li>)}
            </ul>
          </>
        )}
      </details>
    </div>
  )
}
