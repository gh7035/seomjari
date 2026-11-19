import { useEffect, useState } from 'react'
import type { DiagnoseForm, Meta } from '../types'

const AGES = ['20대', '30대', '40대', '50대', '60대+']

export default function DiagnoseFormPanel({ disabled, meta, initial, onSubmit }: {
  disabled: boolean
  meta: Meta | null
  initial?: DiagnoseForm | null
  onSubmit: (f: DiagnoseForm) => void
}) {
  const [f, setF] = useState<DiagnoseForm>(initial ?? { category: null, dong: null, customer: 'any', ages: [], risk: 'balanced' })

  useEffect(() => {
    if (initial) setF(initial)
  }, [initial])

  useEffect(() => {
    if (meta && !f.category) setF((prev) => ({ ...prev, category: meta.categories[0] ?? null }))
  }, [meta, f.category])

  if (!meta) return <div style={{ color: '#8c959f', fontSize: 13 }}>메타 로딩 중…</div>

  const toggleAge = (a: string) => setF({
    ...f,
    ages: f.ages.includes(a) ? f.ages.filter((x) => x !== a) : [...f.ages, a],
  })

  return (
    <form onSubmit={(e) => { e.preventDefault(); onSubmit(f) }}>
      <label>업종</label>
      <select value={f.category ?? ''} onChange={(e) => setF({ ...f, category: e.target.value || null })}>
        {meta.categories.map((c) => <option key={c} value={c}>{c}</option>)}
      </select>

      <label>희망 지역</label>
      <select value={f.dong ?? ''} onChange={(e) => setF({ ...f, dong: e.target.value || null })}>
        <option value="">상관없음 (지역 추천)</option>
        {meta.dongs.map((d) => <option key={d.name} value={d.name}>{d.name}</option>)}
      </select>

      <label>주 고객</label>
      <select value={f.customer} onChange={(e) => setF({ ...f, customer: e.target.value as DiagnoseForm['customer'] })}>
        <option value="any">상관없음</option>
        <option value="tourist">관광객</option>
        <option value="local">도민</option>
      </select>

      <label>타깃 연령</label>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
        {AGES.map((a) => {
          const active = f.ages.includes(a)
          return (
            <button
              key={a}
              type="button"
              onClick={() => toggleAge(a)}
              style={{
                flex: '0 0 auto', width: 'auto', padding: '5px 12px', fontSize: 12,
                background: active ? 'linear-gradient(135deg, #22d3ee, #10b981)' : 'rgba(255,255,255,0.03)',
                color: active ? '#04121a' : '#8b93a7',
                border: '1px solid ' + (active ? 'transparent' : '#1f2634'),
                borderRadius: 999, marginTop: 0, cursor: 'pointer',
                fontWeight: active ? 600 : 400,
              }}
            >{a}</button>
          )
        })}
      </div>

      <label>리스크 성향</label>
      <select value={f.risk} onChange={(e) => setF({ ...f, risk: e.target.value as DiagnoseForm['risk'] })}>
        <option value="safe">안정형</option>
        <option value="balanced">균형</option>
        <option value="aggressive">공격형</option>
      </select>

      <button type="submit" disabled={disabled}>{disabled ? '분석 중…' : '진단 시작'}</button>
    </form>
  )
}
