export default function MonthPanel({ month, onChange }: { month: number; onChange: (m: number) => void }) {
  return (
    <div className="month-panel" data-tour="month">
      <div className="month-panel-head">
        <span className="month-panel-title">월 선택</span>
        <button
          type="button"
          className={`month-avg-chip ${month === 0 ? 'active' : ''}`}
          onClick={() => onChange(0)}
        >월평균</button>
      </div>
      <div className="month-grid-2x6">
        {Array.from({ length: 12 }, (_, i) => i + 1).map((m) => (
          <button
            key={m}
            type="button"
            className={`month-cell ${month === m ? 'active' : ''}`}
            onClick={() => onChange(m)}
            title={`${m}월`}
          >{m}월</button>
        ))}
      </div>
    </div>
  )
}
